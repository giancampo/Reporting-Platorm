import pytest

from reporting_etl.transform.exclusion_rules import (
    ExclusionRuleError,
    apply_exclusion_rules,
    evaluate_filter,
)


def _row(**dims):
    return {"dimension_values": dims, "metric_values": {}}


def test_evaluate_filter_simple_equality():
    row = _row(device_category="desktop")
    assert evaluate_filter("device_category == 'desktop'", row) is True
    assert evaluate_filter("device_category == 'mobile'", row) is False


def test_evaluate_filter_boolean_combination():
    row = _row(device_category="desktop", country="XX")
    assert evaluate_filter("device_category == 'desktop' and country == 'XX'", row) is True
    assert evaluate_filter("device_category == 'mobile' or country == 'XX'", row) is True


def test_evaluate_filter_unknown_field_raises():
    with pytest.raises(ExclusionRuleError):
        evaluate_filter("nonexistent_field == 'x'", _row(device_category="desktop"))


def test_evaluate_filter_rejects_unsupported_syntax():
    with pytest.raises(ExclusionRuleError):
        evaluate_filter("__import__('os').system('echo hi')", _row())


def test_apply_exclusion_rules_is_non_destructive_split():
    rows = [_row(device_category="desktop"), _row(device_category="mobile")]
    kept, excluded = apply_exclusion_rules(rows, ["device_category == 'mobile'"])
    assert kept == [rows[0]]
    assert excluded == [rows[1]]


def test_apply_exclusion_rules_no_rules_keeps_everything():
    rows = [_row(device_category="desktop")]
    kept, excluded = apply_exclusion_rules(rows, [])
    assert kept == rows
    assert excluded == []
