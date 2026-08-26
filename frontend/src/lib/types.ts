/** Shapes shared across the frontend. Mirrors, on the R2-document side, the
 * `Document` dataclass in etl/src/reporting_etl/storage/r2_writer.py, and on
 * the config side, the tables in supabase/migrations/0001_config_tables.sql.
 * Keep both in sync by hand — there is no code generation step yet (a
 * follow-up would generate this from the SQL/Python, not duplicate by hand
 * forever). */

export type Additivity = "sum" | "ratio" | "unique";

export interface MetricDictionaryEntry {
  metric_key: string;
  additivity: Additivity;
  unit: string | null;
  numerator_key: string | null;
  denominator_key: string | null;
  valid_from: string; // ISO date
  valid_to: string | null;
}

export interface LocalizedText {
  en: string;
  it?: string;
}

export interface ReportRow {
  date_key: string;
  dimension_values: Record<string, string>;
  metric_values: Record<string, number>;
}

export interface ReportDocument {
  schema_version: number;
  project_id: string;
  source: string;
  report_key: string;
  granularity: "daily" | "monthly";
  period: string;
  reporting_identity: "blended" | "observed" | null;
  generated_at: string; // ISO 8601 UTC — drives the freshness indicator (action-plan.md §13)
  rows: ReportRow[];
  totals: Record<string, number> | null;
  unattributed: Record<string, number> | null;
  excluded_row_count: number;
}

export interface DerivedMetricDef {
  metric_key: string;
  label: LocalizedText;
  expression: string;
  unit: string | null;
}
