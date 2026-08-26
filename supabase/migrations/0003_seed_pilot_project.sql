-- Phase 0 pilot project, wired to the dummy connector so the full pipeline
-- (config -> ETL -> GCS -> frontend) can be exercised before any real GA4
-- credentials exist. See etl/src/reporting_etl/connectors/dummy.py.

insert into projects (
  slug, display_name, report_language, timezone, currency_code,
  hostname_allowlist, retention_calendar_years, reextraction_window_days,
  resting_reporting_identity
) values (
  'pilot', 'Pilot Project', 'en', 'Europe/Rome', 'EUR',
  array['pilot.example.com'], 2, 14, 'blended'
);

insert into connections (project_id, source, resource_id, metadata)
select id, 'dummy', 'dummy-resource', '{"note": "reference implementation of the connector interface"}'::jsonb
from projects where slug = 'pilot';

insert into query_defs (project_id, source, report_key, dimensions, metrics, granularity)
select id, 'dummy', 'channels_overview',
       array['date', 'source_medium'],
       array['sessions', 'engaged_sessions', 'conversions'],
       'daily'
from projects where slug = 'pilot';

insert into report_defs (project_id, page_key, title, order_index, layout)
select id, 'overview',
       '{"en": "Overview", "it": "Panoramica"}'::jsonb,
       0,
       '[{"type": "chart", "dataset": "channels_overview", "metric": "sessions"}]'::jsonb
from projects where slug = 'pilot';

-- Global metric dictionary entries used by the pilot dataset. engagement_rate's
-- numerator_key/denominator_key must be set in the same INSERT, not a follow-up
-- UPDATE — the additivity='ratio' check constraint requires both non-null at
-- insert time.
insert into metric_dictionary (metric_key, additivity, unit, description, valid_from, numerator_key, denominator_key)
values
  ('sessions', 'sum', 'count', '{"en": "GA4 sessions, unfiltered.", "it": "Sessioni GA4, non filtrate."}'::jsonb, '1970-01-01', null, null),
  ('engaged_sessions', 'sum', 'count', '{"en": "Sessions meeting the GA4 engagement definition.", "it": "Sessioni che soddisfano la definizione di coinvolgimento di GA4."}'::jsonb, '1970-01-01', null, null),
  ('conversions', 'sum', 'count', '{"en": "Key event count.", "it": "Numero di eventi chiave."}'::jsonb, '1970-01-01', null, null),
  ('engagement_rate', 'ratio', 'percent', '{"en": "engaged_sessions / sessions.", "it": "engaged_sessions / sessions."}'::jsonb, '1970-01-01', 'engaged_sessions', 'sessions');

insert into derived_metrics (project_id, metric_key, label, expression, unit)
select null, 'engagement_rate', '{"en": "Engagement rate", "it": "Tasso di coinvolgimento"}'::jsonb,
       'engaged_sessions / sessions', 'percent';
