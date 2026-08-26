"""Storage adapter interface (action-plan.md §4: "Storage is behind an
adapter. The rest of the system asks for 'the object for project X, report
Y, period Z' and does not know whether it comes from GCS, R2 or anything
else. This is what makes a future move back to R2 a one-file change.")

Everything provider-agnostic lives here: the object key layout, the
document schema, and the `StorageAdapter` Protocol every concrete backend
implements. The current concrete backend is `storage/gcs_adapter.py`
(Google Cloud Storage — R2 was rejected in the revised plan because it
requires a payment method the analyst doesn't have, action-plan.md §3
"Explicitly rejected options").

Key format: `{project_id}/{source}/{report_key}/{granularity}/{period}.json.gz`
— period partitioning here is what makes the retention purge a prefix
list+delete instead of an age-based lifecycle rule (see retention/purge.py
and the explicit anti-pattern in §15 against using object age for retention).
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from typing import Protocol


def build_object_key(
    project_slug: str,
    source: str,
    report_key: str,
    granularity: str,
    period: str,
) -> str:
    """`period` is 'YYYY-MM' for monthly-grain files and 'YYYY-MM' for daily
    files too (one file per month holding daily rows). `granularity` selects
    the shape, not the key layout, so a query_defs granularity change never
    breaks existing keys."""
    return f"{project_slug}/{source}/{report_key}/{granularity}/{period}.json.gz"


def parse_object_key(key: str) -> dict[str, str]:
    parts = key.split("/")
    if len(parts) != 5 or not parts[4].endswith(".json.gz"):
        raise ValueError(f"Key does not match the expected object layout: {key!r}")
    project_slug, source, report_key, granularity, filename = parts
    period = filename.removesuffix(".json.gz")
    return {
        "project_slug": project_slug,
        "source": source,
        "report_key": report_key,
        "granularity": granularity,
        "period": period,
    }


def period_year(period: str) -> int:
    """Extracts the data year from a period string, used by the retention
    purge to decide what to delete based on the PERIOD, never the object's
    write timestamp (objects are rewritten nightly, so age carries no
    signal about the data inside)."""
    return int(period.split("-")[0])


@dataclass
class Document:
    schema_version: int
    project_id: str
    source: str
    report_key: str
    granularity: str
    period: str
    reporting_identity: str | None  # 'blended' | 'observed' | None — carried from Phase 1 (§7)
    generated_at: str  # ISO 8601 UTC, so the frontend can show a freshness/staleness indicator
    rows: list[dict]
    totals: dict[str, float] | None
    unattributed: dict[str, float] | None
    excluded_row_count: int


def serialize(document: Document) -> bytes:
    payload = {
        "schema_version": document.schema_version,
        "project_id": document.project_id,
        "source": document.source,
        "report_key": document.report_key,
        "granularity": document.granularity,
        "period": document.period,
        "reporting_identity": document.reporting_identity,
        "generated_at": document.generated_at,
        "rows": document.rows,
        "totals": document.totals,
        "unattributed": document.unattributed,
        "excluded_row_count": document.excluded_row_count,
    }
    return gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


class StorageAdapter(Protocol):
    """Every concrete backend implements exactly this surface. Writing is
    always a full object overwrite (never an append/patch), which is what
    makes the nightly rolling re-extraction window (§7) naturally
    idempotent, and deletion is always by key list, never by an age-based
    lifecycle rule (§15 anti-pattern)."""

    def put_document(self, key: str, document: Document) -> None: ...

    def list_keys_with_prefix(self, prefix: str) -> list[str]: ...

    def delete_keys(self, keys: list[str]) -> None: ...
