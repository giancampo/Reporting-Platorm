"""External overrides (action-plan.md §9, layer 3 of the transformation
stack: override > derived > raw).

Reads from an external source with the FIXED schema
`project_id, date, dimension_key, metric_name, value` and merges it over the
extracted rows with precedence — used both to inject metrics computed
elsewhere and to make targeted corrections (a month of broken tracking, a
reclassified campaign). Two backends share this schema: Google Sheets (free
API) and BigQuery (free tier). Adding a third backend means adding a
function that returns `list[OverrideRow]` in this shape, not touching the
merge logic below.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class OverrideRow:
    project_id: str
    date: date
    dimension_key: str  # e.g. "source_medium=google / organic", or "" for a dimensionless override
    metric_name: str
    value: float


class OverrideSource(Protocol):
    def fetch(self, project_id: str, start: date, end: date) -> list[OverrideRow]: ...


def _row_dimension_key(dimension_values: dict[str, str]) -> str:
    """Matches an extracted row's dimensions against an override's
    `dimension_key`. Kept as a single canonical string (sorted key=value
    pairs) so both sides of the merge compute it the same way."""
    return ",".join(f"{k}={v}" for k, v in sorted(dimension_values.items()))


def apply_overrides(rows: list[dict], overrides: list[OverrideRow]) -> list[dict]:
    """Returns a new row list with override values applied where a
    (date, dimension_key, metric_name) match exists. Extracted data is never
    mutated in place, and unmatched overrides (a dimension_key that doesn't
    correspond to any extracted row, e.g. a fully external metric) are
    appended as new rows rather than silently dropped."""
    override_index: dict[tuple[str, str, str], float] = {
        (o.date.isoformat(), o.dimension_key, o.metric_name): o.value for o in overrides
    }
    consumed: set[tuple[str, str, str]] = set()

    result: list[dict] = []
    for row in rows:
        new_row = {
            "date_key": row["date_key"],
            "dimension_values": dict(row["dimension_values"]),
            "metric_values": dict(row["metric_values"]),
        }
        row_dim_key = _row_dimension_key(row["dimension_values"])
        date_key_str = row["date_key"].isoformat() if hasattr(row["date_key"], "isoformat") else row["date_key"]

        for metric_name in list(new_row["metric_values"].keys()):
            override_key = (date_key_str, row_dim_key, metric_name)
            if override_key in override_index:
                new_row["metric_values"][metric_name] = override_index[override_key]
                consumed.add(override_key)

        result.append(new_row)

    # Overrides that named a metric not already present on any row (e.g. a
    # brand-new metric computed entirely externally) become their own rows.
    for override in overrides:
        key = (override.date.isoformat(), override.dimension_key, override.metric_name)
        if key in consumed:
            continue
        dimension_values = dict(
            pair.split("=", 1) for pair in override.dimension_key.split(",") if "=" in pair
        )
        result.append(
            {
                "date_key": override.date,
                "dimension_values": dimension_values,
                "metric_values": {override.metric_name: override.value},
            }
        )

    return result
