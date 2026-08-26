import pytest

from comment_engine.rules import CommentRule, RuleContext, UnsupportedConditionError, evaluate_condition, select_matching_rules

BASE_CONTEXT = RuleContext(
    pct_change=0.35,
    absolute_change=350,
    top_contributor="google / organic",
    top_contributor_share=0.6,
    is_outlier=False,
    z_score=None,
)


def test_abs_pct_change_gt_matches():
    assert evaluate_condition({"op": "abs_pct_change_gt", "value": 0.30}, BASE_CONTEXT) is True
    assert evaluate_condition({"op": "abs_pct_change_gt", "value": 0.40}, BASE_CONTEXT) is False


def test_abs_pct_change_lte_for_stable_case():
    stable_context = RuleContext(
        pct_change=0.01, absolute_change=10, top_contributor=None, top_contributor_share=None, is_outlier=False, z_score=None
    )
    assert evaluate_condition({"op": "abs_pct_change_lte", "value": 0.03}, stable_context) is True


def test_contributor_share_gt():
    assert evaluate_condition({"op": "contributor_share_gt", "value": 0.30}, BASE_CONTEXT) is True


def test_pct_change_undefined_when_no_previous_value():
    ctx = RuleContext(pct_change=None, absolute_change=50, top_contributor=None, top_contributor_share=None, is_outlier=False, z_score=None)
    assert evaluate_condition({"op": "pct_change_undefined"}, ctx) is True


def test_unsupported_condition_raises():
    with pytest.raises(UnsupportedConditionError):
        evaluate_condition({"op": "something_made_up"}, BASE_CONTEXT)


def test_select_matching_rules_sorted_by_priority_desc():
    low = CommentRule(rule_key="low", metric_key="sessions", condition={"op": "abs_pct_change_gt", "value": 0.1}, priority=10, templates={"en": ["x"]})
    high = CommentRule(rule_key="high", metric_key="sessions", condition={"op": "abs_pct_change_gt", "value": 0.1}, priority=100, templates={"en": ["y"]})
    result = select_matching_rules([low, high], BASE_CONTEXT)
    assert [r.rule_key for r in result] == ["high", "low"]
