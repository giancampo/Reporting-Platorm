from datetime import date

from reporting_etl.retention.purge import cutoff_year, select_keys_to_purge


def test_cutoff_year_default_two_years():
    assert cutoff_year(date(2026, 8, 26), retention_calendar_years=2) == 2024


def test_cutoff_year_shifts_on_january_boundary():
    # The doc's explicit example: Dec 2026 -> oldest available is Jan 2024;
    # Jan 2027 -> the window shifts and 2024 is removed.
    assert cutoff_year(date(2026, 12, 15), retention_calendar_years=2) == 2024
    assert cutoff_year(date(2027, 1, 5), retention_calendar_years=2) == 2025


def test_select_keys_to_purge_uses_period_not_object_age():
    keys = [
        "acme/ga4/channels_overview/daily/2023-12.json.gz",  # too old, purge
        "acme/ga4/channels_overview/daily/2024-01.json.gz",  # boundary, keep
        "acme/ga4/channels_overview/daily/2026-08.json.gz",  # current, keep
    ]
    purged = select_keys_to_purge(keys, today=date(2026, 8, 26), retention_calendar_years=2)
    assert purged == ["acme/ga4/channels_overview/daily/2023-12.json.gz"]


def test_select_keys_to_purge_respects_per_project_window():
    keys = ["acme/ga4/channels_overview/daily/2022-06.json.gz"]
    # A client configured for 5 years of retention keeps 2022 data in 2026.
    purged = select_keys_to_purge(keys, today=date(2026, 8, 26), retention_calendar_years=5)
    assert purged == []
