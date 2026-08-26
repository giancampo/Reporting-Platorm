from datetime import date

from reporting_etl.transform.cardinality import OTHERS_LABEL, bucket_top_n


def _row(item_name: str, sessions: float, day=date(2026, 8, 1)):
    return {
        "date_key": day,
        "dimension_values": {"item_name": item_name},
        "metric_values": {"sessions": sessions},
    }


def test_bucket_top_n_keeps_top_and_collapses_rest():
    rows = [_row("A", 100), _row("B", 80), _row("C", 5), _row("D", 3)]
    result = bucket_top_n(rows, "item_name", "sessions", top_n=2)

    kept_labels = {r["dimension_values"]["item_name"] for r in result}
    assert kept_labels == {"A", "B", OTHERS_LABEL}

    others_row = next(r for r in result if r["dimension_values"]["item_name"] == OTHERS_LABEL)
    assert others_row["metric_values"]["sessions"] == 8


def test_bucket_top_n_no_others_when_within_limit():
    rows = [_row("A", 10), _row("B", 5)]
    result = bucket_top_n(rows, "item_name", "sessions", top_n=5)
    assert len(result) == 2
    assert all(r["dimension_values"]["item_name"] != OTHERS_LABEL for r in result)
