# Action Plan — Multi-Client Reporting Platform

Self-contained specification. Use it as the opening brief in the implementation session: it holds every decision already made, with the reasoning, so none of it has to be relitigated.

**Language of this document and of the project: English.** See section 5.

---

## 1. Objective

Replace the Looker Studio dashboards sent to clients each month with a proprietary reporting web app — multi-project, multi-user, hosted on a free-tier stack.

The owner is a digital marketing analyst with potentially **dozens of projects** (project = one client / one website). Target domain: `reporting.example.com`.

---

## 2. Non-negotiable constraints

1. **Zero cost** for hosting, extraction, storage and visualisation, up to at least 100 projects.
2. **No LLM dependency at runtime.** Extraction, storage, visualisation and comment generation must work without any AI model call. AI is allowed only while writing the code.
3. **Full post-hoc customisability** — see section 4; it is the load-bearing architectural requirement.
4. **No lock-in**: mainstream stack, owned code, no low-code platform.
5. Commercial use permitted by every service employed.

---

## 3. Stack

| Block | Technology | Notes |
|---|---|---|
| Extraction | **Cloud Run Jobs (`europe-west1`)** + Cloud Scheduler, Python container | Chosen for the EU residency requirement; GitHub is only the code repository |
| Google API auth | Service account + key in Secret Manager (EU region) | The service account must be added as Viewer on every GA4 property |
| Data plane | Cloudflare R2, bucket with **`eu` jurisdiction** — gzipped JSON files | 10 GB storage, 1M writes/month, free egress |
| Control plane + user auth | Supabase (Postgres + Auth, RLS), region **`eu-central-1`** | 500 MB, 50k MAU |
| Frontend | React + Vite + TypeScript + ECharts | |
| Hosting | Cloudflare Pages + Workers | Static assets on the CDN only, no data |
| PDF export | Browser-side `@media print` CSS | No server infrastructure |

### Explicitly rejected options

- **Vercel** — the Hobby plan forbids commercial use and client work; risk of account suspension.
- **GitHub Actions as the ETL runner** — hosted runners run on predominantly US infrastructure and region selection is Enterprise-only: incompatible with the EU residency requirement. It was capped at 2,000 minutes/month anyway.
- **Cloudflare Workers Cron for the ETL** — the free plan caps CPU at 10 ms and subrequests at 50 per invocation, two orders of magnitude short. Even on Workers Paid it would force rewriting the ETL in JavaScript and splitting it across queues.
- **Google Cloud Storage or Firebase Hosting instead of R2** — GCS charges egress (~$0.12/GB) and its free tier is 5 GB in US regions only; R2 egress is always free. For an app serving JSON files to client browsers, egress is the dominant cost line.
- **Firestore instead of Supabase** — would give up Postgres, SQL and Row Level Security, which is the only reason per-client isolation costs a policy instead of a code module.
- **A relational database for the reporting data** — at 60 projects that is ~30,000 rows/day, ~7 MB/day: the free Postgres tier saturates in two months.
- **Metabase / n8n / low-code** — require an always-on server and cannot deliver white-label multi-tenancy with per-client access.
- **User OAuth** — evaluated and rejected on setup complexity. If the analyst holds the Administrator role on the GA4 properties, they can add the service account themselves without involving clients.

### Data localisation: EU only

**Binding requirement: no data stored outside the European Union.** Every choice must be checked against this, and almost every setting is immutable once the resource is created.

| Component | Setting | Changeable later? |
|---|---|---|
| R2 | bucket created with `eu` jurisdiction | **No** — must be recreated |
| Supabase | region `eu-central-1` (Frankfurt) | **No** — new project and migration |
| Cloud Run Jobs | region `europe-west1` | Yes, by redeploying |
| Secret Manager | EU-region replication | No |
| BigQuery (if used) | dataset in `EU` location | **No** |
| GA4 → BigQuery export | dataset in `EU` location | **No** |
| Cloudflare Pages | irrelevant: static assets only, no data | — |

**Location hints vs jurisdictions on R2**: two different things, and only the second is a guarantee. Location hints (`weur`, `eeur`) are best effort for performance; jurisdictions enforce that data is stored and processed within the jurisdiction, pinned to EU member-state data centres with no replication to North America. Use `eu` as a jurisdiction, not as a hint.

Operational consequences of the jurisdiction: access goes through a dedicated endpoint, `https://{account_id}.eu.r2.cloudflarestorage.com`, and some Cloudflare dashboard tooling does not interact with jurisdiction-bound buckets, which must therefore be managed via API.

**Why the ETL is not on GitHub Actions**: GitHub-hosted runners run on predominantly US infrastructure and region selection exists only on Enterprise plans. Data would transit outside the EU and workflow logs would be stored in the US. Hence Cloud Run Jobs in `europe-west1` from Phase 1, with Cloud Scheduler as the trigger and GitHub used purely as a repository.

**Distinction worth keeping in mind**: data residency (the bytes sit in the EU) is satisfied by this stack; provider jurisdiction is not, because Cloudflare and Google remain US companies subject to the CLOUD Act. If a client contractually requires a processor operated by an EU entity, a European provider would be needed (Scaleway, OVH, Hetzner, Exoscale) and the cost would no longer be zero.

**Nature of the stored data**: aggregates — sessions by channel, revenue by country, products by category. No client IDs, no user IDs, no individual events. The only personal data in the stack are the analyst and client email addresses in Supabase. If event-level GA4 → BigQuery export were adopted later, the risk profile would change and must be reassessed.

### Role of Google Cloud

The GCP project exists regardless, since it hosts the service account and the Analytics APIs. Google Cloud enters the stack only where the load is predictable and bounded, never as the backbone.

**Allowed**:
- **Cloud Run Jobs** as the ETL runner, in `europe-west1`, from Phase 1 for the EU residency requirement. Free tier: 180,000 vCPU-seconds and 360,000 GiB-seconds per month, permanent, commercial use allowed — roughly 50 hours of CPU. Google's own example of a job in europe-west1 launched hourly for one minute with 1 vCPU and 512 MiB estimates $0.00/month.
- **Cloud Scheduler** as the nightly trigger (3 free jobs per month).
- **Secret Manager** in an EU region for the service account key.
- **BigQuery** as the override layer and as the GA4 export destination for projects under one million events/day, with the dataset in `EU` location. 1 TiB of queries per month in Always Free.

**Reason for the confinement**: the GCP free tier requires an active billing account and provides **no hard spending cap** — budgets are alerts, not blocks. Cloudflare, Supabase and GitHub free tiers stop or throttle; Google keeps going and bills. With dozens of projects and automated nightly jobs, a loop or an unpartitioned BigQuery query produces an invoice, not an error.

**Mandatory rules when using GCP**: budget alerts configured on the billing account, BigQuery queries always filtered on the partition, per-service quotas manually lowered where possible.

---

## 4. Load-bearing principle: everything is configuration, nothing is hardcoded

This is the requirement to verify at every single step of the implementation. **If a future change requires touching the code, the design is wrong.**

Operating rules:

- **No list of metrics or dimensions written in code.** Queries, reports, charts and tables are defined as JSON stored in the control plane and loaded at runtime.
- **Extracted raw data is immutable.** Every transformation is a layer on top, recomputable and reversible. Without this rule, changing a metric definition forces re-running every backfill.
- **Derived metrics are text expressions evaluated at read time**, not in the ETL. Change the formula and the entire history updates instantly, with no re-extraction.
- **Connectors are plugins** behind a common interface. Adding Google Ads or Shopify means adding a file, not modifying the orchestrator.
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

This is where it touches the configurability principle: **config tables store multilingual content, not literal labels.** Two distinct mechanisms:

- **Static UI strings** (buttons, menus, messages) — one translation file per locale, handled with a standard i18n library. `en` is the reference file; `it` may be incomplete.
- **Analyst-authored content** (report titles, derived metric labels, legal texts, comments) — a per-locale JSONB field in the database, shaped like `{"en": "...", "it": "..."}`. **`en` is mandatory, `it` optional**, with explicit fallback to English when missing.

The comment engine therefore holds **templates per locale**, authored in English, and generates in the report language. If an Italian template is missing, it falls back to the English one rather than machine-translating: an automatically translated text about to be sent to a client is exactly the kind of dependency this plan rules out. If the analyst edits a comment, they edit that specific version.

### Data values are not translated

Values returned by GA4 — `Organic Search`, `Italy`, `mobile` — are data, not interface, and stay as the source delivers them. Optional **per-project label mappings** must nonetheless be available in configuration, for cases where an Italian client should see "Ricerca organica". A mapping, not an automatic translation: it stays an explicit analyst decision, consistent with the rest of the plan.

### Formatting

Numbers, dates and currencies must be formatted according to the active locale, not to a fixed format: comma decimal separator in Italian, period in English, different date formats. Handle it with the browser's native internationalisation APIs, never with hand-rolled formatting.

---

## 6. Data model

### Control plane / data plane separation

Reporting data **does not live in the database**. It lives on R2 as gzipped JSON files, one per project/source/report/period, rewritten every night.

Suggested R2 key:

```
{project_id}/{source}/{report_key}/{granularity}/{period}.json.gz
example: acme/ga4/channels_overview/daily/2026-08.json.gz
```

The frontend downloads the file for the selected period through a Worker that validates the Supabase JWT, then performs filtering and dimension/metric toggling **entirely locally in the browser**. No queries, no latency, no marginal cost. This is the mechanism that makes GA4-style interactivity sustainable at zero cost.

### Retention: current calendar year plus the two preceding ones

**Rule**: keep the current calendar year and the two before it. In December 2026 the oldest available data is January 2024; in January 2027 the window shifts and 2024 is removed.

The window therefore varies between 24 and 36 months depending on the point in the year, and that is deliberate: it is anchored to calendar-year boundaries, not to a rolling N months. The reason is YoY comparison — displaying a 12-month period with a previous-year line always requires 24 full months upstream of the oldest month shown, and anchoring to the calendar year guarantees that margin never disappears.

**Implementation**:

- Purge job separate from the ETL, scheduled **once a year on 1 February**, not 1 January. The month of slack exists because the December report is delivered in January and must still have complete comparisons.
- The purge removes R2 objects whose **data period** has a year lower than `current_year - 2`. Period partitioning in the R2 key makes this a list plus a delete by prefix.
- The window is a per-project parameter (`retention_calendar_years`, default 2), not a constant in the code: a client asking for more history is configured, not developed.
- The initial backfill is limited to the same window: no point extracting data that will be deleted.
- The nightly ETL never rewrites files outside the window.
- **The purge concerns the data plane only.** Comments, configuration, ETL logs and users are kept indefinitely: they are small, and comments are the analyst's work, not regenerable data.

**Recommended option (per project, opt-in)**: before deleting, save a monthly-granularity rollup of summary data only and keep it with no expiry. It takes a few dozen KB per project per year, does not affect any limit, and lets you answer a client asking for a five-year trend without having kept full daily detail.

### Sizing at 60 projects

With retention active, storage reaches a ceiling and stops growing.

| | Estimated usage | Free limit |
|---|---|---|
| R2 storage | 1.5–4.5 GB steady state, not cumulative | 10 GB |
| R2 writes | ~11,000/month | 1,000,000 |
| Supabase DB | 10–20 MB | 500 MB |
| Worker requests | 2–3k/day | 100,000/day |
| Cloud Run (ETL) | 15–35 CPU hours/month | 50 hours (180,000 vCPU-s) |

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

- Nightly cron, one job per project, parallelisable.
- **Never query GA4 from the frontend.** Quotas are per property: 200,000 tokens/day, 40,000/hour, 10 concurrent requests. With daily pre-aggregated extraction the problem does not arise.
- Initial backfill limited to the retention window (current year plus the two preceding), run as a separate manual workflow with rate limiting.
- **Cardinality**: high-cardinality reports (product name, landing page) must be stored at monthly grain with top-N plus an "Others" bucket. It is why the *Performance by Item Name* page of the current report errors out in Looker Studio.
- Every run writes an outcome record (`etl_runs`) with rows extracted, duration, errors. The admin panel surfaces it.

### Rolling re-extraction window

**Yesterday's GA4 data is not final.** Attribution settles over the following days and modelling is recomputed: an extraction that writes only the previous day and never touches it again produces a history that drifts progressively away from what the client sees in GA4.

Rule: every night, re-extract the **last 14 days** (per-project parameter), plus the current month at monthly grain. Writing to R2 is a full overwrite of the period file, so the operation is naturally idempotent and safely repeatable.

Consequence to keep in mind: a number already shown to a client may change within those 14 days. The exported PDF is therefore a dated snapshot, and must be stamped with generation date and time.

### Thresholding and the "(other)" row

Two GA4 mechanisms break totals and must be handled, not ignored:

- **Data thresholding**: with Google Signals active, GA4 hides low-volume rows to prevent user identification. The removed rows appear nowhere.
- **`(other)` row**: past cardinality limits, GA4 collapses the long tail into a single row.

Operating rule: **a total is never computed by summing the rows of a breakdown.** For every report, also extract the dimensionless query returning the true total and store it in the same file. The dashboard shows the true total and, when the rows do not sum up to it, explicitly exposes the difference as "unattributed" rather than letting the client discover on their own that the numbers do not reconcile.

### Timezone and currency

- Daily grain follows the **GA4 property timezone**, not the server's and not the browser's. Read it via the Admin API during onboarding and store it in `projects`: two properties of the same client may differ.
- Currency is the property's. Store the **currency code alongside the data** and never convert in the ETL: any conversion is a read-time derived metric, with rate and date made explicit.

### Modeled vs observed (confirmed requirement)

**Required feature, not optional.** The report must show sessions and revenue in both versions, with the gap between them.

The Data API does not return both: the Admin API (v1**alpha**) is needed to switch the property's reporting identity between `BLENDED` and `OBSERVED`. The constraint everything else follows from is that this is a **property-level change, not a query-level one**: during the switch window anyone reading that property — the client in GA4, a leftover Looker Studio report, other tools — sees different numbers.

Mandatory implementation requirements:

- **Atomic sequence per property**: read and record the initial identity, switch, run all of that property's queries, restore. Never switch multiple properties in parallel leaving windows open.
- **Guaranteed restore even on crash**: the restore goes in a `finally` block, and at the start of every run the ETL verifies that no property was left in the wrong state by the previous run. If it finds one, it restores and reports.
- **Narrowest possible nightly window**, with the identity switched only for the queries that need it, not for the property's entire extraction.
- **Per-project configurable resting identity**: the ETL restores the value the property actually had, not a default written in code.
- **Explicit fallback**: the API is alpha and can change without notice. If the switch fails, the ETL still extracts the resting version, flags the data as partial, and the report page states that the comparison is unavailable for that day instead of displaying a false gap.
- **Switch logging** in `etl_runs`: initial state, final state, restore outcome. It is what lets you answer the client who noticed different numbers in GA4 at three in the morning.

**Schema implication, to be honoured from Phase 1**: affected datasets must carry the identity variant as an attribute (`blended` / `observed`) in the R2 key and in the file schema, even before the feature is implemented. Adding it later would mean rewriting keys and redoing backfills.

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

1. **Exclusion rules (ETL)** — row-level filters from `exclusion_rules`. They produce a separate "excluded" file; they delete nothing.
2. **Derived metrics (read time)** — text expressions evaluated in the browser. This is where `valid_sessions` lives. Changeable retroactively without re-extraction.
3. **External overrides (ETL)** — a connector reading an external table with the fixed schema `project_id, date, dimension_key, metric_name, value` and merging it with precedence over GA4 data. Supports **Google Sheets** (free API) and **BigQuery** (free tier: 10 GB storage, 1 TB queries/month). It serves both to inject metrics computed elsewhere and to make targeted corrections: a month of broken tracking, a reclassified campaign.

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

Per-project isolation is implemented with **Row Level Security in Postgres** plus JWT validation in the Worker that serves R2 files. There must exist no path where the frontend requests an R2 file without going through the Worker.

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

Version 2 (optional): Puppeteer inside a Cloud Run Job in `europe-west1` to generate and archive the monthly PDF automatically on R2.

Print requirements: one report page per PDF page, header with project logo and period, comment always visible above the charts, no interactive element printed.

---

## 13. Observability, backup and QA

### ETL monitoring

An ETL that fails silently is discovered when a client asks why the data has stopped. Minimum requirements:

- **Alert on a failed or skipped run**, by email or webhook, naming the project and the error. A run that never starts must alert as loudly as one that errors: silence is the worst case.
- **Freshness indicator in the dashboard**: every page shows the date of the last successful update for that project. It is the first place the analyst looks when a number seems odd.
- **Anomaly thresholds on extracted volume**: if a project extracts 90% fewer rows than its recent median, the ETL reports instead of overwriting a good file with an empty one. Broken client-side tracking manifests exactly like this.
- **Quota consumption** logged per property, to catch saturation before it becomes an error.

### Backup

The data plane is regenerable by re-extracting from GA4, within the retention window. **The control plane is not**: configuration, metric dictionary, exclusion rules, and above all the comments edited by the analyst are non-reproducible work.

Requirement: **weekly dump of the configuration tables and comments to R2**, in a versionable text format. It takes a few MB, and the Supabase free plan offers no restore guarantee to rely on.

### QA

- **Reconciliation**: a script comparing extracted totals against a manual check in the GA4 interface, to be run in Phase 1 on a pilot project and on every query change. It is the only way to catch a dimension or timezone error before it reaches a client report.
- **Config validation**: at startup, the application verifies that every `report_defs` entry references metrics and dimensions actually present in the files. A config pointing at a non-existent field must fail loudly, not render an empty chart.
- **Snapshot tests on the comment engine**: given a fixed dataset, the generated text must be stable. It is what allows thresholds to be changed without discovering months later that one rule broke another.

---

## 14. Phases

| Phase | Deliverable | Customisability check |
|---|---|---|
| 0 | Working service account, config table schema, 1 pilot project | Adding a project is just an INSERT |
| 1 | GA4 ETL + R2 writes + backfill over the retention window + annual purge job + failed-run alerting + reconciliation script. **The file schema must already carry the reporting identity variant** | Adding a query is a `query_defs` record; changing retention or the re-extraction window is a `projects` field |
| 2 | Auth, roles, RLS, project switcher, admin panel | Creating a client user requires no deploy |
| 3 | Report pages, filters, dimension/metric toggles, **i18n groundwork with EN/IT locales** | Adding a page is a `report_defs` record; adding a language is a translation file |
| 4 | Derived metrics, external overrides, transformation panel, **modeled vs observed extraction via Admin API** | Changing `valid_sessions` requires no re-extraction; the resting identity is a `projects` field |
| 5 | Comment engine + PDF export | Changing a threshold is a `comment_rules` record |
| 6 | Multi-account overview, client onboarding, custom domain, complete `README.md` and in-app "Data & privacy" page | Legal texts are configuration entries, not code strings |

Sources other than GA4 are out of scope for now, but the connector interface must be defined in Phase 1 and validated by writing a dummy adapter.

---

## 15. Anti-patterns to avoid

- Querying GA4 from the frontend.
- Lists of metrics, dimensions or pages written in code.
- `localStorage` or `sessionStorage`.
- Overwriting raw data with transformed data.
- A single flat schema for all sources.
- High-cardinality reports at daily grain.
- Retention implemented with R2 lifecycle rules based on object age: files are rewritten every night, so object age bears no relation to the period of the data inside. Deletion must be decided on the period, never on file age.
- Deploying on Vercel.
- Using an R2 location hint (`weur`, `eeur`) believing it guarantees EU residency: it is best effort; only the `eu` jurisdiction is a guarantee.
- Creating an R2 bucket, Supabase project or BigQuery dataset without pinning the location: these settings are immutable, and the mistake is only fixed by recreating and migrating.
- Direct access to R2 files without JWT validation.
- Storing a rate or an average without numerator and denominator: it makes correct recomputation after filtering impossible.
- Computing a total by summing the rows of a breakdown: thresholding and the `(other)` row make it systematically wrong.
- Extracting only the previous day and never revisiting it: GA4 data settles over subsequent days.
- Comparing a partial period against a complete one without declaring it.
- User-facing strings written in code instead of translation files: an automated check must catch them.
- Identifiers, logs, code comments or documentation in Italian.
- Literal labels stored in config tables instead of multilingual content.
- Machine-translating comments or source data values.

---

## 16. Required repository documentation

The repository must contain a final `README.md`, **written in English**, produced at the end of the implementation, with at least these sections:

1. **Architecture** — block diagram and data flow from API to dashboard.
2. **Setup from scratch** — resource creation, with localisation settings flagged as irreversible.
3. **Onboarding a new project** — full procedure, including adding the service account to the GA4 property.
4. **Configuration** — a description of every config table and what changing it achieves, with examples. This is the section that makes the customisability principle real: if a change is not documented here, it is not configurable.
5. **Derived metrics and exclusion rules** — expression syntax and the semantics of the `valid_sessions` metric.
6. **Metric dictionary** — how to update it and why validity dates are mandatory.
7. **Operations** — how to re-run a failed ETL, how to run a backfill, where to read the logs.
8. **Retention** — active window, annual purge date, what is deleted and what is not.
9. **Data residency and provider jurisdiction** — text below.
10. **Known limits** — free-tier quotas, saturation thresholds, alpha APIs in use.

### Disclaimer text

Needed in two versions: **English in `README.md`** — the canonical version — and **English plus Italian as a configuration entry** for the application's "Data & privacy" page and the PDF footer, served according to the report language.

**English version (canonical, for `README.md` and the app):**

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

**Italian version (display only, for Italian-language reports):**

> **Residenza dei dati e giurisdizione del fornitore**
>
> Tutti i dati trattati da questo strumento sono archiviati esclusivamente all'interno dell'Unione Europea:
> - dati di reporting su Cloudflare R2, bucket con jurisdiction `eu` (pinning ai data center di stati membri UE, nessuna replica verso il Nord America);
> - utenti, configurazioni e commenti su Supabase, region `eu-central-1` (Francoforte);
> - elaborazione ETL su Google Cloud Run, region `europe-west1`;
> - credenziali su Google Secret Manager con replica in region UE.
>
> I dati di reporting archiviati sono **aggregati statistici** (sessioni per canale, ricavi per paese, prodotti per categoria) e non contengono identificatori individuali, client ID, user ID o eventi a livello di singolo utente. Gli unici dati personali trattati dallo strumento sono gli indirizzi email degli utenti abilitati all'accesso.
>
> **Limite noto.** I fornitori infrastrutturali impiegati — Cloudflare, Inc. e Google LLC — sono società di diritto statunitense e in quanto tali soggette al CLOUD Act, anche quando i dati risiedono fisicamente nell'Unione Europea. Lo strumento soddisfa pertanto il requisito di **residenza del dato**, ma non un eventuale requisito contrattuale di trattamento da parte di un responsabile stabilito esclusivamente nell'UE. Qualora un cliente ponga questo vincolo, i componenti di archiviazione ed elaborazione vanno migrati su fornitori europei (per esempio Scaleway, OVHcloud, Hetzner, Exoscale), con un impatto sui costi operativi.
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

- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits)
- [Cloudflare Workers pricing](https://developers.cloudflare.com/workers/about/pricing)
- [R2 — data location and jurisdictions](https://developers.cloudflare.com/r2/reference/data-location/)
- [Cloudflare Data Localization Suite — R2](https://developers.cloudflare.com/data-localization/how-to/r2/)
- [Supabase pricing](https://supabase.com/pricing)
- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [GA4 Data API — quotas](https://developers.google.com/analytics/devguides/reporting/data/v1/quotas)
- [GA4 Data API — dimensions and metrics schema](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema)
- [GA4 Admin API — reporting identity](https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1alpha/properties/getReportingIdentitySettings)
- [GA4 — engaged sessions](https://support.google.com/analytics/answer/12195621)
- [GA4 — BigQuery export limits](https://support.google.com/analytics/answer/9823238)
- [Service accounts for the Google Analytics APIs](https://developers.google.com/analytics/devguides/reporting/data/v1/quickstart-client-libraries)
- [Cloud Run pricing and free tier](https://cloud.google.com/run/pricing)
- [Google Cloud Always Free](https://cloud.google.com/free/docs/free-cloud-features)
- [BigQuery free tier](https://cloud.google.com/bigquery/pricing#free-tier)
- [Workload Identity Federation from GitHub Actions](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)