-- Per-project isolation via RLS (action-plan.md §10). No frontend path is ever
-- allowed to bypass these policies; the Cloud Run signing service also
-- validates the JWT and re-checks project access before issuing a signed
-- URL, but that is a second, independent gate, not a substitute.

alter table projects            enable row level security;
alter table connections         enable row level security;
alter table query_defs          enable row level security;
alter table report_defs         enable row level security;
alter table derived_metrics     enable row level security;
alter table exclusion_rules     enable row level security;
alter table metric_dictionary   enable row level security;
alter table comment_rules       enable row level security;
alter table users                enable row level security;
alter table project_users       enable row level security;
alter table comments            enable row level security;
alter table etl_runs            enable row level security;

-- Helper: is the current user a global admin?
create or replace function is_global_admin()
returns boolean as $$
  select exists (
    select 1 from users where id = auth.uid() and global_role = 'admin'
  );
$$ language sql stable security definer set search_path = public;

-- Helper: does the current user have at least `role` on `p_project_id`?
-- Role ordering for this check: admin > analyst > client.
create or replace function has_project_role(p_project_id uuid, p_min_role text)
returns boolean as $$
  select is_global_admin() or exists (
    select 1 from project_users pu
    where pu.project_id = p_project_id
      and pu.user_id = auth.uid()
      and (
        p_min_role = 'client'
        or (p_min_role = 'analyst' and pu.role in ('analyst', 'admin'))
        or (p_min_role = 'admin' and pu.role = 'admin')
      )
  );
$$ language sql stable security definer set search_path = public;

-- users: everyone can read their own row; admins can read/write all.
create policy users_select_self on users for select using (id = auth.uid() or is_global_admin());
create policy users_update_self on users for update using (id = auth.uid() or is_global_admin());
create policy users_admin_all on users for all using (is_global_admin());

-- project_users: readable by project members and admins; writable by admins only.
create policy project_users_select on project_users for select
  using (user_id = auth.uid() or has_project_role(project_id, 'client'));
create policy project_users_admin_write on project_users for all
  using (is_global_admin()) with check (is_global_admin());

-- projects: readable by any assigned member (client and up); writable by admins.
create policy projects_select on projects for select
  using (has_project_role(id, 'client'));
create policy projects_admin_write on projects for all
  using (is_global_admin()) with check (is_global_admin());

-- connections / query_defs / exclusion_rules: analyst+ only, never exposed to clients
-- (they may reference credentials metadata or filter logic clients shouldn't see).
create policy connections_analyst_read on connections for select
  using (has_project_role(project_id, 'analyst'));
create policy connections_admin_write on connections for all
  using (is_global_admin()) with check (is_global_admin());

create policy query_defs_analyst_read on query_defs for select
  using (project_id is null or has_project_role(project_id, 'analyst'));
create policy query_defs_admin_write on query_defs for all
  using (is_global_admin()) with check (is_global_admin());

create policy exclusion_rules_analyst_read on exclusion_rules for select
  using (has_project_role(project_id, 'analyst'));
create policy exclusion_rules_analyst_write on exclusion_rules for all
  using (has_project_role(project_id, 'analyst')) with check (has_project_role(project_id, 'analyst'));

-- report_defs / derived_metrics / comment_rules / metric_dictionary: readable
-- by any project member (they drive what the client sees), writable analyst+.
create policy report_defs_select on report_defs for select
  using (project_id is null or has_project_role(project_id, 'client'));
create policy report_defs_analyst_write on report_defs for all
  using (project_id is null or has_project_role(project_id, 'analyst'))
  with check (project_id is null or has_project_role(project_id, 'analyst'));

create policy derived_metrics_select on derived_metrics for select
  using (project_id is null or has_project_role(project_id, 'client'));
create policy derived_metrics_analyst_write on derived_metrics for all
  using (project_id is null or has_project_role(project_id, 'analyst'))
  with check (project_id is null or has_project_role(project_id, 'analyst'));

create policy comment_rules_select on comment_rules for select
  using (project_id is null or has_project_role(project_id, 'analyst'));
create policy comment_rules_analyst_write on comment_rules for all
  using (project_id is null or has_project_role(project_id, 'analyst'))
  with check (project_id is null or has_project_role(project_id, 'analyst'));

create policy metric_dictionary_select on metric_dictionary for select using (true);
create policy metric_dictionary_admin_write on metric_dictionary for all
  using (is_global_admin()) with check (is_global_admin());

-- comments: readable by any project member; editable analyst+; clients read-only.
create policy comments_select on comments for select
  using (has_project_role(project_id, 'client'));
create policy comments_analyst_write on comments for all
  using (has_project_role(project_id, 'analyst')) with check (has_project_role(project_id, 'analyst'));

-- etl_runs: analyst+ only (operational detail, not client-facing).
create policy etl_runs_analyst_read on etl_runs for select
  using (has_project_role(project_id, 'analyst'));
create policy etl_runs_service_write on etl_runs for all
  using (is_global_admin()) with check (is_global_admin());
