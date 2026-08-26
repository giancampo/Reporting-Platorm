import pytest

from comment_engine.rules import CommentRule
from comment_engine.templates import MissingEnglishTemplateError, render_template

RULE = CommentRule(
    rule_key="big_jump",
    metric_key="sessions",
    condition={"op": "abs_pct_change_gt", "value": 0.3},
    priority=100,
    templates={
        "en": ["Sessions changed by {pct_change}.", "A notable {pct_change} move in sessions.", "Sessions moved {pct_change} this period."],
        "it": ["Le sessioni sono cambiate del {pct_change}."],
    },
)


def test_render_template_is_deterministic_for_the_same_seed():
    first = render_template(RULE, "en", seed="2026-08", tokens={"pct_change": "35%"})
    second = render_template(RULE, "en", seed="2026-08", tokens={"pct_change": "35%"})
    assert first == second


def test_render_template_rotates_across_different_seeds():
    seen = {render_template(RULE, "en", seed=f"2026-{month:02d}", tokens={"pct_change": "35%"}) for month in range(1, 13)}
    # Not asserting exact distribution, just that rotation actually happens
    # across a year of periods rather than always landing on variant 0.
    assert len(seen) > 1


def test_render_template_falls_back_to_english_when_locale_missing_variants():
    text = render_template(
        CommentRule(rule_key="x", metric_key="sessions", condition={}, priority=1, templates={"en": ["Only English."]}),
        "it",
        seed="2026-08",
        tokens={},
    )
    assert text == "Only English."


def test_render_template_raises_when_no_english_template_exists():
    bad_rule = CommentRule(rule_key="x", metric_key="sessions", condition={}, priority=1, templates={"it": ["Solo italiano."]})
    with pytest.raises(MissingEnglishTemplateError):
        render_template(bad_rule, "it", seed="2026-08", tokens={})


def test_render_template_raises_on_unknown_token():
    with pytest.raises(ValueError):
        render_template(RULE, "en", seed="2026-08", tokens={})  # missing 'pct_change'
