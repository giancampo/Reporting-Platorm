"""Google Cloud Storage backend for the `StorageAdapter` interface
(action-plan.md §3, §4).

The bucket MUST be private with uniform bucket-level access, created in
`europe-west1` (immutable once created), same region as the Cloud Run job so
ETL reads/writes never generate egress charges (§3 "Cost control on Google
Cloud"). No object is ever public — the only read path is a short-lived
signed URL issued by the separate signing-service (§6 "Read path"), never a
direct write-side grant.
"""

from __future__ import annotations

import os

from .base import Document, serialize


class GCSAdapter:
    """Structurally satisfies the `StorageAdapter` Protocol (base.py) —
    Protocols are duck-typed in this codebase, not subclassed, so a future
    backend just needs to implement the same three methods."""

    def __init__(self, bucket_name: str) -> None:
        from google.cloud import storage  # deferred: no credentials needed to import this module, for tests

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    @classmethod
    def from_env(cls) -> "GCSAdapter":
        return cls(bucket_name=os.environ["GCS_BUCKET"])

    def put_document(self, key: str, document: Document) -> None:
        body = serialize(document)
        blob = self._bucket.blob(key)
        blob.content_type = "application/json"
        blob.content_encoding = "gzip"
        blob.upload_from_string(body, content_type="application/json")

    def list_keys_with_prefix(self, prefix: str) -> list[str]:
        return [blob.name for blob in self._client.list_blobs(self._bucket, prefix=prefix)]

    def delete_keys(self, keys: list[str]) -> None:
        # batch() groups the per-blob delete calls into a single HTTP batch
        # request rather than issuing one round trip per key.
        with self._client.batch():
            for key in keys:
                self._bucket.blob(key).delete()
