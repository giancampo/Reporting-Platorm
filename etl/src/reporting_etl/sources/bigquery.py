"""BigQuery override source (action-plan.md §9). Reads a table with the same
fixed schema as the Sheets backend: `project_id, date, dimension_key,
metric_name, value`. The dataset MUST be created in the `EU` location
(action-plan.md §3 — immutable once created); queries must filter on the
partition column (`date`) per §3's mandatory-rules-when-using-GCP."""

from __future__ import annotations

from datetime import date

from ..overrides import OverrideRow


class BigQueryOverrideSource:
    def __init__(self, table_fqn: str) -> None:
        # e.g. "my-gcp-project.reporting_overrides.overrides"
        self._table_fqn = table_fqn

    def fetch(self, project_id: str, start: date, end: date) -> list[OverrideRow]:
        from google.cloud import bigquery  # deferred: no network/creds needed to import this module

        client = bigquery.Client()
        query = f"""
            SELECT project_id, date, dimension_key, metric_name, value
            FROM `{self._table_fqn}`
            WHERE project_id = @project_id
              AND date BETWEEN @start AND @end
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("project_id", "STRING", project_id),
                bigquery.ScalarQueryParameter("start", "DATE", start.isoformat()),
                bigquery.ScalarQueryParameter("end", "DATE", end.isoformat()),
            ]
        )
        rows = client.query(query, job_config=job_config).result()
        return [
            OverrideRow(
                project_id=row.project_id,
                date=row.date,
                dimension_key=row.dimension_key,
                metric_name=row.metric_name,
                value=float(row.value),
            )
            for row in rows
        ]
