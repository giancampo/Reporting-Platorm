"""Partial-period comparisons (action-plan.md §11).

"Comparing a month in progress against a complete month a year earlier
always produces an apparent collapse. The engine must recognise the partial
period and behave accordingly: compare at equal elapsed days, and state
explicitly in the text that the period is incomplete."

Same rule applies to the most recent days inside the rolling re-extraction
window (§7), where data is still settling — `reextraction_window_days` from
`projects` is the boundary the caller should also treat as "still settling"
when deciding what counts as a safe comparison day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PeriodWindow:
    start: date
    end: date  # inclusive

    @property
    def elapsed_days(self) -> int:
        return (self.end - self.start).days + 1


def is_partial_period(period_end: date, today: date) -> bool:
    """A period is partial when its end date hasn't happened yet."""
    return period_end >= today


def equal_elapsed_days_window(full_period: PeriodWindow, elapsed_days: int) -> PeriodWindow:
    """Truncates `full_period` (e.g. the same month a year earlier) to the
    same number of elapsed days as the current, in-progress period — this is
    the "equal elapsed days" comparison basis the doc requires, instead of
    comparing a partial month to a complete one."""
    if elapsed_days > full_period.elapsed_days:
        raise ValueError(
            f"Requested {elapsed_days} elapsed days but the comparison period only has "
            f"{full_period.elapsed_days} days."
        )
    from datetime import timedelta

    return PeriodWindow(start=full_period.start, end=full_period.start + timedelta(days=elapsed_days - 1))


def build_comparison_basis(
    current_period: PeriodWindow,
    comparison_period: PeriodWindow,
    today: date,
) -> tuple[PeriodWindow, bool]:
    """Returns (the window to actually use for the comparison period,
    whether the comparison was truncated to equal elapsed days). If
    `current_period` is complete, the comparison period is used as-is."""
    if not is_partial_period(current_period.end, today):
        return comparison_period, False

    days_elapsed_so_far = (today - current_period.start).days + 1  # today counts as an elapsed (if partial) day
    days_elapsed_so_far = max(1, min(days_elapsed_so_far, current_period.elapsed_days))
    truncated = equal_elapsed_days_window(comparison_period, days_elapsed_so_far)
    return truncated, True
