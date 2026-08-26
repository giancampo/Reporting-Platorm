"""Snapshot tests on the comment engine (action-plan.md §13): "given a fixed
dataset, the generated text must be stable. It is what allows thresholds to
be changed without discovering months later that one rule broke another."

Each test below hardcodes an exact expected string. If a deliberate change
to a template or a threshold changes the output, the fix is to update the
literal here consciously — not to loosen the assertion — so a change to
generated client-facing text is always a reviewed diff.
"""

from datetime import date

from comment_engine.engine import generate_comment
from comment_engine.metric_dictionary import MetricDictionaryEntry
from comment_engine.partial_period import PeriodWindow
from comment_engine.rules import CommentRule

BIG_JUMP_RULE = CommentRule(
    rule_key="big_jump",
    metric_key="sessions",
    condition={"op": "abs_pct_change_gt", "value": 0.30},
    priority=100,
    templates={
        "en": [
            "Sessions changed by {pct_change} compared to the prior period, led by {top_contributor}.",
        ],
        "it": [
            "Le sessioni sono cambiate del {pct_change} rispetto al periodo precedente, trainate da {top_contributor}.",
        ],
    },
)

STABLE_RULE = CommentRule(
    rule_key="stable",
    metric_key="sessions",
    condition={"op": "abs_pct_change_lte", "value": 0.03},
    priority=10,
    templates={"en": ["Sessions were stable this period."]},
)

RULES = [BIG_JUMP_RULE, STABLE_RULE]
DICTIONARY: list[MetricDictionaryEntry] = []


def test_snapshot_complete_period_big_jump_english():
    result = generate_comment(
        metric_key="sessions",
        current_period=PeriodWindow(start=date(2026, 7, 1), end=date(2026, 7, 31)),
        comparison_period=PeriodWindow(start=date(2025, 7, 1), end=date(2025, 7, 31)),
        current_value=1350,
        comparison_value=1000,
        contributor_deltas={"google / organic": 300, "direct / (none)": 50},
        recent_weekly_values=[240, 250, 245, 255, 260, 248, 252, 249],
        rules=RULES,
        metric_dictionary_entries=DICTIONARY,
        locale="en",
        today=date(2026, 8, 26),
        period_seed="2026-07",
    )
    assert result.text == (
        "Sessions changed by 35.0% compared to the prior period, led by google / organic."
    )
    assert result.is_partial_period_comparison is False
    assert result.definition_changed is False


def test_snapshot_complete_period_big_jump_italian():
    result = generate_comment(
        metric_key="sessions",
        current_period=PeriodWindow(start=date(2026, 7, 1), end=date(2026, 7, 31)),
        comparison_period=PeriodWindow(start=date(2025, 7, 1), end=date(2025, 7, 31)),
        current_value=1350,
        comparison_value=1000,
        contributor_deltas={"google / organic": 300, "direct / (none)": 50},
        recent_weekly_values=[240, 250, 245, 255, 260, 248, 252, 249],
        rules=RULES,
        metric_dictionary_entries=DICTIONARY,
        locale="it",
        today=date(2026, 8, 26),
        period_seed="2026-07",
    )
    assert result.text == (
        "Le sessioni sono cambiate del 35.0% rispetto al periodo precedente, trainate da google / organic."
    )


def test_snapshot_partial_period_appends_note():
    result = generate_comment(
        metric_key="sessions",
        current_period=PeriodWindow(start=date(2026, 8, 1), end=date(2026, 8, 31)),
        comparison_period=PeriodWindow(start=date(2025, 8, 1), end=date(2025, 8, 31)),
        current_value=1350,
        comparison_value=1000,
        contributor_deltas={"google / organic": 300, "direct / (none)": 50},
        recent_weekly_values=[240, 250, 245, 255, 260, 248, 252, 249],
        rules=RULES,
        metric_dictionary_entries=DICTIONARY,
        locale="en",
        today=date(2026, 8, 26),  # month in progress
        period_seed="2026-08",
    )
    assert result.is_partial_period_comparison is True
    assert result.text.endswith(
        "This period is still in progress; the comparison uses an equal number of elapsed days."
    )


def test_snapshot_definition_change_appends_note():
    dictionary = [
        MetricDictionaryEntry(metric_key="sessions", valid_from=date(2020, 1, 1), valid_to=date(2026, 6, 30)),
        MetricDictionaryEntry(metric_key="sessions", valid_from=date(2026, 7, 1), valid_to=None),
    ]
    result = generate_comment(
        metric_key="sessions",
        current_period=PeriodWindow(start=date(2026, 7, 1), end=date(2026, 7, 31)),
        comparison_period=PeriodWindow(start=date(2025, 7, 1), end=date(2025, 7, 31)),
        current_value=1350,
        comparison_value=1000,
        contributor_deltas={"google / organic": 300, "direct / (none)": 50},
        recent_weekly_values=[240, 250, 245, 255, 260, 248, 252, 249],
        rules=RULES,
        metric_dictionary_entries=dictionary,
        locale="en",
        today=date(2026, 8, 26),
        period_seed="2026-07",
    )
    assert result.definition_changed is True
    assert "Note: the definition of sessions changed" in result.text


def test_snapshot_stable_metric_matches_the_stable_rule():
    result = generate_comment(
        metric_key="sessions",
        current_period=PeriodWindow(start=date(2026, 7, 1), end=date(2026, 7, 31)),
        comparison_period=PeriodWindow(start=date(2025, 7, 1), end=date(2025, 7, 31)),
        current_value=1010,
        comparison_value=1000,
        contributor_deltas={},
        recent_weekly_values=[240, 250, 245, 255, 260, 248, 252, 249],
        rules=RULES,
        metric_dictionary_entries=DICTIONARY,
        locale="en",
        today=date(2026, 8, 26),
        period_seed="2026-07",
    )
    assert result.text == "Sessions were stable this period."
