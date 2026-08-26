"""Layer 1 of the comment engine (action-plan.md §11): MoM/YoY changes,
contribution to a delta, and z-score outliers over a 12-week window. Pure
arithmetic — no rule thresholds and no text live here, so this module stays
reusable if the analyst-facing dashboard ever wants the same numbers without
generating a comment."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median, pstdev


@dataclass(frozen=True)
class PeriodChange:
    current_value: float
    previous_value: float
    absolute_change: float
    pct_change: float | None  # None when previous_value is 0 (undefined % change)


def compute_change(current_value: float, previous_value: float) -> PeriodChange:
    absolute_change = current_value - previous_value
    pct_change = None if previous_value == 0 else absolute_change / previous_value
    return PeriodChange(
        current_value=current_value,
        previous_value=previous_value,
        absolute_change=absolute_change,
        pct_change=pct_change,
    )


def compute_contribution(delta_by_segment: dict[str, float], total_delta: float) -> dict[str, float]:
    """Fraction of `total_delta` each segment's own delta accounts for.
    Used by the rules layer's "if a channel contributes more than 30% of the
    total delta, name it" example (§11)."""
    if total_delta == 0:
        return {segment: 0.0 for segment in delta_by_segment}
    return {segment: delta / total_delta for segment, delta in delta_by_segment.items()}


@dataclass(frozen=True)
class OutlierCheck:
    sufficient_history: bool
    z_score: float | None  # None when sufficient_history is False
    is_outlier: bool


def z_score_outliers(
    current_value: float,
    recent_values: list[float],
    z_threshold: float = 2.0,
) -> OutlierCheck:
    """Checks `current_value` against `recent_values` (expected: the last 12
    weekly values, not including the current one). Fewer than 4 samples is
    treated as insufficient history to judge, distinct from "checked and
    found not to be an outlier" — the comment engine phrases these two cases
    differently rather than collapsing them into the same silence."""
    if len(recent_values) < 4:
        return OutlierCheck(sufficient_history=False, z_score=None, is_outlier=False)
    baseline_median = median(recent_values)
    baseline_stdev = pstdev(recent_values) or 1e-9
    score = (current_value - baseline_median) / baseline_stdev
    return OutlierCheck(sufficient_history=True, z_score=score, is_outlier=abs(score) >= z_threshold)
