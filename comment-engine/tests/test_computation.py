from comment_engine.computation import compute_change, compute_contribution, z_score_outliers


def test_compute_change_basic():
    change = compute_change(120, 100)
    assert change.absolute_change == 20
    assert change.pct_change == 0.2


def test_compute_change_undefined_when_previous_is_zero():
    change = compute_change(50, 0)
    assert change.pct_change is None
    assert change.absolute_change == 50


def test_compute_contribution_shares_sum_to_one_when_signs_match():
    contributions = compute_contribution({"google": 60, "direct": 40}, total_delta=100)
    assert contributions == {"google": 0.6, "direct": 0.4}


def test_compute_contribution_zero_total_delta_returns_zeros():
    contributions = compute_contribution({"google": 10, "direct": -10}, total_delta=0)
    assert contributions == {"google": 0.0, "direct": 0.0}


def test_z_score_outliers_insufficient_history():
    result = z_score_outliers(1000, [100, 110])
    assert result.sufficient_history is False
    assert result.is_outlier is False


def test_z_score_outliers_flags_extreme_value():
    history = [95, 100, 105, 98, 102, 97, 101, 99]
    result = z_score_outliers(500, history)
    assert result.sufficient_history is True
    assert result.is_outlier is True


def test_z_score_outliers_stable_value_not_flagged():
    history = [95, 100, 105, 98, 102, 97, 101, 99]
    result = z_score_outliers(100, history)
    assert result.is_outlier is False
