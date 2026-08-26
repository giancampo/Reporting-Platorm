"""Reconciliation QA script (action-plan.md §13).

"A script comparing extracted totals against a manual check in the GA4
interface, to be run in Phase 1 on a pilot project and on every query
change. It is the only way to catch a dimension or timezone error before it
reaches a client report."

This module is deliberately a comparator, not a GA4 client: it takes an
extracted total and a manually-observed value (typed in by the analyst after
reading the GA4 UI) and reports whether they reconcile within tolerance.
Wiring it to argv / a CLI happens in scripts/, kept out of the library so it
stays unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TOLERANCE_PCT = 0.01  # 1%: GA4's own UI vs API values can differ by rounding/sampling


@dataclass(frozen=True)
class ReconciliationResult:
    metric_key: str
    extracted_value: float
    manual_value: float
    diff_pct: float
    within_tolerance: bool


def reconcile(
    metric_key: str,
    extracted_value: float,
    manual_value: float,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> ReconciliationResult:
    if manual_value == 0:
        diff_pct = 0.0 if extracted_value == 0 else float("inf")
    else:
        diff_pct = abs(extracted_value - manual_value) / abs(manual_value)

    return ReconciliationResult(
        metric_key=metric_key,
        extracted_value=extracted_value,
        manual_value=manual_value,
        diff_pct=diff_pct,
        within_tolerance=diff_pct <= tolerance_pct,
    )


def reconcile_batch(
    checks: dict[str, tuple[float, float]],
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> list[ReconciliationResult]:
    """`checks` maps metric_key -> (extracted_value, manual_value)."""
    return [
        reconcile(metric_key, extracted, manual, tolerance_pct)
        for metric_key, (extracted, manual) in checks.items()
    ]
