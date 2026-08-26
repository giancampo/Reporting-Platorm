from datetime import date

from comment_engine.metric_dictionary import MetricDictionaryEntry, definition_changed_between

# Mirrors the doc's real example: GA total revenue included shipping/taxes
# until 2026-02-01, then a new definition took over.
ENTRIES = [
    MetricDictionaryEntry(metric_key="revenue", valid_from=date(2020, 1, 1), valid_to=date(2026, 1, 31)),
    MetricDictionaryEntry(metric_key="revenue", valid_from=date(2026, 2, 1), valid_to=None),
]


def test_flags_definition_change_spanning_the_boundary():
    changed = definition_changed_between(ENTRIES, "revenue", date(2026, 1, 1), date(2026, 3, 1))
    assert changed is True


def test_no_change_flagged_when_comparison_stays_within_one_definition():
    changed = definition_changed_between(ENTRIES, "revenue", date(2026, 3, 1), date(2026, 4, 1))
    assert changed is False


def test_unrelated_metric_never_flagged():
    changed = definition_changed_between(ENTRIES, "sessions", date(2026, 1, 1), date(2026, 3, 1))
    assert changed is False
