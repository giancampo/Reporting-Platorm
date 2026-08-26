from reporting_etl.transform.bot_filter import (
    SegmentStats,
    apply_hostname_filter,
    bucket_screen_resolution,
    flag_anomalous_segments,
)


def test_bucket_screen_resolution_suspicious_defaults():
    assert bucket_screen_resolution("800x600", top_resolutions_for_project=set()) == "suspicious"
    assert bucket_screen_resolution("(not set)", top_resolutions_for_project=set()) == "suspicious"


def test_bucket_screen_resolution_common_vs_rare():
    top = {"1920x1080"}
    assert bucket_screen_resolution("1920x1080", top) == "common"
    assert bucket_screen_resolution("2560x1440", top) == "rare"


def test_flag_anomalous_segments_requires_all_three_conditions():
    # Bounced human traffic: near-zero engagement, ~1 page/session, but
    # volume is NOT anomalous vs history -> must not be flagged.
    bounced_human = SegmentStats(
        key=("direct / (none)", "Chrome", "mobile", "iOS", "common"),
        sessions=120,
        engaged_sessions=1,
        pageviews=125,
    )
    history = {bounced_human.key: [110, 115, 118, 120, 122]}
    flagged = flag_anomalous_segments([bounced_human], history)
    assert flagged == set()


def test_flag_anomalous_segments_flags_bot_like_traffic():
    bot_segment = SegmentStats(
        key=("(direct) / (none)", "HeadlessChrome", "desktop", "Linux", "suspicious"),
        sessions=5000,
        engaged_sessions=2,
        pageviews=5010,
    )
    # Weekly baseline hovers around 100 sessions -> 5000 is a massive z-score outlier.
    history = {bot_segment.key: [95, 100, 105, 98, 102, 97, 101, 99]}
    flagged = flag_anomalous_segments([bot_segment], history)
    assert bot_segment.key in flagged


def test_flag_anomalous_segments_skips_when_insufficient_history():
    new_segment = SegmentStats(
        key=("google / cpc", "Chrome", "desktop", "Windows", "common"),
        sessions=1000,
        engaged_sessions=1,
        pageviews=1005,
    )
    flagged = flag_anomalous_segments([new_segment], {new_segment.key: [50]})
    assert flagged == set()


def test_apply_hostname_filter_empty_allowlist_keeps_everything():
    rows = [{"hostname": "staging.example.com"}]
    kept, excluded = apply_hostname_filter(rows, hostname_allowlist=[])
    assert kept == rows
    assert excluded == []


def test_apply_hostname_filter_drops_non_allowlisted_hosts():
    rows = [{"hostname": "acme.com"}, {"hostname": "staging.acme.com"}]
    kept, excluded = apply_hostname_filter(rows, hostname_allowlist=["acme.com"])
    assert kept == [{"hostname": "acme.com"}]
    assert excluded == [{"hostname": "staging.acme.com"}]
