# Reporting Platform

Proprietary, multi-tenant reporting web app replacing per-client Looker
Studio dashboards. Full rationale and every locked-in decision live in
[`action-plan.md`](action-plan.md); this document is the operational
reference. Target domain: `reporting.example.com` (replace with your own).

## 1. Architecture

```
┌─────────────┐   nightly cron    ┌──────────────────┐    gzip JSON     ┌─────────────┐
│ GA4 Data API │ ────────────────▶│  Cloud Run Job     │ ───────────────▶│ Cloudflare  │
│ (+ Admin API)│                   │  (etl/, Python,    │                  │ R2 (`eu`    │
└─────────────┘                   │  europe-west1)     │                  │ jurisdiction)│
                                   └─────────┬──────────┘                  └──────┬──────┘
                                             │ writes config/results               │ GET, JWT-gated
                                             ▼                                     ▼
                                   ┌──────────────────┐   REST + RLS    ┌─────────────────────┐
                                   │ Supabase Postgres  │◀───────────────│ Cloudflare Worker     │
                                   │ (eu-central-1)     │  auth + config  │ (worker/) — the only  │
                                   │ config + auth + RLS │────────────────▶│ path that reads R2    │
                                   └──────────┬──────────┘                └──────────┬───────────┘
                                              │ auth (Supabase JS)                    │ fetch
                                              ▼                                       ▼
                                   ┌──────────────────────────────────────────────────────┐
                                   │  React + Vite + TS + ECharts frontend (frontend/)      │
                                   │  — filtering/aggregation/derived metrics run HERE      │
                                   │  Hosted on Cloudflare Pages                            │
                                   └──────────────────────────────────────────────────────┘
```

Repository layout:

| Path | Role |
|---|---|
| `supabase/migrations/` | Control-plane schema (config tables) + RLS policies |
| `etl/` | Cloud Run Job: GA4 extraction, transforms, R2 writer, retention purge, alerting, reconciliation |
| `worker/` | Cloudflare Worker: the only path that reads reporting data out of R2 |
| `frontend/` | React app: report pages, admin panel, aggregation/derived-metric engines, i18n |
| `comment-engine/` | Deterministic (no-LLM) automated comment generation, shared by the ETL/an Edge Function |
| `scripts/` | Operational CLIs: backfill, reconciliation |

**Data plane vs control plane** (action-plan.md §6): reporting data itself
never touches Postgres — it lives on R2 as gzipped JSON, one file per
project/source/report/period, rewritten nightly. Supabase holds only
configuration, auth, and analyst-authored content (comments). The frontend
downloads one file per report block and does all filtering, dimension
toggling and metric aggregation **locally in the browser** — no query
latency, no marginal cost per view.

**Load-bearing principle** (action-plan.md §4): nothing about *what* is
extracted, *what* a report page shows, or *what* triggers a comment is
hardcoded. It all lives in the config tables listed in §4 below.

## 2. Setup from scratch

⚠️ Settings marked **IRREVERSIBLE** cannot be changed after creation — the
resource must be deleted and recreated, which for R2/Supabase/BigQuery means
a full data migration. Get these right the first time.

1. **GCP project** — create a project, enable the Google Analytics Data API,
   Google Analytics Admin API, Cloud Run, Cloud Scheduler, Secret Manager.
   Attach a billing account and **configure budget alerts immediately**
   (action-plan.md §3: GCP's free tier has no hard spending cap).
2. **Service account** — create one in the GCP project, generate a JSON key,
   store it in **Secret Manager with EU-region replication (IRREVERSIBLE)**.
   Do not commit the key file; `etl/.gitignore` already excludes
   `service-account*.json`.
3. **Cloudflare R2 bucket** — create with **jurisdiction `eu`
   (IRREVERSIBLE)**, not a location hint (`weur`/`eeur` are best-effort
   only, not a residency guarantee — action-plan.md §3). Jurisdiction-bound
   buckets must be managed via the API; some dashboard tooling doesn't
   support them. Access endpoint:
   `https://{account_id}.eu.r2.cloudflarestorage.com`.
4. **Supabase project** — create in **region `eu-central-1` (Frankfurt,
   IRREVERSIBLE)**. Run the migrations in `supabase/migrations/` in order
   (`supabase db push`, or apply the four `.sql` files manually via the SQL
   editor). Set `enable_signup = false` (already the default in
   `supabase/config.toml`) — users are invited by an admin, never
   self-registered.
5. **Cloud Run Job** — deploy `etl/` to **region `europe-west1`** (the one
   setting here that *is* changeable later, by redeploying):
   ```bash
   cd etl
   gcloud run jobs deploy reporting-etl \
     --source . \
     --region europe-west1 \
     --set-secrets GOOGLE_APPLICATION_CREDENTIALS=ga4-service-account:latest \
     --set-env-vars SUPABASE_URL=...,R2_ENDPOINT_URL=...,R2_BUCKET=...
   ```
6. **Cloud Scheduler** — create a job that triggers the Cloud Run Job
   nightly (e.g. `0 3 * * *` in the project's primary timezone).
7. **Cloudflare Worker** — `cd worker && wrangler secret put SUPABASE_JWT_SECRET`
   (found in the Supabase project's API settings), `wrangler secret put
   SUPABASE_ANON_KEY`, then `npm run deploy`.
8. **Cloudflare Pages** — connect the `frontend/` directory, build command
   `npm run build`, output directory `dist`. Set `VITE_SUPABASE_URL`,
   `VITE_SUPABASE_ANON_KEY`, `VITE_WORKER_URL` as Pages environment
   variables (copy from `frontend/.env.example`).
9. **Custom domain** — point your domain (e.g. `reporting.example.com`) at the Pages project.

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
   user" or `supabase.auth.admin.inviteUserByEmail`) — a trigger
   (`on_auth_user_created` in `0001_config_tables.sql`) automatically mirrors
   the new `auth.users` row into `public.users`, then insert a
   `project_users` row with the appropriate role (`admin` / `analyst` /
   `client`).
8. Run the manual backfill (bounded to the retention window, rate-limited):
   ```bash
   python scripts/backfill.py --project-slug <slug> --requests-per-minute 30
   ```
9. Run the reconciliation check against a manual GA4 UI read before treating
   the project as live (see §12 below).

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
"who can see what" — the Worker re-checks against the same policies rather
than re-implementing role logic (see `worker/src/index.ts`).

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
written to a separate file, never deleted.

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
Because R2 writes are full-object overwrites, re-running is always safe —
there is no partial-write state to clean up.

**Run a backfill**: `python scripts/backfill.py --project-slug <slug>
--requests-per-minute <n>` — bounded to the project's retention window,
rate-limited, and separate from the nightly cron on purpose.

**Read the logs**: Cloud Run Job execution logs are in Cloud Logging
(`europe-west1`); per-run outcome summaries (rows extracted, duration,
errors, reporting-identity switch outcome) are in the `etl_runs` table,
surfaced in the admin panel.

**Reconciliation**: `python scripts/reconcile.py --check
sessions:<extracted>:<manual_ga4_ui_value>` — run against the pilot project
in Phase 1 and after every `query_defs` change (action-plan.md §13).

## 8. Retention

- **Window**: current calendar year plus the two preceding
  (`projects.retention_calendar_years`, default 2) — 24 to 36 months
  depending on the point in the year, anchored to calendar-year boundaries
  so a 12-month YoY comparison never loses its prior-year data.
- **Purge date**: once a year, **1 February** (not 1 January) — the month
  of slack ensures the December report, delivered in January, still has a
  complete comparison at purge time.
- **What's deleted**: R2 objects whose *data period* (from the key, not the
  object's write timestamp — files are rewritten nightly) falls before
  `current_year - retention_calendar_years`. See
  `etl/src/reporting_etl/retention/purge.py`.
- **What's never deleted**: comments, configuration, ETL run history, users.
  Small, and — for comments — analyst work product, not regenerable data.
- **Optional pre-purge archive**: per-project opt-in
  (`projects.archive_summary_on_purge`) monthly-granularity rollup kept
  indefinitely, for answering a multi-year trend question without full
  daily detail.

## 9. Data residency and provider jurisdiction

> **Data residency and provider jurisdiction**
>
> All data handled by this tool is stored exclusively within the European Union:
> - reporting data on Cloudflare R2, bucket created with the `eu` jurisdiction (pinned to EU member-state data centres, no replication to North America);
> - users, configuration and comments on Supabase, region `eu-central-1` (Frankfurt);
> - ETL processing on Google Cloud Run, region `europe-west1`;
> - credentials in Google Secret Manager with EU-region replication.
>
> Stored reporting data consists of **statistical aggregates** (sessions by channel, revenue by country, products by category) and contains no individual identifiers, client IDs, user IDs or user-level events. The only personal data processed by the tool are the email addresses of authorised users.
>
> **Known limitation.** The infrastructure providers used — Cloudflare, Inc. and Google LLC — are US-incorporated companies and therefore subject to the CLOUD Act, even when data physically resides in the European Union. The tool therefore satisfies a **data residency** requirement, but not a contractual requirement for processing by a processor established exclusively within the EU. Should a client impose that constraint, the storage and compute components must be migrated to European providers (for example Scaleway, OVHcloud, Hetzner, Exoscale), with an impact on operating costs.
>
> **Obligations of the tool operator**: execute DPAs with the providers, maintain an up-to-date sub-processor list, verify the legal bases for processing.
>
> This text is informational and does not constitute legal advice. Have it reviewed by legal counsel before using it in a contractual context or reproducing it in a client-facing privacy notice.

The same text (EN + IT) is served in-app from the `legal_texts` config table
(`supabase/migrations/0004_legal_texts.sql`) via the "Data & Privacy" page
(`frontend/src/pages/DataPrivacyPage.tsx`) and, condensed to one line, in
the PDF footer — so updating the wording never requires a deploy.

## 10. Known limits

| Limit | Threshold | Consequence |
|---|---|---|
| GA4 Data API quota | 200,000 tokens/day, 40,000/hour, 10 concurrent requests per property | Never queried from the frontend; nightly pre-aggregated extraction stays well under this |
| Cloud Run free tier | 180,000 vCPU-seconds / 360,000 GiB-seconds per month (~50 CPU hours) | First limit to saturate, around 150–200 projects; past that, cost is marginal ($0.000024/vCPU-second) |
| R2 free tier | 10 GB storage, 1M writes/month | Not expected to saturate before Cloud Run does, at retention-window steady state |
| Supabase free tier | 500 MB DB, 50k MAU | Config-only data; expected 10–20 MB at 60 projects |
| GA4 → BigQuery export (if adopted) | 1M events/day for standard properties, batch export paused with no recovery if consistently exceeded | Not viable for high-volume clients; not in the current stack |
| GA4 Admin API (reporting identity) | **v1alpha** — can change without notice | `identity_switch.py` has an explicit fallback: on switch failure, extraction proceeds with the resting identity and the day is flagged partial, never a fabricated comparison |
| GCP billing | No hard spending cap on the free tier | Budget alerts are mandatory (see §2); every BigQuery query must filter on its partition column |

---

For every decision's full reasoning — including rejected alternatives — see
[`action-plan.md`](action-plan.md).
