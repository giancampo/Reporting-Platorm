"""Bot-adjusted sessions metric (action-plan.md §8).

Three layers, applied in order and each independently inspectable — the
dashboard must be able to show what each layer removed, not just the final
number:

1. Base: engagedSessions as the floor. No discretion.
2. Hostname filter: drop rows whose hostname is outside the project's
   allowlist (staging, mirrors, scraped GTM containers).
3. Anomalous segment detection: cross source_medium x browser x
   device_category x os x screen_resolution_bucket, and flag a cell as
   non-human only when ALL three hold: near-zero engagement rate, ~1
   page/session, and volume beyond 3 standard deviations from the median of
   the previous 8 weeks. Bounced human traffic satisfies the first two but
   not the third, which is what keeps this from over-filtering.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median, pstdev

# Common headless-browser / bot default resolutions. Not exhaustive by design —
# this list is a starting signal, not the sole determinant; the volume+z-score
# check in layer 3 is what actually decides.
_SUSPICIOUS_RESOLUTIONS = {"800x600", "1024x768", "(not set)"}

ENGAGEMENT_RATE_NEAR_ZERO = 0.02
PAGES_PER_SESSION_BOT_CEILING = 1.05
VOLUME_Z_SCORE_THRESHOLD = 3.0


@dataclass(frozen=True)
class SegmentStats:
    key: tuple[str, str, str, str, str]  # source_medium, browser, device_category, os, resolution_bucket
    sessions: float
    engaged_sessions: float
    pageviews: float

    @property
    def engagement_rate(self) -> float:
        return self.engaged_sessions / self.sessions if self.sessions else 0.0

    @property
    def pages_per_session(self) -> float:
        return self.pageviews / self.sessions if self.sessions else 0.0


def bucket_screen_resolution(resolution: str, top_resolutions_for_project: set[str]) -> str:
    """Buckets into 'common' (top-50 by volume for the project), 'rare', or
    'suspicious'. Suspicious is the sharpest signal, sharper than browser."""
    if resolution in _SUSPICIOUS_RESOLUTIONS:
        return "suspicious"
    if resolution in top_resolutions_for_project:
        return "common"
    return "rare"


def flag_anomalous_segments(
    current: list[SegmentStats],
    historical_volume_by_key: dict[tuple, list[float]],
) -> set[tuple]:
    """Returns the set of segment keys flagged as non-human. `historical_volume_by_key`
    holds the last 8 weekly volume samples per segment key, used to compute the
    median/stdev baseline this week's volume is compared against."""
    flagged: set[tuple] = set()
    for segment in current:
        if segment.engagement_rate > ENGAGEMENT_RATE_NEAR_ZERO:
            continue
        if segment.pages_per_session > PAGES_PER_SESSION_BOT_CEILING:
            continue

        history = historical_volume_by_key.get(segment.key, [])
        if len(history) < 2:
            continue  # not enough history to judge volume as anomalous
        baseline_median = median(history)
        baseline_stdev = pstdev(history) or 1e-9
        z_score = (segment.sessions - baseline_median) / baseline_stdev
        if z_score > VOLUME_Z_SCORE_THRESHOLD:
            flagged.add(segment.key)

    return flagged


def apply_hostname_filter(
    rows: list[dict], hostname_allowlist: list[str]
) -> tuple[list[dict], list[dict]]:
    """Splits rows into (kept, excluded) based on the project's hostname
    allowlist. If the allowlist is empty, no hostname filtering is applied —
    an empty allowlist is a configuration gap, not an instruction to drop
    everything."""
    if not hostname_allowlist:
        return rows, []
    allowed = set(hostname_allowlist)
    kept = [r for r in rows if r.get("hostname") in allowed]
    excluded = [r for r in rows if r.get("hostname") not in allowed]
    return kept, excluded
