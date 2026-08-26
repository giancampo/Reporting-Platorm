# Reporting Platform

Proprietary, multi-tenant reporting web app replacing per-client Looker
Studio dashboards. Full rationale and every locked-in decision live in
[`action-plan.md`](action-plan.md); this document is the operational
reference. Target domain: `reporting.example.com` (replace with your own).

**Binding constraint**: no payment method exists for any provider other
than the already-billed Google Cloud account (action-plan.md §2.1). Every
component in this stack was chosen or rejected on that basis — see §3
"Payment method audit" in the plan before adding anything new.

## 1. Architecture

```
┌─────────────┐   nightly cron    ┌──────────────────┐   gzip JSON      ┌──────────────┐
│ GA4 Data API │ ────────────────▶│  Cloud Run JOB     │ ────────────────▶│ Google Cloud │
│ (+ Admin API)│                   │  (etl/, Python,    │                  │ Storage       │
└─────────────┘                   │  europe-west1)     │                  │ (europe-west1,│
                                   └─────────┬──────────┘                  │ private)      │
                                             │ writes config/results        └──────┬───────┘
                                             ▼                                     │ signed URL only
                                   ┌──────────────────┐   REST + RLS    ┌──────────▼───────────┐
                                   │ Supabase Postgres  │◀───────────────│ Cloud Run SERVICE      │
                                   │ (eu-central-1)     │  auth + config  │ (signing-service/) —   │
                                   │ config + auth + RLS │────────────────▶│ the only path that     │
                                   └──────────┬──────────┘                │ reaches a GCS object   │
                                              │ auth (Supabase JS)        └──────────┬─────────────┘
                                              ▼                                      │ {url}, then a direct fetch
                                   ┌──────────────────────────────────────────────────────┐
                                   │  React + Vite + TS + ECharts frontend (frontend/)      │
                                   │  — filtering/aggregation/derived metrics run HERE      │
                                   │  Hosted on Cloudflare Pages (static assets only)       │
                                   └──────────────────────────────────────────────────────┘
```

Repository layout:

| Path | Role |
|---|---|
| `supabase/migrations/` | Control-plane schema (config tables) + RLS policies |
| `etl/` | Cloud Run Job: GA4 extraction, transforms, storage adapter, retention purge, alerting, reconciliation |
| `signing-service/` | Cloud Run service: the only path that issues access to a GCS object |
| `frontend/` | React app: report pages, admin panel, aggregation/derived-metric engines, i18n |
| `comment-engine/` | Deterministic (no-LLM) automated comment generation, shared by the ETL/an Edge Function |
| `scripts/` | Operational CLIs: backfill, reconciliation |

**Data plane vs control plane** (action-plan.md §6): reporting data itself
never touches Postgres — it lives in Google Cloud Storage as gzipped JSON,
one object per project/source/report/period, rewritten nightly. Supabase
holds only configuration, auth, and analyst-authored content (comments).
The frontend asks the signing service for a short-lived signed URL, fetches
the object directly from GCS, and does all filtering, dimension toggling
and metric aggregation **locally in the browser** — no query latency, no
marginal cost beyond the bytes transferred.

**Load-bearing principle** (action-plan.md §4): nothing about *what* is
extracted, *what* a report page shows, or *what* triggers a comment is
hardcoded. It all lives in the config tables listed in §4 below. Storage
itself is also behind an adapter (`etl/src/reporting_etl/storage/base.py`)
— swapping the backend is a one-file change, not an architecture change.

## 2. Setup from scratch

⚠️ Settings marked **IRREVERSIBLE** cannot be changed after creation — the
resource must be deleted and recreated, which for GCS/Supabase/BigQuery
means a full data migration. Get these right the first time.

1. **GCP project** — create a project (or use the existing one — this stack
   is designed to add zero new vendors), enable the Google Analytics Data
   API, Google Analytics Admin API, Cloud Run, Cloud Build, Artifact
   Registry, Cloud Scheduler, Secret Manager, Cloud Monitoring. Attach a
   billing account and **configure budget alerts immediately**
   (action-plan.md §3: GCP's free tier has no hard spending cap, and GCS
   egress specifically has no hard cap at all — see §9 below).
2. **Service account** (for GA4 extraction) — create one in the GCP
   project, generate a JSON key, store it in **Secret Manager with
   EU-region replication (IRREVERSIBLE)**. Do not commit the key file;
   `etl/.gitignore` already excludes `service-account*.json`.
3. **GCS bucket** — create in **`europe-west1` (Belgium, IRREVERSIBLE)**,
   a single region (not multi-region — costs more, buys redundancy this
   workload doesn't need). **Private, with uniform bucket-level access
   enabled and no `allUsers`/`allAuthenticatedUsers` grant, ever** — the
   only read path is a signed URL issued by `signing-service/`.
4. **Supabase project** — create in **region `eu-central-1` (Frankfurt,
   IRREVERSIBLE)**. Run the migrations in `supabase/migrations/` in order
   (`supabase db push`, or apply the four `.sql` files manually via the SQL
   editor). Set `enable_signup = false` (already the default in
   `supabase/config.toml`) — users are invited by an admin, never
   self-registered.
5. **Custom SMTP for Supabase Auth** — the built-in email sender only
   reaches the project's own team and is capped at ~2 messages/hour (not
   production-usable). In the Supabase dashboard, configure custom SMTP
   using your existing Google Workspace account's SMTP relay — no new
   vendor, no card. Do this now, in Phase 2, not when the first client
   can't log in.
6. **Cloud Run JOB** — deploy `etl/` to **region `europe-west1`** (the one
   setting here that *is* changeable later, by redeploying), same region as
   the bucket so ETL reads/writes never generate egress charges:
   ```bash
   cd etl
   gcloud run jobs deploy reporting-etl \
     --source . \
     --region europe-west1 \
     --set-secrets GOOGLE_APPLICATION_CREDENTIALS=ga4-service-account:latest \
     --set-env-vars SUPABASE_URL=...,SUPABASE_SERVICE_ROLE_KEY=...,GCS_BUCKET=...,GCP_PROJECT_ID=...
   ```
7. **Cloud Scheduler** — create a job that triggers the Cloud Run Job
   nightly (e.g. `0 3 * * *` in the project's primary timezone).
8. **Cloud Run SERVICE** (signing service) — deploy `signing-service/` to
   **region `europe-west1`**, same reasoning as the job:
   ```bash
   cd signing-service
   gcloud run deploy signing-service \
     --source . \
     --region europe-west1 \
     --set-env-vars SUPABASE_URL=...,SUPABASE_ANON_KEY=...,SUPABASE_JWT_SECRET=...,GCS_BUCKET=...
   ```
   Then grant the service's own runtime identity the `roles/iam.serviceAccountTokenCreator`
   role **on itself** — this is what lets it sign GCS URLs via IAM signBlob
   without a downloadable private key file:
   ```bash
   gcloud iam service-accounts add-iam-policy-binding <signing-service-sa-email> \
     --member="serviceAccount:<signing-service-sa-email>" \
     --role="roles/iam.serviceAccountTokenCreator"
   ```
9. **Cloud Monitoring alerting** — create a log-based metric filtering on
   `labels.reporting_etl_alert="true"` (see
   `etl/src/reporting_etl/alerting_sinks.py`), a notification channel
   (email), and an alerting policy tying the two together. Console or
   `gcloud alpha monitoring` — inside the existing GCP project, no third-party
   service.
10. **Cloudflare Pages** — connect the `frontend/` directory, build command
    `npm run build`, output directory `dist`. Set `VITE_SUPABASE_URL`,
    `VITE_SUPABASE_ANON_KEY`, `VITE_SIGNING_SERVICE_URL` as Pages
    environment variables (copy from `frontend/.env.example`). Cloudflare
    hosts static assets only here — no reporting data ever transits it.
11. **Custom domain** — point your domain (e.g. `reporting.example.com`) at
    the Pages project.

## 3. Onboarding a new project

1. In GA4, add the service account's email as **Viewer** on the property
   (Admin → Property Access Management). Requires the analyst to hold
   Administrator on that property — no client involvement needed
   (action-plan.md §3, "User OAuth... rejected on setup complexity").
2. Read the property's **timezone and currency** via the GA4 Admin API (or
   the GA4 UI: Admin → Property Settings) — these are stored per-project and
   never assumed.
3. Insert a row into `projects` (slug, display name, timezone, currency,
   report language, hostname allowlist, retention window). See
   `supabase/migrations/0003_seed_pilot_project.sql` for a worked example.
4. Insert a `connections` row: `source = 'ga4'`, `resource_id` = the GA4
   property ID.
5. Insert one `query_defs` row per report you want extracted (dimensions,
   metrics, granularity — mark `high_cardinality = true` for
   product/landing-page breakdowns).
6. Insert `report_defs` rows for the pages the client should see.
7. Assign users: invite the person via Supabase Auth (dashboard "Invite
   user" or `supabase.auth.admin.inviteUserByEmail`, delivered through the
   custom SMTP configured in §2.5) — a trigger (`on_auth_user_created` in
   `0001_config_tables.sql`) automatically mirrors the new `auth.users` row
   into `public.users`, then insert a `project_users` row with the
   appropriate role (`admin` / `analyst` / `client`).
8. Run the manual backfill (bounded to the retention window, rate-limited):
   ```bash
   python scripts/backfill.py --project-slug <slug> --requests-per-minute 30
   ```
9. Run the reconciliation check against a manual GA4 UI read before treating
   the project as live (see §7 below).

**No code change and no deploy is required for any of the above** — that is
the customisability principle in practice.

## 4. Configuration

Every table below lives in `supabase/migrations/0001_config_tables.sql`
(plus `0004_legal_texts.sql` for legal copy). Changing behaviour means
changing a row, never a file.

| Table | What changing it achieves | Example |
|---|---|---|
| `projects` | Per-client branding, timezone, currency, retention window, hostname allowlist, resting reporting identity | Set `retention_calendar_years = 5` for a client who wants longer history — no code touched |
| `connections` | Which sources feed a project, and their resource IDs | Add a second GA4 property to the same project |
| `query_defs` | What gets extracted: dimensions, metrics, granularity, cardinality handling | Add `landing_page` breakdown by inserting one row with `high_cardinality = true` |
| `report_defs` | Page structure: which blocks, which datasets, order, localized titles | Add a new report page by inserting a row — no frontend deploy |
| `derived_metrics` | Read-time computed metrics as text expressions | Change `engagement_rate`'s formula and the entire history updates instantly |
| `exclusion_rules` | Row-level ETL filters, non-destructive | Exclude a staging hostname without touching raw extracted data |
| `metric_dictionary` | Canonical metric semantics, unit, additivity, validity dates | Flag that `revenue`'s definition changed on a date — the comment engine then explains a jump instead of alarming about it |
| `comment_rules` | Thresholds, priorities, localized templates for the comment engine | Change the "notable channel" threshold from 30% to 25% contribution |
| `users` / `project_users` | Roles and per-project access | Grant a new client user `client` role on one project — no deploy |
| `comments` | Generated + analyst-edited commentary, versioned | — |
| `legal_texts` | EN/IT legal copy shown in-app and in the PDF footer | Update the data-residency disclaimer wording without a deploy |

RLS policies (`0002_rls_policies.sql`) are the single source of truth for
"who can see what" — the signing service re-checks against the same
policies (via a request made with the caller's own JWT, so RLS decides)
rather than re-implementing role logic; see
`signing-service/src/signing_service/access_control.py`.

## 5. Derived metrics and exclusion rules

**Derived metrics** (`derived_metrics.expression`): a small arithmetic
grammar — `+ - * /`, parentheses, metric-key identifiers, numeric literals —
evaluated client-side by `frontend/src/lib/derivedMetrics.ts` against
already-aggregated numerator/denominator sums (never against raw per-row
values, so ratio-safety is inherited from the aggregation engine). Example:
`engaged_sessions / sessions`. An expression referencing an unavailable
metric evaluates to `null`, which the UI renders as "unavailable", never as
`0`.

**`valid_sessions` semantics** (action-plan.md §8): three layers, in order —
1. `engaged_sessions` as the floor (GA4's own definition, no discretion).
2. Hostname allowlist filter (`projects.hostname_allowlist`) — drops
   staging/mirror traffic.
3. Anomalous-segment detection — a `source_medium × browser × device ×
   os × screen_resolution_bucket` cell is flagged non-human only when
   **all three** hold: near-zero engagement rate, ~1 page/session, and
   volume beyond 3 standard deviations from its own 8-week baseline. See
   `etl/src/reporting_etl/transform/bot_filter.py`.

The dashboard must always show GA sessions, valid sessions, % discarded, and
the diagnostic table of what was excluded and why — see
`ValidSessionsDiagnostic.tsx`.

**Exclusion rules** (`exclusion_rules.filter_expression`): a restricted
boolean grammar (`==`, `!=`, comparisons, `and`/`or`/`not`) over canonical
dimension/metric names, evaluated by
`etl/src/reporting_etl/transform/exclusion_rules.py`. Deliberately not
`eval`/arbitrary code — this is analyst-authored config. Excluded rows are
written to a separate object, never deleted.

## 6. Metric dictionary

Every metric referenced anywhere (report block, derived-metric formula,
comment rule) must have a `metric_dictionary` row declaring its
**additivity** (`sum` / `ratio` / `unique`) and, for ratios, its
`numerator_key`/`denominator_key`. This is what lets the aggregation engine
(`frontend/src/lib/aggregation.ts`) recompute a ratio correctly after a
filter changes which rows are visible, instead of averaging a stored
per-row ratio (the single most delicate correctness rule in the system —
action-plan.md §9).

**Validity dates matter**: when a metric's real-world definition changes
(the doc's example: GA total revenue included shipping/taxes until a
certain date, then didn't), insert a **new** `metric_dictionary` row with
`valid_from` set to the change date rather than editing the old row's
semantics in place. The comment engine
(`comment-engine/src/comment_engine/metric_dictionary.py`) checks whether a
comparison window spans a definition change and appends an explanatory note
instead of reporting a false collapse/spike.

## 7. Operations

**Re-run a failed ETL run**: find the failed `etl_runs` row (surfaced in the
admin panel), then re-invoke the Cloud Run Job for that project:
```bash
gcloud run jobs execute reporting-etl --region europe-west1 --args="--project-slug=<slug>"
```
Because GCS writes are full-object overwrites, re-running is always safe —
there is no partial-write state to clean up.

**Run a backfill**: `python scripts/backfill.py --project-slug <slug>
--requests-per-minute <n>` — bounded to the project's retention window,
rate-limited, and separate from the nightly cron on purpose.

**Read the logs**: Cloud Run Job execution logs are in Cloud Logging
(`europe-west1`); per-run outcome summaries (rows extracted, duration,
errors, reporting-identity switch outcome) are in the `etl_runs` table,
surfaced in the admin panel. Alerts written by
`alerting_sinks.CloudMonitoringAlertSink` also land in Cloud Logging with
`labels.reporting_etl_alert = "true"`.

**Reconciliation**: `python scripts/reconcile.py --check
sessions:<extracted>:<manual_ga4_ui_value>` — run against the pilot project
in Phase 1 and after every `query_defs` change (action-plan.md §13).

**Check the monthly bill**: GCS egress and storage are the only lines with
real (if small) cost — see §9 below. Check the Billing console monthly; the
budget alert from setup step 2.1 is the backstop, not a substitute.

## 8. Retention

- **Window**: current calendar year plus the two preceding
  (`projects.retention_calendar_years`, default 2) — 24 to 36 months
  depending on the point in the year, anchored to calendar-year boundaries
  so a 12-month YoY comparison never loses its prior-year data.
- **Purge date**: once a year, **1 February** (not 1 January) — the month
  of slack ensures the December report, delivered in January, still has a
  complete comparison at purge time.
- **What's deleted**: GCS objects whose *data period* (from the key, not
  the object's write timestamp — objects are rewritten nightly) falls
  before `current_year - retention_calendar_years`. See
  `etl/src/reporting_etl/retention/purge.py`.
- **What's never deleted**: comments, configuration, ETL run history, users.
  Small, and — for comments — analyst work product, not regenerable data.
- **Optional pre-purge archive**: per-project opt-in
  (`projects.archive_summary_on_purge`) monthly-granularity rollup kept
  indefinitely, for answering a multi-year trend question without full
  daily detail.

## 9. Cost model

The only billable component in this stack is Google Cloud (action-plan.md
§2.2: "expected under $1/month at 60 projects"). Everything else — Supabase,
Cloudflare Pages, Workspace SMTP — sits on a genuinely free, card-free tier.

| Item | Estimate at 60 projects |
|---|---|
| GCS storage (4.5 GB steady state, EU regional) | ~$0.10/month |
| GCS internet egress (1–2 GB/month, $0.12/GB first TB) | ~$0.12–0.25/month |
| GCS operations | negligible |
| Cloud Run job + signing service | $0 (within the permanent free tier) |
| Cloud Build + Artifact Registry | ~$0 (2,500 free build-minutes/month; first 0.5 GB image storage free) |
| Supabase, Cloudflare Pages, Workspace SMTP | $0 |

Bucket and both Cloud Run components share `europe-west1`, so **ETL reads
and writes generate no egress charge**: only what browsers download (via
signed URLs) is billed. The Cloud Storage always-free 100 GB/month egress
allowance applies to US regions only — unavailable here, don't count on it.

**Controls in place** (mandatory, not advisory — GCS egress has no hard
cap, only budget *alerts*):
- The bucket is private, uniform bucket-level access, no public objects.
- Signed URLs are short-lived (5 minutes, `signing-service/src/signing_service/main.py`'s
  `SIGNED_URL_TTL_SECONDS`).
- Budget alerts on the billing account (setup step 2.1).
- If BigQuery is ever used (override layer, event-level export): custom
  quotas at project level plus `maximum_bytes_billed` on every query, and
  every query filtered on its partition column.

The realistic failure mode is not gradual growth: it's a public object
found by a crawler, or a runaway ETL loop. Both are addressed by the two
bolded controls above.

## 10. Data residency and provider jurisdiction

> **Data residency and provider jurisdiction**
>
> All data handled by this tool is stored exclusively within the European Union:
> - reporting data in Google Cloud Storage, bucket located in `europe-west1` (Belgium), private, accessible only through short-lived signed URLs;
> - users, configuration and comments on Supabase, region `eu-central-1` (Frankfurt);
> - ETL processing and access control on Google Cloud Run, region `europe-west1`;
> - credentials in Google Secret Manager with EU-region replication.
>
> Stored reporting data consists of **statistical aggregates** (sessions by channel, revenue by country, products by category) and contains no individual identifiers, client IDs, user IDs or user-level events. The only personal data processed by the tool are the email addresses of authorised users.
>
> **Known limitation.** The infrastructure providers used — Google LLC and Cloudflare, Inc. for static frontend hosting — are US-incorporated companies and therefore subject to the CLOUD Act, even when data physically resides in the European Union. The tool therefore satisfies a **data residency** requirement, but not a contractual requirement for processing by a processor established exclusively within the EU. Should a client impose that constraint, the storage and compute components must be migrated to European providers (for example Scaleway, OVHcloud, Hetzner, Exoscale), with an impact on operating costs.
>
> **Obligations of the tool operator**: execute DPAs with the providers, maintain an up-to-date sub-processor list, verify the legal bases for processing.
>
> This text is informational and does not constitute legal advice. Have it reviewed by legal counsel before using it in a contractual context or reproducing it in a client-facing privacy notice.

The same text (EN + IT) is served in-app from the `legal_texts` config table
(`supabase/migrations/0004_legal_texts.sql`) via the "Data & Privacy" page
(`frontend/src/pages/DataPrivacyPage.tsx`) and, condensed to one line, in
the PDF footer — so updating the wording never requires a deploy.

## 11. Known limits

| Limit | Threshold | Consequence |
|---|---|---|
| No payment method beyond GCP | Binding constraint (action-plan.md §2.1) | Any provider requiring a card, however generous its free tier, is out — see §3 "Payment method audit" in the plan before adding a dependency |
| GA4 Data API quota | 200,000 tokens/day, 40,000/hour, 10 concurrent requests per property | Never queried from the frontend; nightly pre-aggregated extraction stays well under this |
| Cloud Run free tier | 180,000 vCPU-seconds / 360,000 GiB-seconds per month (~50 CPU hours), shared across the job and the signing service | First limit to saturate, around 150–200 projects; past that, cost is marginal ($0.000024/vCPU-second) |
| GCS egress | No hard cap — budgets are alerts, not blocks | Procedural control only: private bucket + short-lived signed URLs (§9) |
| Supabase free tier | 500 MB DB, 50k MAU, **project pauses after 7 days of inactivity** | Config-only data, expected 10–20 MB at 60 projects; `ConfigClient.ping()` runs at the top of every nightly ETL invocation as an explicit keep-alive |
| Signed URL TTL | 5 minutes | A page open longer than that re-requests on the next data refresh, not a one-time load; not an issue in practice since the frontend re-fetches per period change |
| GA4 → BigQuery export (if adopted) | 1M events/day for standard properties, batch export paused with no recovery if consistently exceeded | Not viable for high-volume clients; not in the current stack |
| GA4 Admin API (reporting identity) | **v1alpha** — can change without notice | `identity_switch.py` has an explicit fallback: on switch failure, extraction proceeds with the resting identity and the day is flagged partial, never a fabricated comparison |
| GCP billing | No hard spending cap on the free tier | Budget alerts are mandatory (see §2); every BigQuery query must filter on its partition column |

---

For every decision's full reasoning — including rejected alternatives and
the payment-method audit — see [`action-plan.md`](action-plan.md).
