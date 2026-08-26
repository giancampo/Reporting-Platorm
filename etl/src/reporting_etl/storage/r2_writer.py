"""R2 writer (action-plan.md §6).

Key format: `{project_id}/{source}/{report_key}/{granularity}/{period}.json.gz`
— period partitioning here is what makes the retention purge a prefix
list+delete instead of an age-based lifecycle rule (see retention/purge.py
and the explicit anti-pattern in §15 against using object age for retention).

The bucket MUST be created with the `eu` jurisdiction (action-plan.md §3),
which means access goes through the dedicated endpoint
`https://{account_id}.eu.r2.cloudflarestorage.com` rather than the default
R2 S3-compatible endpoint — that endpoint is what `R2_ENDPOINT_URL` must
point to in production, set at bucket-creation time and never changed.
"""

from __future__ import annotations

import gzip
import json
import os
from dataclasses import dataclass


def build_r2_key(
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


def parse_r2_key(key: str) -> dict[str, str]:
    parts = key.split("/")
    if len(parts) != 5 or not parts[4].endswith(".json.gz"):
        raise ValueError(f"Key does not match the expected R2 layout: {key!r}")
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
    write timestamp (files are rewritten nightly, so object age carries no
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


class R2Client:
    """Thin wrapper over boto3's S3-compatible client. Writing is a full
    object overwrite (never an append/patch), which is what makes the nightly
    rolling re-extraction window (§7) naturally idempotent."""

    def __init__(self, endpoint_url: str, bucket: str, access_key_id: str, secret_access_key: str) -> None:
        import boto3  # deferred: keeps this module importable without boto3 installed, for tests

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    @classmethod
    def from_env(cls) -> "R2Client":
        return cls(
            endpoint_url=os.environ["R2_ENDPOINT_URL"],
            bucket=os.environ["R2_BUCKET"],
            access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        )

    def put_document(self, key: str, document: Document) -> None:
        body = serialize(document)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ContentEncoding="gzip",
        )

    def list_keys_with_prefix(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def delete_keys(self, keys: list[str]) -> None:
        for i in range(0, len(keys), 1000):  # S3 delete_objects caps at 1000 per call
            batch = keys[i : i + 1000]
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": k} for k in batch]},
            )
