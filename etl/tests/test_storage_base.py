from reporting_etl.storage.base import build_object_key, parse_object_key, period_year


def test_build_object_key_matches_expected_layout():
    key = build_object_key("acme", "ga4", "channels_overview", "daily", "2026-08")
    assert key == "acme/ga4/channels_overview/daily/2026-08.json.gz"


def test_parse_object_key_round_trips():
    key = build_object_key("acme", "ga4", "channels_overview", "monthly", "2026-08")
    parsed = parse_object_key(key)
    assert parsed == {
        "project_slug": "acme",
        "source": "ga4",
        "report_key": "channels_overview",
        "granularity": "monthly",
        "period": "2026-08",
    }


def test_parse_object_key_rejects_malformed_key():
    import pytest

    with pytest.raises(ValueError):
        parse_object_key("not/a/valid/key")


def test_period_year_extracts_the_year():
    assert period_year("2026-08") == 2026
