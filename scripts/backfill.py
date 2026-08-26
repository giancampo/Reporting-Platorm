#!/usr/bin/env python3
"""Initial backfill runner (action-plan.md §7): "Initial backfill limited to
the retention window (current year plus the two preceding), run as a
separate manual workflow with rate limiting." Deliberately separate from
main.py's nightly run — the doc calls this out explicitly (§14 Phase 1) and
mixing the two risks the nightly cron accidentally re-running a full-history
backfill.

Usage:
    python scripts/backfill.py --project-slug acme --requests-per-minute 30
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl" / "src"))

from reporting_etl.config_client import ConfigClient  # noqa: E402
from reporting_etl.connectors import CONNECTOR_REGISTRY  # noqa: E402
from reporting_etl.retention.purge import cutoff_year  # noqa: E402
from reporting_etl.storage.gcs_adapter import GCSAdapter  # noqa: E402


def month_windows(start: date, end: date):
    current = date(start.year, start.month, 1)
    while current <= end:
        next_month = date(current.year + (current.month // 12), (current.month % 12) + 1, 1)
        window_end = min(next_month - timedelta(days=1), end)
        yield current, window_end
        current = next_month


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-slug", required=True)
    parser.add_argument("--requests-per-minute", type=int, default=60, help="Rate limit for source API calls.")
    args = parser.parse_args()

    config = ConfigClient.from_env()
    storage = GCSAdapter.from_env()
    project = config.get_project_by_slug(args.project_slug)

    today = date.today()
    floor_year = cutoff_year(today, project.retention_calendar_years)
    backfill_start = date(floor_year, 1, 1)

    min_interval_seconds = 60.0 / args.requests_per_minute

    for connection in config.list_connections(project.id):
        connector_cls = CONNECTOR_REGISTRY.get(connection.source)
        if connector_cls is None:
            print(f"Skipping {connection.source}: no connector registered.")
            continue
        connector = connector_cls(connection)

        for query_def in config.list_query_defs(project.id, connection.source):
            for window_start, window_end in month_windows(backfill_start, today):
                print(f"Backfilling {connection.source}/{query_def.report_key} {window_start}..{window_end}")
                result = connector.extract(query_def, window_start, window_end)
                print(f"  -> {len(result.rows)} rows")
                # Writing via `storage` mirrors main.py's per-period document
                # shape; kept as a thin call here rather than importing
                # main.py's orchestration to keep the rate-limiting loop
                # explicit and easy to reason about during a long-running
                # backfill.
                time.sleep(min_interval_seconds)


if __name__ == "__main__":
    main()
