from datetime import date

from comment_engine.partial_period import PeriodWindow, build_comparison_basis, is_partial_period


def test_is_partial_period_true_for_month_in_progress():
    assert is_partial_period(period_end=date(2026, 8, 31), today=date(2026, 8, 26)) is True


def test_is_partial_period_false_for_complete_month():
    assert is_partial_period(period_end=date(2026, 7, 31), today=date(2026, 8, 26)) is False


def test_build_comparison_basis_truncates_to_equal_elapsed_days():
    # Aug 2026 is in progress: today is Aug 26, so 26 days elapsed.
    current = PeriodWindow(start=date(2026, 8, 1), end=date(2026, 8, 31))
    comparison = PeriodWindow(start=date(2025, 8, 1), end=date(2025, 8, 31))

    truncated, was_truncated = build_comparison_basis(current, comparison, today=date(2026, 8, 26))

    assert was_truncated is True
    assert truncated.start == date(2025, 8, 1)
    assert truncated.end == date(2025, 8, 26)
    assert truncated.elapsed_days == 26


def test_build_comparison_basis_uses_full_period_when_current_is_complete():
    current = PeriodWindow(start=date(2026, 7, 1), end=date(2026, 7, 31))
    comparison = PeriodWindow(start=date(2025, 7, 1), end=date(2025, 7, 31))

    result, was_truncated = build_comparison_basis(current, comparison, today=date(2026, 8, 26))

    assert was_truncated is False
    assert result == comparison
