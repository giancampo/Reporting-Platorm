"""Annual retention purge (action-plan.md §6).

Run once a year on 1 February, NOT 1 January — the month of slack exists
because the December report is delivered in January and must still have
complete YoY comparisons. This is a separate job from the nightly ETL,
intentionally: mixing purge logic into the nightly run risks an off-by-one
deleting data a report page still needs.

The window is anchored to calendar-year boundaries (current year plus the
two before it), not a rolling N months, because YoY comparison of a 12-month
period always needs 24 full months upstream of the oldest month shown.
`retention_calendar_years` is a per-project parameter (`projects` table),
default 2 — never a constant here.

Deletion is decided on the PERIOD encoded in the R2 key, never on object
age (§15 anti-pattern): files are rewritten every night, so an object's
last-modified timestamp bears no relation to which period it holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..storage.r2_writer import parse_r2_key, period_year


@dataclass(frozen=True)
class PurgeProjectConfig:
    project_id: str
    project_slug: str
    retention_calendar_years: int
    archive_summary_on_purge: bool


def cutoff_year(today: date, retention_calendar_years: int) -> int:
    """First year that survives the purge. E.g. today=2026-08-26,
    retention_calendar_years=2 -> keep 2024, 2025, 2026 -> cutoff 2024.
    In January 2027 the same call returns 2025, dropping 2024 — this is the
    "window shifts on 1 Jan, purge runs 1 Feb" behavior from §6."""
    return today.year - retention_calendar_years


def select_keys_to_purge(all_keys: list[str], today: date, retention_calendar_years: int) -> list[str]:
    """`all_keys` are the full list of R2 object keys for one project
    (already prefix-filtered by the caller to `{project_slug}/`)."""
    floor_year = cutoff_year(today, retention_calendar_years)
    to_purge: list[str] = []
    for key in all_keys:
        parsed = parse_r2_key(key)
        if period_year(parsed["period"]) < floor_year:
            to_purge.append(key)
    return to_purge


def run_purge(
    r2_client,
    project: PurgeProjectConfig,
    today: date,
) -> list[str]:
    """Returns the list of keys deleted. Archival-before-delete (the
    opt-in monthly summary rollup from §6) is a separate concern handled by
    the caller before invoking this function, since it needs access to the
    document contents, not just keys."""
    prefix = f"{project.project_slug}/"
    all_keys = r2_client.list_keys_with_prefix(prefix)
    keys_to_purge = select_keys_to_purge(all_keys, today, project.retention_calendar_years)
    if keys_to_purge:
        r2_client.delete_keys(keys_to_purge)
    return keys_to_purge
