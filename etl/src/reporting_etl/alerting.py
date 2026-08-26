"""ETL alerting (action-plan.md §13).

"A run that never starts must alert as loudly as one that errors: silence is
the worst case." Two triggers implemented here: a run recorded as
failed/skipped, and an anomalous drop in extracted row volume versus the
project's recent median (broken client-side tracking looks exactly like
this — a good file gets silently overwritten with an almost-empty one
unless this check exists).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Protocol

VOLUME_DROP_ALERT_THRESHOLD = 0.90  # alert if rows extracted are >=90% below the recent median


class AlertSink(Protocol):
    def send(self, subject: str, body: str, project_slug: str) -> None: ...


@dataclass(frozen=True)
class RunOutcome:
    project_slug: str
    source: str
    status: str  # 'success' | 'partial' | 'failed' | 'skipped'
    rows_extracted: int | None
    error_message: str | None


def check_run_outcome(outcome: RunOutcome, sink: AlertSink) -> None:
    if outcome.status in ("failed", "skipped"):
        sink.send(
            subject=f"[ETL] {outcome.status.upper()} — {outcome.project_slug}/{outcome.source}",
            body=outcome.error_message or "No error message recorded.",
            project_slug=outcome.project_slug,
        )


def check_volume_anomaly(
    project_slug: str,
    source: str,
    rows_extracted: int,
    recent_run_row_counts: list[int],
    sink: AlertSink,
) -> bool:
    """Returns True if an anomaly was flagged. `recent_run_row_counts` should
    be recent successful runs for the same project/source, excluding the
    current one. Requires at least 3 samples to establish a meaningful
    baseline; with fewer, a real (non-anomalous) ramp-up would trip this."""
    if len(recent_run_row_counts) < 3:
        return False

    baseline = median(recent_run_row_counts)
    if baseline <= 0:
        return False

    drop_ratio = (baseline - rows_extracted) / baseline
    if drop_ratio >= VOLUME_DROP_ALERT_THRESHOLD:
        sink.send(
            subject=f"[ETL] Volume anomaly — {project_slug}/{source}",
            body=(
                f"Extracted {rows_extracted} rows vs a recent median of {baseline:.0f} "
                f"({drop_ratio:.0%} drop). Possible broken tracking; file was NOT overwritten "
                "pending review."
            ),
            project_slug=project_slug,
        )
        return True
    return False
