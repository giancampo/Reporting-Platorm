-- Control-plane schema. Reporting data itself never lives here (see README.md
-- §1 "Architecture"); these tables hold configuration, credentials metadata,
-- and analyst-authored content only. action-plan.md §4 and §6 are the source
-- of truth for the table list and its rationale.

create extension if not exists "pgcrypto";

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- ---------------------------------------------------------------------------
-- projects: one row per client/website. Branding, locale and retention are
-- per-project parameters, never constants in code (action-plan.md §4, §6).
-- ---------------------------------------------------------------------------
create table projects (
  id                       uuid primary key default gen_random_uuid(),
  slug                     text not null unique,                 -- used as the GCS object key prefix
  display_name             text not null,
  report_language          text not null default 'en',           -- drives comment/PDF language, §5
  timezone                 text not null,                        -- GA4 property timezone, §7
  currency_code            text not null,                        -- ISO 4217, stored alongside data, §7
  logo_url                 text,
  brand_primary_color      text,
  brand_secondary_color    text,
  hostname_allowlist       text[] not null default '{}',         -- bot filter layer 2, §8
  retention_calendar_years int not null default 2,                -- §6
  reextraction_window_days int not null default 14,                -- §7 rolling re-extraction
  resting_reporting_identity text not null default 'blended'
    check (resting_reporting_identity in ('blended', 'observed')), -- §7 modeled vs observed
  archive_summary_on_purge boolean not null default false,        -- §6 optional rollup before delete
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

comment on table projects is 'One row per client/project. Every per-client parameter lives here, never in code.';

-- ---------------------------------------------------------------------------
-- connections: credentials/resource identifiers per source. A project can have
-- N connections (multiple GA4 properties, Google Ads accounts, etc).
-- ---------------------------------------------------------------------------
create table connections (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid not null references projects(id) on delete cascade,
  source            text not null,                 -- e.g. 'ga4', 'google_ads', 'shopify', 'dummy'
  resource_id       text not null,                  -- e.g. GA4 property id
  secret_ref        text,                           -- pointer into Secret Manager, never the secret itself
  is_active         boolean not null default true,
  metadata          jsonb not null default '{}'::jsonb,
  created_at        timestamptz not null default now(),
  unique (project_id, source, resource_id)
);

-- ---------------------------------------------------------------------------
-- query_defs: extraction query definitions. Adding a query is an INSERT, not
-- a code change (action-plan.md §4, §14).
-- ---------------------------------------------------------------------------
create table query_defs (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid references projects(id) on delete cascade, -- null = applies to all projects
  source            text not null,
  report_key        text not null,                 -- e.g. 'channels_overview'
  dimensions        text[] not null default '{}',  -- canonical dimension names
  metrics           text[] not null default '{}',  -- canonical metric names
  granularity       text not null default 'daily' check (granularity in ('daily', 'monthly')),
  high_cardinality  boolean not null default false, -- forces monthly grain + top-N bucketing, §7
  top_n             int not null default 50,
  is_active         boolean not null default true,
  created_at        timestamptz not null default now(),
  unique (project_id, source, report_key)
);

-- ---------------------------------------------------------------------------
-- report_defs: page structure. Adding a page is a record (§14).
-- ---------------------------------------------------------------------------
create table report_defs (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid references projects(id) on delete cascade, -- null = shared template
  page_key          text not null,
  title             jsonb not null,                -- {"en": "...", "it": "..."}, en mandatory (§5)
  order_index       int not null default 0,
  layout            jsonb not null default '[]'::jsonb, -- ordered list of block definitions
  is_active         boolean not null default true,
  created_at        timestamptz not null default now(),
  unique (project_id, page_key)
);

-- ---------------------------------------------------------------------------
-- derived_metrics: computed metrics as text expressions, evaluated at read
-- time in the browser (§4, §9). Never in the ETL.
-- ---------------------------------------------------------------------------
create table derived_metrics (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid references projects(id) on delete cascade, -- null = global
  metric_key        text not null,
  label             jsonb not null,                -- {"en": "...", "it": "..."}
  expression        text not null,                 -- e.g. "engaged_sessions / sessions"
  unit              text,
  created_at        timestamptz not null default now(),
  unique (project_id, metric_key)
);

-- ---------------------------------------------------------------------------
-- exclusion_rules: row-level filters applied in the ETL. Non-destructive:
-- excluded rows are written to a separate file, never deleted (§9).
-- ---------------------------------------------------------------------------
create table exclusion_rules (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid not null references projects(id) on delete cascade,
  source            text not null,
  description       text not null,
  filter_expression text not null,                 -- evaluated against a canonical row
  is_active         boolean not null default true,
  created_at        timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- metric_dictionary: canonical name, semantics, unit, additivity, validity
-- dates. Load-bearing for both the aggregation engine and the comment engine
-- (§6, §9, §13).
-- ---------------------------------------------------------------------------
create table metric_dictionary (
  id                uuid primary key default gen_random_uuid(),
  metric_key        text not null,
  additivity        text not null check (additivity in ('sum', 'ratio', 'unique')),
  unit              text,
  description       jsonb not null,                -- {"en": "...", "it": "..."}
  numerator_key     text,                           -- required when additivity = 'ratio'
  denominator_key   text,                           -- required when additivity = 'ratio'
  valid_from        date not null default '1970-01-01',
  valid_to          date,                            -- null = still valid
  created_at        timestamptz not null default now(),
  check (
    additivity <> 'ratio' or (numerator_key is not null and denominator_key is not null)
  )
);

create index metric_dictionary_key_validity_idx
  on metric_dictionary (metric_key, valid_from, valid_to);

-- ---------------------------------------------------------------------------
-- comment_rules: thresholds, priorities, text templates for the deterministic
-- comment engine (§11). No LLM, no hand-written functions.
-- ---------------------------------------------------------------------------
create table comment_rules (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid references projects(id) on delete cascade, -- null = global default
  rule_key          text not null,
  metric_key        text not null,
  condition         jsonb not null,                -- e.g. {"op": "abs_pct_change_gt", "value": 0.30}
  priority          int not null default 100,
  templates         jsonb not null,                -- {"en": ["variant 1", "variant 2", ...], "it": [...]}
  is_active         boolean not null default true,
  created_at        timestamptz not null default now(),
  unique (project_id, rule_key)
);

-- ---------------------------------------------------------------------------
-- users / project_users: roles and project assignment (§10).
-- users mirrors auth.users by id; kept as an explicit table so profile data
-- (UI language preference, display name) doesn't live on the auth schema.
-- ---------------------------------------------------------------------------
create table users (
  id                uuid primary key references auth.users(id) on delete cascade,
  email             text not null,
  display_name      text,
  ui_language       text not null default 'en',
  global_role       text not null default 'client' check (global_role in ('admin', 'analyst', 'client')),
  created_at        timestamptz not null default now()
);

create table project_users (
  project_id        uuid not null references projects(id) on delete cascade,
  user_id           uuid not null references users(id) on delete cascade,
  role              text not null check (role in ('admin', 'analyst', 'client')),
  created_at        timestamptz not null default now(),
  primary key (project_id, user_id)
);

-- Mirrors every new auth.users row into public.users automatically. Without
-- this, an admin inviting a user (action-plan.md §14 Phase 2: "Creating a
-- client user requires no deploy") would create an auth.users row with no
-- corresponding public.users row, and every RLS check in
-- 0002_rls_policies.sql keys off public.users — the invited user would be
-- silently locked out of everything until someone noticed and inserted the
-- row by hand.
create or replace function handle_new_auth_user()
returns trigger as $$
begin
  insert into public.users (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$ language plpgsql security definer set search_path = public;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_auth_user();

-- ---------------------------------------------------------------------------
-- comments: generated and edited comments, draft/approved, versioned (§11).
-- ---------------------------------------------------------------------------
create table comments (
  id                uuid primary key default gen_random_uuid(),
  project_id        uuid not null references projects(id) on delete cascade,
  page_key          text not null,
  period            text not null,                 -- e.g. '2026-07'
  locale            text not null default 'en',
  status            text not null default 'draft' check (status in ('draft', 'approved')),
  generated_text    text,                           -- rules-engine output, kept for history
  edited_text       text,                           -- analyst override, supersedes generated_text
  version           int not null default 1,
  created_by        uuid references users(id),
  created_at        timestamptz not null default now()
);

create index comments_project_page_period_idx on comments (project_id, page_key, period);

-- ---------------------------------------------------------------------------
-- etl_runs: outcome record per run, surfaced in the admin panel (§7, §13).
-- ---------------------------------------------------------------------------
create table etl_runs (
  id                       uuid primary key default gen_random_uuid(),
  project_id               uuid not null references projects(id) on delete cascade,
  source                   text not null,
  started_at               timestamptz not null default now(),
  finished_at              timestamptz,
  status                   text not null default 'running'
    check (status in ('running', 'success', 'partial', 'failed', 'skipped')),
  rows_extracted           int,
  error_message            text,
  reporting_identity_initial text check (reporting_identity_initial in ('blended', 'observed')),
  reporting_identity_final   text check (reporting_identity_final in ('blended', 'observed')),
  identity_restore_ok      boolean
);

create index etl_runs_project_started_idx on etl_runs (project_id, started_at desc);

create trigger set_projects_updated_at
  before update on projects
  for each row execute function set_updated_at();
