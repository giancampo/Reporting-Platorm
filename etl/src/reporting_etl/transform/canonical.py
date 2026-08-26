"""Native -> canonical field renaming (action-plan.md §6).

"Native source names never leave the adapter. sessionSourceMedium ->
source_medium, screenPageViews -> pageviews. The rest of the system knows
canonical names only." This module is the single place that mapping lives
for GA4; a future connector (Google Ads, Shopify) gets its own mapping file
next to its adapter, following the same pattern, never a shared enum that
grows unbounded.
"""

from __future__ import annotations

# GA4 Data API dimension/metric API-names -> canonical names used everywhere
# downstream (query_defs, derived_metrics expressions, metric_dictionary,
# report_defs, the frontend aggregation engine).
GA4_DIMENSION_MAP: dict[str, str] = {
    "date": "date",
    "sessionSourceMedium": "source_medium",
    "sessionDefaultChannelGroup": "channel_group",
    "country": "country",
    "deviceCategory": "device_category",
    "browser": "browser",
    "operatingSystem": "os",
    "screenResolution": "screen_resolution",
    "landingPagePlusQueryString": "landing_page",
    "itemName": "item_name",
    "hostName": "hostname",
}

GA4_METRIC_MAP: dict[str, str] = {
    "sessions": "sessions",
    "engagedSessions": "engaged_sessions",
    "screenPageViews": "pageviews",
    "conversions": "conversions",
    "totalRevenue": "revenue",
    "transactions": "transactions",
    "engagementRate": "engagement_rate",  # raw GA4 ratio; not used for aggregation, see §9
    "averageSessionDuration": "avg_session_duration",
    "bounceRate": "bounce_rate",
}

CANONICAL_TO_GA4_DIMENSION = {v: k for k, v in GA4_DIMENSION_MAP.items()}
CANONICAL_TO_GA4_METRIC = {v: k for k, v in GA4_METRIC_MAP.items()}


def to_canonical_dimension(ga4_name: str) -> str:
    try:
        return GA4_DIMENSION_MAP[ga4_name]
    except KeyError as exc:
        raise ValueError(
            f"Unmapped GA4 dimension '{ga4_name}'. Add it to GA4_DIMENSION_MAP "
            "before referencing it from a query_defs row."
        ) from exc


def to_canonical_metric(ga4_name: str) -> str:
    try:
        return GA4_METRIC_MAP[ga4_name]
    except KeyError as exc:
        raise ValueError(
            f"Unmapped GA4 metric '{ga4_name}'. Add it to GA4_METRIC_MAP "
            "before referencing it from a query_defs row."
        ) from exc


def to_ga4_dimension(canonical_name: str) -> str:
    try:
        return CANONICAL_TO_GA4_DIMENSION[canonical_name]
    except KeyError as exc:
        raise ValueError(f"Canonical dimension '{canonical_name}' has no GA4 mapping.") from exc


def to_ga4_metric(canonical_name: str) -> str:
    try:
        return CANONICAL_TO_GA4_METRIC[canonical_name]
    except KeyError as exc:
        raise ValueError(f"Canonical metric '{canonical_name}' has no GA4 mapping.") from exc
