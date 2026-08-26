"""Reference implementation of the Connector interface (action-plan.md §14:
"the connector interface must be defined in Phase 1 and validated by writing
a dummy adapter"). Generates deterministic synthetic rows so the rest of the
pipeline — canonical transforms, R2 writer, frontend — can be exercised
end-to-end without any live source credentials."""

from __future__ import annotations

from datetime import date, timedelta

from .base import Connection, Connector, ExtractedRow, ExtractionResult, QueryDef

_SOURCE_MEDIUMS = ["google / organic", "google / cpc", "direct / (none)", "newsletter / email"]


class DummyConnector(Connector):
    def __init__(self, connection: Connection) -> None:
        super().__init__(connection)

    def extract(self, query_def: QueryDef, start: date, end: date) -> ExtractionResult:
        rows: list[ExtractedRow] = []
        totals = {metric: 0.0 for metric in query_def.metrics}

        day = start
        while day <= end:
            for i, source_medium in enumerate(_SOURCE_MEDIUMS):
                seed = day.toordinal() + i
                sessions = float(50 + (seed % 40))
                engaged = round(sessions * 0.6, 1)
                conversions = float(seed % 5)

                metric_values: dict[str, float] = {}
                if "sessions" in query_def.metrics:
                    metric_values["sessions"] = sessions
                if "engaged_sessions" in query_def.metrics:
                    metric_values["engaged_sessions"] = engaged
                if "conversions" in query_def.metrics:
                    metric_values["conversions"] = conversions

                dimension_values: dict[str, str] = {}
                if "date" in query_def.dimensions:
                    dimension_values["date"] = day.isoformat()
                if "source_medium" in query_def.dimensions:
                    dimension_values["source_medium"] = source_medium

                rows.append(
                    ExtractedRow(
                        date_key=day,
                        dimension_values=dimension_values,
                        metric_values=metric_values,
                    )
                )
                for key, value in metric_values.items():
                    totals[key] = totals.get(key, 0.0) + value

            day += timedelta(days=1)

        return ExtractionResult(rows=rows, totals=totals, reporting_identity=None)
