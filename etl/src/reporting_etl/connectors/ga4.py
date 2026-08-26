"""GA4 Data API connector (action-plan.md §7).

Uses the Data API (v1beta) for metrics/dimensions and, when the query
requires a reporting-identity comparison, relies on `identity_switch.py`
having already put the property into the desired state before `extract()`
is called — this connector never switches identity itself, keeping the
atomic switch/restore sequence centralised (§7's "atomic sequence per
property" requirement would be violated if every connector could trigger
its own switch).

Requires `GOOGLE_APPLICATION_CREDENTIALS` (or the connection's `secret_ref`
resolved to a service-account key by the caller) to actually run — this
module is safe to import and unit-test without any credentials present.
"""

from __future__ import annotations

from datetime import date

from ..transform.canonical import to_canonical_dimension, to_canonical_metric, to_ga4_dimension, to_ga4_metric
from .base import Connection, Connector, ExtractedRow, ExtractionResult, QueryDef


class GA4Connector(Connector):
    def __init__(self, connection: Connection) -> None:
        super().__init__(connection)
        self._property_id = connection.resource_id

    def supports_identity_switch(self) -> bool:
        return True

    def extract(self, query_def: QueryDef, start: date, end: date) -> ExtractionResult:
        # Deferred import: the google-analytics-data client pulls in gRPC/auth
        # machinery that isn't needed (or installable without credentials) for
        # unit tests exercising the connector interface via DummyConnector.
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            RunReportRequest,
        )

        client = BetaAnalyticsDataClient()
        ga4_dimensions = [to_ga4_dimension(d) for d in query_def.dimensions if d != "date"]
        ga4_metrics = [to_ga4_metric(m) for m in query_def.metrics]

        breakdown_request = RunReportRequest(
            property=f"properties/{self._property_id}",
            date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
            dimensions=[Dimension(name="date")] + [Dimension(name=d) for d in ga4_dimensions],
            metrics=[Metric(name=m) for m in ga4_metrics],
            limit=250000 if query_def.high_cardinality else 100000,
        )
        breakdown = client.run_report(breakdown_request)
        rows = self._parse_rows(breakdown, query_def)

        # Dimensionless total, per the "never sum a breakdown" rule (§7, §9):
        # thresholding and the (other) row make a summed breakdown unreliable.
        totals_request = RunReportRequest(
            property=f"properties/{self._property_id}",
            date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
            metrics=[Metric(name=m) for m in ga4_metrics],
        )
        totals_response = client.run_report(totals_request)
        totals = self._parse_totals(totals_response, query_def)

        return ExtractionResult(rows=rows, totals=totals, reporting_identity=None)

    def _parse_rows(self, response, query_def: QueryDef) -> list[ExtractedRow]:
        dimension_headers = [h.name for h in response.dimension_headers]
        metric_headers = [h.name for h in response.metric_headers]

        rows: list[ExtractedRow] = []
        for api_row in response.rows:
            dim_values = {
                to_canonical_dimension(name) if name != "date" else "date": value.value
                for name, value in zip(dimension_headers, api_row.dimension_values)
            }
            date_str = dim_values.pop("date")
            metric_values = {
                to_canonical_metric(name): float(value.value)
                for name, value in zip(metric_headers, api_row.metric_values)
            }
            rows.append(
                ExtractedRow(
                    date_key=date.fromisoformat(date_str),
                    dimension_values=dim_values,
                    metric_values=metric_values,
                )
            )
        return rows

    def _parse_totals(self, response, query_def: QueryDef) -> dict[str, float] | None:
        if not response.rows:
            return None
        metric_headers = [h.name for h in response.metric_headers]
        totals_row = response.rows[0]
        return {
            to_canonical_metric(name): float(value.value)
            for name, value in zip(metric_headers, totals_row.metric_values)
        }
