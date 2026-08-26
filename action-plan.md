# Action Plan — Multi-Client Reporting Platform

Self-contained specification. Use it as the opening brief in the implementation session: it holds every decision already made, with the reasoning, so none of it has to be relitigated.

**Language of this document and of the project: English.** See section 5.

---

## 1. Objective

Replace the Looker Studio dashboards sent to clients each month with a proprietary reporting web app — multi-project, multi-user, hosted on free or near-free infrastructure.

The owner is a digital marketing analyst with potentially **dozens of projects** (project = one client / one website). Target domain: `reporting.ciaodino.com`.

---

## 2. Non-negotiable constraints

1. **No payment method beyond the existing Google Cloud billing account.** No credit card is available for any other provider. Any service requiring a card on file — even for a free tier — is out.
2. **Near-zero cost**: the only billable component is Google Cloud, expected under $1/month at 60 projects. Everything else must sit on genuinely free tiers that do not ask for a card.
3. **No LLM dependency at runtime.** Extraction, storage, visualisation and comment generation must work without any AI model call. AI is allowed only while writing the code.
4. **Full post-hoc customisability** — see section 4; it is the load-bearing architectural requirement.
5. **No lock-in**: mainstream stack, owned code, no low-code platform.
6. **EU-only data residency** — see section 3.
7. Commercial use permitted by every service employed.

---

## 3. Stack

| Block | Technology | Notes |
|---|---|---|
| Extraction | **Cloud Run Jobs (`europe-west1`)** + Cloud Scheduler, Python container | GitHub is only the code repository |
| Google API auth | Service account + key in Secret Manager (EU region) | The service account must be added as Viewer on every GA4 property |
| Data plane | **Google Cloud Storage, bucket in `europe-west1`** — gzipped JSON objects | Private bucket, same region as Cloud Run |
| Data access | **Cloud Run service (`europe-west1`)** issuing short-lived V4 signed URLs | Validates the Supabase JWT and the user's project permission |
| Control plane + user auth | Supabase (Postgres + Auth, RLS), region **`eu-central-1`** | Free tier, no card required. ⚠️ Free projects pause after 7 days of inactivity — see the keep-alive requirement below |
| Transactional email | **Google Workspace SMTP**, configured as Supabase custom SMTP | Uses the existing ciaodino.com subscription; no new vendor, no card |
| Alerting | **Cloud Monitoring** notification channels (email) | Inside the existing GCP project; no third-party service |
| Frontend | React + Vite + TypeScript + ECharts | |
| Hosting | Cloudflare Pages | Free tier, no card required; static assets only, no data |
| Container build | Cloud Build + Artifact Registry | Needed to deploy the Cloud Run image |
| PDF export | Browser-side `@media print` CSS | No server infrastructure |

### Expected cost

| Item | Estimate at 60 projects |
|---|---|
| GCS storage (4.5 GB steady state, EU regional) | ~$0.10/month |
| GCS internet egress (1–2 GB/month, $0.12/GB first TB) | ~$0.12–0.25/month |
| GCS operations | negligible |
| Cloud Run jobs + service | $0 (within the permanent free tier) |
| Cloud Build + Artifact Registry | ~$0 (2,500 free build-minutes/month; first 0.5 GB of image storage free) |
| Supabase, Cloudflare Pages, Workspace SMTP | $0 (Workspace already subscribed) |

Bucket and Cloud Run share the same region, so **ETL reads and writes generate no egress charge**: only what browsers download is billed. Note that the Cloud Storage always-free allowance of 100 GB/month egress applies to US regions only (us-east1, us-west1, us-central1) and is therefore unavailable here — do not count on it.

### Payment method audit

Constraint 1 is easy to violate by accident, since most providers only ask for a card at the moment a feature is first used. Every component was checked; this is the result.

| Component | Card required? | Note |
|---|---|---|
| Google Cloud (Run, Storage, Scheduler, Secret Manager, Build, Artifact Registry, Monitoring, BigQuery) | Already covered | The existing billing account |
| Supabase Free | **No** | Commercial use permitted on the free plan |
| Cloudflare Pages Free | **No** | Adding a custom domain does not require one either |
| GitHub, private repository | **No** | Used only as a code repository |
| Google Workspace SMTP | **No** | Existing subscription |
| npm packages, React, ECharts | **No** | Open source |
| ~~Cloudflare R2~~ | **Yes** | Rejected for this reason |

**Two traps found during the audit**, both of which would have surfaced late:

- **Supabase auth email.** The built-in sender delivers only to addresses belonging to the project's own team and is capped at roughly 2 messages per hour; it is explicitly not intended for production. Client invitations and password resets would silently never arrive. Custom SMTP is therefore mandatory, and the card-free route is the existing Google Workspace account — a transactional provider like Resend or SendGrid would be an additional vendor and an additional payment method risk. Set this up in Phase 2, not when the first client cannot log in.
- **Alerting.** ETL alerts must go through Cloud Monitoring notification channels rather than a third-party email API, for the same reason.

**Keep-alive requirement**: Supabase free projects are paused after 7 days of inactivity. The nightly ETL touches the database on every run, which is normally enough, but a lightweight explicit ping must be part of the job so that a week of ETL failures does not also silently pause the control plane.

### Explicitly rejected options

- **Cloudflare R2** — technically the best fit (zero egress, 10 GB free) but requires a payment method on file even on the free plan. Blocked by constraint 1. If a card ever becomes available, migrating back is a change to the storage adapter only, and would return the bill to zero.
- **Vercel** — the Hobby plan forbids commercial use and client work; risk of account suspension.
- **GitHub Actions as the ETL runner** — hosted runners run on predominantly US infrastructure and region selection is Enterprise-only: incompatible with EU residency. Capped at 2,000 minutes/month anyway.
- **Cloudflare Workers Cron for the ETL** — the free plan caps CPU at 10 ms and subrequests at 50 per invocation, two orders of magnitude short.
- **Cloudflare KV or D1 as the data plane** — free and card-free, but KV replicates globally with no residency control, and D1 offers only a location *hint*, not a guarantee. Both fail constraint 6.
- **BigQuery as the data plane** — cost is roughly a wash (10 GB storage free, batch loading free, identical egress), so the decision is architectural. Serving from BigQuery turns every filter and dimension toggle into a query: a six-chart page becomes six queries at 0.5–2 s each, which is precisely the GA4-style interactivity this project exists to deliver. Billing on bytes scanned rather than rows returned also makes a forgotten `WHERE` clause an instant, silent cost. BigQuery stays where it belongs: override layer, event-level GA4 export for small properties, ad-hoc exploration. **Revisit this decision** when drill-down beyond predefined reports or cross-source joins are needed — at that point BigQuery becomes the warehouse and GCS keeps only the pre-computed serving artefacts, which is the standard pattern and is why the storage adapter exists.
- **Supabase Storage as the data plane** — 1 GB on the free tier against a 4.5 GB steady-state requirement, plus a 5 GB/month egress cap. Too tight.
- **A relational database for the reporting data** — at 60 projects that is ~30,000 rows/day, ~7 MB/day: the free Postgres tier saturates in two months.
- **Firestore instead of Supabase** — would give up Postgres, SQL and Row Level Security, which is the only reason per-client isolation costs a policy instead of a code module.
- **Firebase Hosting instead of Cloudflare Pages** — viable (the billing account exists) but subject to a daily transfer cap; Cloudflare Pages is free, uncapped, and needs no card.
- **Metabase / n8n / low-code** — require an always-on server and cannot deliver white-label multi-tenancy with per-client access.
- **User OAuth** — evaluated and rejected on setup complexity. If the analyst holds the Administrator role on the GA4 properties, they can add the service account themselves without involving clients.

### Data localisation: EU only

**Binding requirement: no data stored outside the European Union.** Every choice must be checked against this, and several settings are immutable once the resource is created.

| Component | Setting | Changeable later? |
|---|---|---|
| GCS bucket | location `europe-west1` | **No** — must be recreated and objects copied |
| Supabase | region `eu-central-1` (Frankfurt) | **No** — new project and migration |
| Cloud Run (job and service) | region `europe-west1` | Yes, by redeploying |
| Secret Manager | EU-region replication | No |
| BigQuery (if used) | dataset in `EU` location | **No** |
| GA4 → BigQuery export | dataset in `EU` location | **No** |
| Cloudflare Pages | irrelevant: static assets only, no data | — |

Choose a **single region**, not a multi-region: `EU` multi-region stays inside the Union but costs more and buys redundancy this workload does not need. Keeping the bucket in the same region as Cloud Run is what makes ETL traffic free.

**Why the ETL is not on GitHub Actions**: GitHub-hosted runners run on predominantly US infrastructure and region selection exists only on Enterprise plans. Data would transit outside the EU and workflow logs would be stored in the US.

**Distinction worth keeping in mind**: data residency (the bytes sit in the EU) is satisfied by this stack; provider jurisdiction is not, because Google remains a US company subject to the CLOUD Act. If a client contractually requires a processor operated by an EU entity, a European provider would be needed (Scaleway, OVH, Hetzner, Exoscale) and the cost would rise.

**Nature of the stored data**: aggregates — sessions by channel, revenue by country, products by category. No client IDs, no user IDs, no individual events. The only personal data in the stack are the analyst and client email addresses in Supabase. If event-level GA4 → BigQuery export were adopted later, the risk profile would change and must be reassessed.

### Cost control on Google Cloud

GCP now carries the backbone, so cost control becomes an operational requirement rather than a footnote. The two billable services behave very differently here, and the difference matters:

- **Cloud Storage egress has no hard cap.** Budgets are alerts, not blocks: there is no setting that makes Google stop serving bytes past a threshold. Control is procedural, not technical — which is why the bucket privacy rules below are mandatory rather than advisory.
- **BigQuery does have hard caps.** Custom quotas are proactive — with a 10 TB daily quota an 11 TB query simply cannot run — and can be set at project and per-user level. `maximum_bytes_billed` additionally fails a query before execution when the estimate exceeds the limit. Both must be configured if BigQuery is used at all.

Mandatory controls:

- **The bucket is private.** No public objects, no `allUsers` grant, uniform bucket-level access enabled. The only path to an object is a signed URL.
- **Signed URLs are short-lived** (minutes, not hours) and issued per request by the Cloud Run service after validating the JWT and the user's project assignment.
- **Budget alerts** on the billing account, at a threshold low enough to notice an anomaly within a day.
- **BigQuery custom quotas** set at project level, plus `maximum_bytes_billed` on every query issued by the application.
- **BigQuery queries always filtered on the partition**, if BigQuery is used at all.
- **Per-service quotas** lowered by hand where the console allows it.

The realistic failure mode is not gradual growth: it is a public object discovered by a crawler, or a runaway loop in the ETL. Both are addressed by the two rules above.

---

## 4. Load-bearing principle: everything is configuration, nothing is hardcoded

This is the requirement to verify at every single step of the implementation. **If a future change requires touching the code, the design is wrong.**

Operating rules:

- **No list of metrics or dimensions written in code.** Queries, reports, charts and tables are defined as JSON stored in the control plane and loaded at runtime.
- **Extracted raw data is immutable.** Every transformation is a layer on top, recomputable and reversible. Without this rule, changing a metric definition forces re-running every backfill.
- **Derived metrics are text expressions evaluated at read time**, not in the ETL. Change the formula and the entire history updates instantly, with no re-extraction.
- **Connectors are plugins** behind a common interface. Adding Google Ads or Shopify means adding a file, not modifying the orchestrator.
- **Storage is behind an adapter.** The rest of the system asks for "the object for project X, report Y, period Z" and does not know whether it comes from GCS, R2 or anything else. This is what makes a future move back to R2 a one-file change.
- **Automated comments are rules in configuration**, not hand-written functions.
- **Theming is per project**: logo, colours, client name in a table, not in CSS.
- **Every numeric threshold is a parameter**: no `if x > 0.03` anywhere in the code.

### Required configuration tables

| Table | Contents |
|---|---|
| `projects` | Projects, branding, timezone, currency, report language, hostname allowlist, retention window |
| `connections` | Credentials and resource IDs per source (a project has N connections) |
| `query_defs` | Extraction query definitions: source, dimensions, metrics, granularity, retention |
| `report_defs` | Page structure: which blocks, which datasets, layout, order |
| `derived_metrics` | Computed metrics as text expressions, per project or global |
| `exclusion_rules` | Row-level filter rules applied in the ETL |
| `metric_dictionary` | Canonical name, semantics, unit, additivity, **validity dates** |
| `comment_rules` | Thresholds, priorities and text templates for the comment engine |
| `users`, `project_users` | Users, roles and project assignment |
| `comments` | Generated and edited comments, with status and version |
| `etl_runs` | Run outcomes: rows extracted, duration, errors, identity switch log |

---

## 5. Language and internationalisation

**English is the source language of the entire project. Italian exists only as a display option in the frontend, where a translation is available.**

### English everywhere, without exception

Code, variable, table and column names, code comments, commit messages, logs, error messages, ETL alerts, configuration file names and config keys. All repository documentation, `README.md` included. This document itself.

It also applies to the canonical field schema: `source_medium`, `engaged_sessions`, `valid_sessions`. No Italian identifiers exist anywhere in the backend.

It applies equally to analyst-authored content: report titles, derived metric labels, comment templates, legal texts are **written in English first**. English is the source of truth; Italian is an optional overlay.

### Italian as a display layer

Language selector per user, preference stored in the profile. Default: English. Italian is offered **where a translation exists**, with automatic fallback to English for anything missing — never a blank label, never a machine translation.

**Two axes not to be confused:**

- **UI language** — a user preference. An Italian analyst may work with an Italian interface on a project whose report is delivered in English.
- **Report language** — a project attribute, since it depends on the recipient client. It drives the language of generated comments and of the exported PDF.

Keeping them separate prevents the case where a PDF meant for a foreign client comes out in Italian merely because that was the analyst's preference.

### Consequences for the configuration tables

**Config tables store multilingual content, not literal labels.** Two distinct mechanisms:

- **Static UI strings** (buttons, menus, messages) — one translation file per locale, handled with a standard i18n library. `en` is the reference file; `it` may be incomplete.
- **Analyst-authored content** (report titles, derived metric labels, legal texts, comments) — a per-locale JSONB field in the database, shaped like `{"en": "...", "it": "..."}`. **`en` is mandatory, `it` optional**, with explicit fallback to English when missing.

The comment engine holds **templates per locale**, authored in English, and generates in the report language. If an Italian template is missing, it falls back to the English one rather than machine-translating: an automatically translated text about to be sent to a client is exactly the kind of dependency this plan rules out.

### Data values are not translated

Values returned by GA4 — `Organic Search`, `Italy`, `mobile` — are data, not interface, and stay as the source delivers them. Optional **per-project label mappings** must nonetheless be available in configuration, for cases where an Italian client should see "Ricerca organica". A mapping, not an automatic translation: it stays an explicit analyst decision.

### Formatting

Numbers, dates and currencies must be formatted according to the active locale, not to a fixed format: comma decimal separator in Italian, period in English, different date formats. Handle it with the browser's native internationalisation APIs, never with hand-rolled formatting.

---

## 6. Data model

### Control plane / data plane separation

Reporting data **does not live in the database**. It lives in Google Cloud Storage as gzipped JSON objects, one per project/source/report/period, rewritten every night.

Suggested object key:

```
{project_id}/{source}/{report_key}/{granularity}/{period}.json.gz
example: acme/ga4/channels_overview/daily/2026-08.json.gz
```

Set `Content-Encoding: gzip` and `Content-Type: application/json` on upload so browsers decompress transparently.

### Read path

1. The frontend asks the Cloud Run service for a given object.
2. The service validates the Supabase JWT, checks in `project_users` that the caller may read that project, and returns a **V4 signed URL with a short TTL** (minutes).
3. The browser fetches the object directly from GCS and then performs filtering and dimension/metric toggling **entirely locally**.

No queries, no latency, no marginal cost beyond the bytes transferred. This is the mechanism that makes GA4-style interactivity sustainable at almost zero cost. **There must exist no path where the frontend reaches an object without going through the signing service**, and the bucket must never expose public objects.

### Retention: current calendar year plus the two preceding ones

**Rule**: keep the current calendar year and the two before it. In December 2026 the oldest available data is January 2024; in January 2027 the window shifts and 2024 is removed.

The window therefore varies between 24 and 36 months depending on the point in the year, and that is deliberate: it is anchored to calendar-year boundaries, not to a rolling N months. The reason is YoY comparison — displaying a 12-month period with a previous-year line always requires 24 full months upstream of the oldest month shown, and anchoring to the calendar year guarantees that margin never disappears.

**Implementation**:

- Purge job separate from the ETL, scheduled **once a year on 1 February**, not 1 January. The month of slack exists because the December report is delivered in January and must still have complete comparisons.
- The purge removes objects whose **data period** has a year lower than `current_year - 2`. Period partitioning in the key makes this a list plus a delete by prefix.
- The window is a per-project parameter (`retention_calendar_years`, default 2), not a constant in the code.
- The initial backfill is limited to the same window: no point extracting data that will be deleted.
- The nightly ETL never rewrites objects outside the window.
- **The purge concerns the data plane only.** Comments, configuration, ETL logs and users are kept indefinitely: they are small, and comments are the analyst's work, not regenerable data.

**Recommended option (per project, opt-in)**: before deleting, save a monthly-granularity rollup of summary data only and keep it with no expiry. A few dozen KB per project per year, and it answers the client asking for a five-year trend without having kept full daily detail.

### Sizing at 60 projects

With retention active, storage reaches a ceiling and stops growing.

| | Estimated usage | Limit or cost |
|---|---|---|
| GCS storage | 1.5–4.5 GB steady state, not cumulative | ~$0.10/month |
| GCS writes (Class A) | ~11,000/month | negligible |
| GCS egress | 1–2 GB/month | ~$0.12–0.25/month |
| Supabase DB | 10–20 MB | 500 MB free |
| Cloud Run (ETL + signing service) | 15–35 CPU hours/month | 50 hours free (180,000 vCPU-s) |

The first limit to saturate is Cloud Run CPU time, around 150–200 projects. Past that threshold the cost is marginal ($0.000024/vCPU-second) and requires no architectural change.

### Dataset families

A single flat schema across all sources does not hold: Shopify and Klaviyo do not speak in sessions and campaigns. Correct structure:

| Family | Sources | Grain | Core metrics |
|---|---|---|---|
| Traffic & spend | GA4, Google Ads, Meta, TikTok, GSC | date × campaign × channel | sessions, clicks, impressions, cost, conversions |
| Commerce | Shopify, Amazon, GA4 ecommerce | date × order / product | orders, revenue, units, returns |
| CRM & messaging | Klaviyo | date × flow / campaign | sends, opens, clicks, attributed revenue |

The glue between families is `date` plus the normalised UTM pair. **UTM normalisation is the real cross-source integration work**, not renaming columns.

### Canonical naming

Native source names never leave the adapter. `sessionSourceMedium` → `source_medium`, `screenPageViews` → `pageviews`. The rest of the system knows canonical names only. The point is to make the source replaceable (an aggregator such as Windsor.ai, for example) by rewriting a single file.

### Metric dictionary with validity dates

Metrics sharing a name while their semantics change over time are the fastest route to wrong automated comments. Real case from the existing report: GA total revenue included shipping and taxes until February 2026, and not afterwards. The comment engine queries the dictionary and, faced with a jump that coincides with a definition change, says so instead of announcing a collapse.

---

## 7. Extraction

- Nightly Cloud Run Job triggered by Cloud Scheduler, one task per project.
- **Never query GA4 from the frontend.** Quotas are per property: 200,000 tokens/day, 40,000/hour, 10 concurrent requests. With daily pre-aggregated extraction the problem does not arise.
- Initial backfill limited to the retention window, run as a separate manual execution with rate limiting.
- **Cardinality**: high-cardinality reports (product name, landing page) must be stored at monthly grain with top-N plus an "Others" bucket. It is why the *Performance by Item Name* page of the current report errors out in Looker Studio.
- Every run writes an outcome record in `etl_runs`. The admin panel surfaces it.

### Rolling re-extraction window

**Yesterday's GA4 data is not final.** Attribution settles over the following days and modelling is recomputed: an extraction that writes only the previous day and never touches it again produces a history that drifts progressively away from what the client sees in GA4.

Rule: every night, re-extract the **last 14 days** (per-project parameter), plus the current month at monthly grain. Writing to GCS is a full overwrite of the period object, so the operation is naturally idempotent and safely repeatable.

Consequence: a number already shown to a client may change within those 14 days. The exported PDF is therefore a dated snapshot, and must be stamped with generation date and time.

### Thresholding and the "(other)" row

Two GA4 mechanisms break totals and must be handled, not ignored:

- **Data thresholding**: with Google Signals active, GA4 hides low-volume rows to prevent user identification. The removed rows appear nowhere.
- **`(other)` row**: past cardinality limits, GA4 collapses the long tail into a single row.

Operating rule: **a total is never computed by summing the rows of a breakdown.** For every report, also extract the dimensionless query returning the true total and store it in the same object. The dashboard shows the true total and, when the rows do not sum up to it, explicitly exposes the difference as "unattributed" rather than letting the client discover on their own that the numbers do not reconcile.

### Timezone and currency

- Daily grain follows the **GA4 property timezone**, not the server's and not the browser's. Read it via the Admin API during onboarding and store it in `projects`: two properties of the same client may differ.
- Currency is the property's. Store the **currency code alongside the data** and never convert in the ETL: any conversion is a read-time derived metric, with rate and date made explicit.

### Modeled vs observed (confirmed requirement)

**Required feature, not optional.** The report must show sessions and revenue in both versions, with the gap between them.

The Data API does not return both: the Admin API (v1**alpha**) is needed to switch the property's reporting identity between `BLENDED` and `OBSERVED`. The constraint everything else follows from is that this is a **property-level change, not a query-level one**: during the switch window anyone reading that property — the client in GA4, a leftover Looker Studio report, other tools — sees different numbers.

Mandatory implementation requirements:

- **Atomic sequence per property**: read and record the initial identity, switch, run all of that property's queries, restore. Never switch multiple properties in parallel leaving windows open.
- **Guaranteed restore even on crash**: the restore goes in a `finally` block, and at the start of every run the ETL verifies that no property was left in the wrong state by the previous run. If it finds one, it restores and reports.
- **Narrowest possible nightly window**, with the identity switched only for the queries that need it.
- **Per-project configurable resting identity**: the ETL restores the value the property actually had, not a default written in code.
- **Explicit fallback**: the API is alpha and can change without notice. If the switch fails, the ETL still extracts the resting version, flags the data as partial, and the report page states that the comparison is unavailable for that day instead of displaying a false gap.
- **Switch logging** in `etl_runs`: initial state, final state, restore outcome. It is what lets you answer the client who noticed different numbers in GA4 at three in the morning.

**Schema implication, to be honoured from Phase 1**: affected datasets must carry the identity variant as an attribute (`blended` / `observed`) in the object key and in the file schema, even before the feature is implemented. Adding it later would mean rewriting keys and redoing backfills.

---

## 8. Bot-adjusted sessions metric

GA4 filters only known bots (the IAB list), it cannot be disabled, and it is not exposed as a dimension. The metric must be built, in three layers computed in the ETL and open to inspection:

1. **Base** — `engagedSessions` as the floor. It is GA4's own definition of a session with real activity (>10 s, or 2+ pageviews, or a conversion). No discretion involved.
2. **Hostname filter** — exclude traffic on hostnames outside the project allowlist. Catches staging, test environments and mirror sites scraping the GTM container.
3. **Anomalous segment detection** — cross `source_medium × browser × device_category × os × screen_resolution_bucket`, computing engagement rate, pages per session and average duration per cell. A cell is flagged non-human when **all three** conditions hold: near-zero engagement rate, ~1 page per session, and volume beyond 3 standard deviations from the median of the previous 8 weeks. Bounced human traffic satisfies the first two but not the third.

**Screen resolution**: `screenResolution` has very high cardinality and must be bucketed in the ETL into three classes — common (top 50 by volume for the project), rare, and suspicious (`(not set)`, implausible dimensions, known headless-browser defaults such as 800×600 and 1024×768). The third class does the work, and it is a sharper signal than the browser.

**In the dashboard**: three numbers side by side — GA sessions, valid sessions, % discarded — plus a diagnostic table of the excluded segments. The table is mandatory: the metric is only defensible with a client if what was removed is visible.

**Future extension** — once GSC and Google Ads are connected, a fourth layer is added: expected sessions anchored to actual clicks. In the current report the GA sessions / GSC clicks ratio runs between 129% and 248%, and GA / Ads clicks between 122% and 198%; sessions systematically exceeding clicks is anomalous, because a share of clicks naturally never becomes a tracked session.

---

## 9. Transformation layers

Three intervention points, in order of application. Precedence: **override > derived > raw**. Raw data is always kept.

1. **Exclusion rules (ETL)** — row-level filters from `exclusion_rules`. They produce a separate "excluded" object; they delete nothing.
2. **Derived metrics (read time)** — text expressions evaluated in the browser. This is where `valid_sessions` lives. Changeable retroactively without re-extraction.
3. **External overrides (ETL)** — a connector reading an external table with the fixed schema `project_id, date, dimension_key, metric_name, value` and merging it with precedence over GA4 data. Supports **Google Sheets** (free API) and **BigQuery**. It serves both to inject metrics computed elsewhere and to make targeted corrections: a month of broken tracking, a reclassified campaign.

The analyst panel must expose all three layers with direct editing and a preview of the effect.

### Non-additive metrics

The most delicate technical point of the architecture, because aggregation happens in the browser. **Rates, averages and ratios cannot be summed or averaged across rows.** If the user applies a filter or turns off a dimension, an engagement rate recomputed as the mean of the visible rows is simply wrong — and silently so: no error, just a plausible, false number.

Rule: **always store numerator and denominator, never the ratio alone.** Engagement rate is stored as `engaged_sessions` and `sessions`; conversion rate as `conversions` and `sessions`; average order value as `revenue` and `transactions`. The ratio is a derived metric, recomputed at read time over the sums of the rows actually visible after filtering.

Every metric in `metric_dictionary` therefore carries an additivity attribute — `sum`, `ratio`, `unique` — and the aggregation engine honours it. `unique` metrics (users, and sessions under certain breakdowns) are neither additive nor recomputable: they must be extracted at every breakdown level required, or marked unavailable when the user aggregates. Declaring it beats returning a sum that overstates.

**Future option for small projects**: native GA4 → BigQuery export, which yields raw events and therefore total freedom in reconstructing sessions. Constraint: standard properties are limited to 1 million events/day for the batch export, and if the limit is consistently exceeded the export is paused with no recovery of the lost days. Not viable for high-volume clients.

---

## 10. Authentication and roles

Supabase Auth with three roles:

- **Admin** — manages projects, connections, users, configuration.
- **Analyst** — accesses all projects, edits comments, uses the transformation panel.
- **Client** — read-only, restricted to assigned projects.

Per-project isolation is implemented with **Row Level Security in Postgres** for control-plane data, plus JWT validation in the Cloud Run signing service for data-plane objects. The signing service is the single choke point: it must re-check permissions on every request and never issue a URL for a project the caller is not assigned to.

UI requirements: project switcher always visible for analysts, cross-account overview with KPIs for every project, admin panel to create projects and invite users.

---

## 11. Automated comments

Deterministic rules engine, no LLM. Three layers:

1. **Computation** — MoM and YoY changes per metric and per dimension, contribution to the delta, outliers via z-score over the last 12 weeks.
2. **Rules** — thresholds and priorities from `comment_rules`, editable. For example: if a channel contributes more than 30% of the total delta, name it; if the change is within ±3%, call it stable.
3. **Templates with variants** — 3–5 phrasings per sentence type, rotated, so monthly reports do not read like photocopies.

One comment per report page, saved as a draft in `comments` with `draft` / `approved` status. The analyst's edited version supersedes the generated one and is kept in history. The engine always consults the metric dictionary before commenting on a jump.

### Partial periods

Comparing a month in progress against a complete month a year earlier always produces an apparent collapse. The engine must recognise the partial period and behave accordingly: compare **at equal elapsed days**, and state explicitly in the text that the period is incomplete. Same rule for the most recent days inside the re-extraction window, where data is still settling.

If a comparison cannot be computed on equal terms, the comment says so instead of omitting it: a missing figure noticed by the client costs more than a missing figure declared.

---

## 12. PDF export

Version 1: `@media print` CSS plus `window.print()`. Zero infrastructure, respects active filters and the comments approved at print time.

Version 2 (optional): Puppeteer inside a Cloud Run Job in `europe-west1` to generate and archive the monthly PDF automatically in GCS.

Print requirements: one report page per PDF page, header with project logo and period, comment always visible above the charts, generation timestamp in the footer, no interactive element printed.

---

## 13. Observability, backup and QA

### ETL monitoring

An ETL that fails silently is discovered when a client asks why the data has stopped. Minimum requirements:

- **Alert on a failed or skipped run**, through a Cloud Monitoring notification channel, naming the project and the error. A run that never starts must alert as loudly as one that errors: silence is the worst case.
- **Freshness indicator in the dashboard**: every page shows the date of the last successful update for that project.
- **Anomaly thresholds on extracted volume**: if a project extracts 90% fewer rows than its recent median, the ETL reports instead of overwriting a good object with an empty one. Broken client-side tracking manifests exactly like this.
- **Quota consumption** logged per property, to catch saturation before it becomes an error.
- **Egress and storage monitoring**: since these are billable, a monthly check against the budget alert is part of operations, not an optional extra.

### Backup

The data plane is regenerable by re-extracting from GA4, within the retention window. **The control plane is not**: configuration, metric dictionary, exclusion rules, and above all the comments edited by the analyst are non-reproducible work.

Requirement: **weekly dump of the configuration tables and comments to GCS**, in a versionable text format. It takes a few MB, and the Supabase free plan offers no restore guarantee to rely on.

### QA

- **Reconciliation**: a script comparing extracted totals against a manual check in the GA4 interface, to be run in Phase 1 on a pilot project and on every query change. It is the only way to catch a dimension or timezone error before it reaches a client report.
- **Config validation**: at startup, the application verifies that every `report_defs` entry references metrics and dimensions actually present in the objects. A config pointing at a non-existent field must fail loudly, not render an empty chart.
- **Snapshot tests on the comment engine**: given a fixed dataset, the generated text must be stable. It is what allows thresholds to be changed without discovering months later that one rule broke another.

---

## 14. Phases

| Phase | Deliverable | Customisability check |
|---|---|---|
| 0 | Working service account, GCS bucket in `europe-west1`, Supabase project in `eu-central-1`, config table schema, 1 pilot project | Adding a project is just an INSERT |
| 1 | GA4 ETL + GCS writes behind a storage adapter + backfill over the retention window + annual purge job + failed-run alerting via Cloud Monitoring + Supabase keep-alive ping + reconciliation script. **The object schema must already carry the reporting identity variant** | Adding a query is a `query_defs` record; changing retention or the re-extraction window is a `projects` field; changing storage provider is one adapter file |
| 2 | Auth, roles, RLS, signing service, project switcher, admin panel, **custom SMTP via Google Workspace** | Creating a client user requires no deploy |
| 3 | Report pages, filters, dimension/metric toggles, **i18n groundwork with EN/IT locales** | Adding a page is a `report_defs` record; adding a language is a translation file |
| 4 | Derived metrics, external overrides, transformation panel, **modeled vs observed extraction via Admin API** | Changing `valid_sessions` requires no re-extraction; the resting identity is a `projects` field |
| 5 | Comment engine + PDF export | Changing a threshold is a `comment_rules` record |
| 6 | Multi-account overview, client onboarding, custom domain, complete `README.md` and in-app "Data & privacy" page | Legal texts are configuration entries, not code strings |

Sources other than GA4 are out of scope for now, but the connector interface must be defined in Phase 1 and validated by writing a dummy adapter.

---

## 15. Anti-patterns to avoid

- Querying GA4 from the frontend.
- Lists of metrics, dimensions or pages written in code.
- Calling the GCS SDK directly from application code instead of going through the storage adapter.
- **Any public object or `allUsers` grant on the bucket.** Egress is billed: a public object found by a crawler is an invoice, not an error.
- Serving objects through anything other than a short-lived signed URL issued after JWT validation.
- Creating the bucket in a multi-region, or in a region different from Cloud Run: the first costs more, the second adds inter-region egress on every ETL run.
- Creating the GCS bucket, Supabase project or BigQuery dataset without pinning the location: these settings are immutable, and the mistake is only fixed by recreating and migrating.
- `localStorage` or `sessionStorage`.
- Overwriting raw data with transformed data.
- A single flat schema for all sources.
- High-cardinality reports at daily grain.
- Retention implemented with GCS lifecycle rules based on object age: objects are rewritten every night, so age bears no relation to the period of the data inside. Deletion must be decided on the period, never on object age.
- Deploying on Vercel.
- Storing a rate or an average without numerator and denominator: it makes correct recomputation after filtering impossible.
- Computing a total by summing the rows of a breakdown: thresholding and the `(other)` row make it systematically wrong.
- Extracting only the previous day and never revisiting it: GA4 data settles over subsequent days.
- Comparing a partial period against a complete one without declaring it.
- User-facing strings written in code instead of translation files: an automated check must catch them.
- Identifiers, logs, code comments or documentation in Italian.
- Literal labels stored in config tables instead of multilingual content.
- Machine-translating comments or source data values.
- Relying on Supabase's built-in email sender: it only reaches the project team and is capped at about 2 messages per hour.
- Introducing any provider that requires a payment method, however generous its free tier.

---

## 16. Required repository documentation

The repository must contain a final `README.md`, **written in English**, produced at the end of the implementation, with at least these sections:

1. **Architecture** — block diagram and data flow from API to dashboard.
2. **Setup from scratch** — resource creation, with localisation settings flagged as irreversible and the bucket privacy rules stated explicitly.
3. **Onboarding a new project** — full procedure, including adding the service account to the GA4 property.
4. **Configuration** — a description of every config table and what changing it achieves, with examples. This is the section that makes the customisability principle real: if a change is not documented here, it is not configurable.
5. **Derived metrics and exclusion rules** — expression syntax and the semantics of the `valid_sessions` metric.
6. **Metric dictionary** — how to update it and why validity dates are mandatory.
7. **Operations** — how to re-run a failed ETL, how to run a backfill, where to read the logs, how to check the monthly bill.
8. **Retention** — active window, annual purge date, what is deleted and what is not.
9. **Cost model** — what is billable, expected magnitude, and the controls in place.
10. **Data residency and provider jurisdiction** — text below.
11. **Known limits** — free-tier quotas, saturation thresholds, alpha APIs in use.

### Disclaimer text

Needed in two versions: **English in `README.md`** — the canonical version — and **English plus Italian as a configuration entry** for the application's "Data & privacy" page and the PDF footer, served according to the report language.

**English version (canonical, for `README.md` and the app):**

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

**Italian version (display only, for Italian-language reports):**

> **Residenza dei dati e giurisdizione del fornitore**
>
> Tutti i dati trattati da questo strumento sono archiviati esclusivamente all'interno dell'Unione Europea:
> - dati di reporting su Google Cloud Storage, bucket nella region `europe-west1` (Belgio), privato e accessibile solo tramite URL firmati a scadenza breve;
> - utenti, configurazioni e commenti su Supabase, region `eu-central-1` (Francoforte);
> - elaborazione ETL e controllo degli accessi su Google Cloud Run, region `europe-west1`;
> - credenziali su Google Secret Manager con replica in region UE.
>
> I dati di reporting archiviati sono **aggregati statistici** (sessioni per canale, ricavi per paese, prodotti per categoria) e non contengono identificatori individuali, client ID, user ID o eventi a livello di singolo utente. Gli unici dati personali trattati dallo strumento sono gli indirizzi email degli utenti abilitati all'accesso.
>
> **Limite noto.** I fornitori infrastrutturali impiegati — Google LLC e Cloudflare, Inc. per l'hosting del frontend statico — sono società di diritto statunitense e in quanto tali soggette al CLOUD Act, anche quando i dati risiedono fisicamente nell'Unione Europea. Lo strumento soddisfa pertanto il requisito di **residenza del dato**, ma non un eventuale requisito contrattuale di trattamento da parte di un responsabile stabilito esclusivamente nell'UE. Qualora un cliente ponga questo vincolo, i componenti di archiviazione ed elaborazione vanno migrati su fornitori europei (per esempio Scaleway, OVHcloud, Hetzner, Exoscale), con un impatto sui costi operativi.
>
> **Adempimenti a carico dell'operatore dello strumento**: stipula dei DPA con i fornitori, mantenimento aggiornato dell'elenco dei sub-responsabili, verifica delle basi giuridiche per il trattamento.
>
> Questo testo ha finalità informativa e non costituisce consulenza legale. Prima di utilizzarlo in un contesto contrattuale o di riprodurlo in un'informativa verso i clienti, sottoporlo a un consulente legale.

### Visibility of the disclaimer beyond the README

Developers read the README; clients do not. The same information, in condensed form, must also appear:

- on a **"Data & privacy"** page in the application, reachable by every role;
- in the **footer of the exported PDF**, as a single line: data stored in the EU, pointer to the full page.

Both texts come from a configuration entry, not from code, so updating them requires no deploy.

---

## 17. Sources

- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Cloud Storage locations](https://cloud.google.com/storage/docs/locations)
- [Cloud Storage V4 signed URLs](https://cloud.google.com/storage/docs/access-control/signed-urls)
- [Cloud Storage uniform bucket-level access](https://cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Google Cloud network pricing](https://cloud.google.com/vpc/network-pricing)
- [Cloud Run pricing and free tier](https://cloud.google.com/run/pricing)
- [Google Cloud Always Free](https://cloud.google.com/free/docs/free-cloud-features)
- [Cloud Billing budgets and alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [BigQuery free tier](https://cloud.google.com/bigquery/pricing#free-tier)
- [BigQuery custom query quotas](https://cloud.google.com/bigquery/docs/custom-quotas)
- [Controlling BigQuery costs](https://cloud.google.com/blog/topics/developers-practitioners/controlling-your-bigquery-costs)
- [Supabase pricing](https://supabase.com/pricing)
- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase — custom SMTP](https://supabase.com/docs/guides/auth/auth-smtp)
- [Supabase — production checklist](https://supabase.com/docs/guides/deployment/going-into-prod)
- [Cloud Monitoring notification channels](https://cloud.google.com/monitoring/support/notification-options)
- [Google Workspace SMTP relay](https://support.google.com/a/answer/2956491)
- [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/)
- [GA4 Data API — quotas](https://developers.google.com/analytics/devguides/reporting/data/v1/quotas)
- [GA4 Data API — dimensions and metrics schema](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema)
- [GA4 Admin API — reporting identity](https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1alpha/properties/getReportingIdentitySettings)
- [GA4 — engaged sessions](https://support.google.com/analytics/answer/12195621)
- [GA4 — BigQuery export limits](https://support.google.com/analytics/answer/9823238)
- [Service accounts for the Google Analytics APIs](https://developers.google.com/analytics/devguides/reporting/data/v1/quickstart-client-libraries)
- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)