"""Reconciliation between a breakdown and its dimensionless total
(action-plan.md §7: "a total is never computed by summing the rows of a
breakdown"). GA4 data thresholding and the (other) row mean the sum of a
breakdown can legitimately fall short of the true total; this module makes
that gap explicit as "unattributed" instead of letting the dashboard show
inconsistent numbers."""

from __future__ import annotations


def compute_unattributed(
    breakdown_rows: list[dict],
    true_totals: dict[str, float] | None,
) -> dict[str, float] | None:
    """Returns, per metric, true_total - sum(breakdown), floored at 0 (a
    negative gap indicates a data/timing inconsistency between the two
    queries, not "negative unattributed traffic", so it is reported as 0
    with the discrepancy left visible via the two raw numbers instead of
    hidden inside a negative bucket)."""
    if true_totals is None:
        return None

    breakdown_sums: dict[str, float] = {}
    for row in breakdown_rows:
        for metric, value in row["metric_values"].items():
            breakdown_sums[metric] = breakdown_sums.get(metric, 0.0) + value

    return {
        metric: max(true_value - breakdown_sums.get(metric, 0.0), 0.0)
        for metric, true_value in true_totals.items()
    }
