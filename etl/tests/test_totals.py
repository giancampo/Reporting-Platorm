from reporting_etl.transform.totals import compute_unattributed


def test_compute_unattributed_reports_gap():
    breakdown_rows = [
        {"metric_values": {"sessions": 100}},
        {"metric_values": {"sessions": 50}},
    ]
    true_totals = {"sessions": 200}  # 50 sessions hidden by thresholding/(other)
    result = compute_unattributed(breakdown_rows, true_totals)
    assert result == {"sessions": 50}


def test_compute_unattributed_floors_at_zero():
    breakdown_rows = [{"metric_values": {"sessions": 210}}]
    true_totals = {"sessions": 200}
    result = compute_unattributed(breakdown_rows, true_totals)
    assert result == {"sessions": 0}


def test_compute_unattributed_none_when_no_true_total_available():
    assert compute_unattributed([{"metric_values": {"sessions": 10}}], None) is None
