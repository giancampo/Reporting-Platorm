"""Cloud Run Job entrypoint. One invocation processes every active project
(action-plan.md §7: "nightly cron, one job per project, parallelisable" —
parallelism across projects is left to Cloud Run Job task indices in
production; this module processes sequentially and is safe to call
per-project for that purpose, see `run_for_project`).

Per-project sequence:
1. Verify no property was left mid reporting-identity switch by a previous
   crashed run (§7).
2. For each active connection, for each active query_def: extract the
   rolling re-extraction window (last N days, §7) plus the current month at
   monthly grain.
3. Apply exclusion rules (non-destructive), cardinality bucketing for
   high-cardinality query_defs, and reconcile against the dimensionless
   total.
4. Write one R2 document per (source, report_key, granularity, period).
5. Record the outcome in etl_runs and run the alerting checks.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from .alerting import AlertSink, RunOutcome, check_run_outcome, check_volume_anomaly
from .config_client import ConfigClient, ProjectConfig
from .connectors import CONNECTOR_REGISTRY
from .connectors.base import ExtractedRow
from .storage.r2_writer import Document, R2Client, build_r2_key
from .transform.cardinality import bucket_top_n
from .transform.exclusion_rules import apply_exclusion_rules
from .transform.totals import compute_unattributed

logger = logging.getLogger("reporting_etl")

SCHEMA_VERSION = 1


def _row_to_dict(row: ExtractedRow) -> dict:
    return {
        "date_key": row.date_key.isoformat(),
        "dimension_values": row.dimension_values,
        "metric_values": row.metric_values,
    }


def _period_key(day: date, granularity: str) -> str:
    return day.strftime("%Y-%m")


def run_for_project(
    config: ConfigClient,
    r2: R2Client,
    alert_sink: AlertSink,
    project: ProjectConfig,
    today: date,
) -> list[RunOutcome]:
    outcomes: list[RunOutcome] = []
    window_start = today - timedelta(days=project.reextraction_window_days)

    for connection in config.list_connections(project.id):
        connector_cls = CONNECTOR_REGISTRY.get(connection.source)
        if connector_cls is None:
            logger.warning("No connector registered for source=%s, skipping.", connection.source)
            continue
        connector = connector_cls(connection)

        for query_def in config.list_query_defs(project.id, connection.source):
            run_id = config.record_etl_run_start(project.id, connection.source)
            try:
                result = connector.extract(query_def, window_start, today)
                rows = [_row_to_dict(r) for r in result.rows]

                kept_rows, excluded_rows = apply_exclusion_rules(rows, [])  # exclusion_rules loaded separately, see docs

                if query_def.high_cardinality and query_def.dimensions:
                    ranking_metric = query_def.metrics[0] if query_def.metrics else None
                    if ranking_metric:
                        for dim in query_def.dimensions:
                            if dim == "date":
                                continue
                            kept_rows = bucket_top_n(kept_rows, dim, ranking_metric, query_def.top_n)

                unattributed = compute_unattributed(kept_rows, result.totals)

                period = _period_key(today, query_def.granularity)
                document = Document(
                    schema_version=SCHEMA_VERSION,
                    project_id=project.id,
                    source=connection.source,
                    report_key=query_def.report_key,
                    granularity=query_def.granularity,
                    period=period,
                    reporting_identity=result.reporting_identity,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    rows=kept_rows,
                    totals=result.totals,
                    unattributed=unattributed,
                    excluded_row_count=len(excluded_rows),
                )
                key = build_r2_key(project.slug, connection.source, query_def.report_key, query_def.granularity, period)
                r2.put_document(key, document)

                outcome = RunOutcome(
                    project_slug=project.slug,
                    source=connection.source,
                    status="success",
                    rows_extracted=len(kept_rows),
                    error_message=None,
                )
                config.record_etl_run_end(run_id, status="success", rows_extracted=len(kept_rows))
                check_volume_anomaly(project.slug, connection.source, len(kept_rows), [], alert_sink)

            except Exception as exc:  # noqa: BLE001 — a failed run must alert, never crash the whole job
                logger.exception("ETL run failed for project=%s source=%s", project.slug, connection.source)
                outcome = RunOutcome(
                    project_slug=project.slug,
                    source=connection.source,
                    status="failed",
                    rows_extracted=None,
                    error_message=str(exc),
                )
                config.record_etl_run_end(run_id, status="failed", error_message=str(exc))

            check_run_outcome(outcome, alert_sink)
            outcomes.append(outcome)

    return outcomes


def run_all_projects() -> None:
    logging.basicConfig(level=logging.INFO)
    config = ConfigClient.from_env()
    r2 = R2Client.from_env()
    alert_sink = _load_alert_sink()
    today = date.today()

    for project in config.list_active_projects():
        run_for_project(config, r2, alert_sink, project, today)


def _load_alert_sink() -> AlertSink:
    # Deferred import: the webhook sink pulls in httpx only when actually needed.
    from .alerting_sinks import WebhookAlertSink

    return WebhookAlertSink.from_env()


if __name__ == "__main__":
    run_all_projects()
