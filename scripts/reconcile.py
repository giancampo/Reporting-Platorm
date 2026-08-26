#!/usr/bin/env python3
"""Reconciliation CLI (action-plan.md §13): compares extracted totals
against numbers typed in by the analyst after reading the GA4 UI directly.
Run on the pilot project in Phase 1 and on every query_defs change.

Usage:
    python scripts/reconcile.py --check sessions:12345:12350 --check revenue:980.5:1000.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "comment-engine" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl" / "src"))

from reporting_etl.reconciliation import reconcile_batch  # noqa: E402


def parse_check(raw: str) -> tuple[str, tuple[float, float]]:
    metric_key, extracted, manual = raw.split(":")
    return metric_key, (float(extracted), float(manual))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="append",
        required=True,
        metavar="METRIC:EXTRACTED:MANUAL",
        help="e.g. --check sessions:12345:12350",
    )
    parser.add_argument("--tolerance-pct", type=float, default=0.01)
    args = parser.parse_args()

    checks = dict(parse_check(raw) for raw in args.check)
    results = reconcile_batch(checks, tolerance_pct=args.tolerance_pct)

    failed = [r for r in results if not r.within_tolerance]
    for result in results:
        status = "OK" if result.within_tolerance else "MISMATCH"
        print(
            f"[{status}] {result.metric_key}: extracted={result.extracted_value} "
            f"manual={result.manual_value} diff={result.diff_pct:.2%}"
        )

    if failed:
        print(f"\n{len(failed)} metric(s) outside tolerance.")
        sys.exit(1)


if __name__ == "__main__":
    main()
