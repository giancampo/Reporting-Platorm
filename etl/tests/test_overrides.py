from datetime import date

from reporting_etl.overrides import OverrideRow, apply_overrides


def _row(day, dims, metrics):
    return {"date_key": day, "dimension_values": dims, "metric_values": metrics}


def test_override_replaces_matching_metric_value():
    rows = [_row(date(2026, 8, 1), {"source_medium": "google / organic"}, {"sessions": 100})]
    overrides = [
        OverrideRow(
            project_id="p1",
            date=date(2026, 8, 1),
            dimension_key="source_medium=google / organic",
            metric_name="sessions",
            value=250,
        )
    ]
    result = apply_overrides(rows, overrides)
    assert len(result) == 1
    assert result[0]["metric_values"]["sessions"] == 250


def test_override_does_not_touch_unrelated_metrics():
    rows = [_row(date(2026, 8, 1), {"source_medium": "google / organic"}, {"sessions": 100, "conversions": 4})]
    overrides = [
        OverrideRow(project_id="p1", date=date(2026, 8, 1), dimension_key="source_medium=google / organic", metric_name="sessions", value=250)
    ]
    result = apply_overrides(rows, overrides)
    assert result[0]["metric_values"]["conversions"] == 4


def test_override_does_not_mutate_original_rows():
    original = _row(date(2026, 8, 1), {"source_medium": "google / organic"}, {"sessions": 100})
    overrides = [
        OverrideRow(project_id="p1", date=date(2026, 8, 1), dimension_key="source_medium=google / organic", metric_name="sessions", value=250)
    ]
    apply_overrides([original], overrides)
    assert original["metric_values"]["sessions"] == 100


def test_unmatched_override_is_appended_as_a_new_row():
    rows = [_row(date(2026, 8, 1), {"source_medium": "google / organic"}, {"sessions": 100})]
    overrides = [
        OverrideRow(project_id="p1", date=date(2026, 8, 1), dimension_key="source_medium=newsletter / email", metric_name="sessions", value=42)
    ]
    result = apply_overrides(rows, overrides)
    assert len(result) == 2
    appended = next(r for r in result if r["dimension_values"].get("source_medium") == "newsletter / email")
    assert appended["metric_values"]["sessions"] == 42
