"""Metric dictionary lookups used to guard the comment engine against
mistaking a definition change for a real trend (action-plan.md §6: "Real
case from the existing report: GA total revenue included shipping and taxes
until February 2026, and not afterwards. The comment engine queries the
dictionary and, faced with a jump that coincides with a definition change,
says so instead of announcing a collapse.")"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MetricDictionaryEntry:
    metric_key: str
    valid_from: date
    valid_to: date | None  # None = still valid


def definition_changed_between(
    entries: list[MetricDictionaryEntry], metric_key: str, period_start: date, period_end: date
) -> bool:
    """True when the metric has more than one dictionary entry whose
    validity window overlaps [period_start, period_end] — i.e. its
    definition changed at some point inside the comparison window."""
    relevant = [e for e in entries if e.metric_key == metric_key]
    overlapping = [
        e
        for e in relevant
        if e.valid_from <= period_end and (e.valid_to is None or e.valid_to >= period_start)
    ]
    return len(overlapping) > 1
