import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_google_cloud_storage(monkeypatch):
    """Installs a fake `google.cloud.storage` module before GCSAdapter's
    deferred import runs, so this test needs no real GCP credentials or
    network access."""
    fake_module = types.ModuleType("google.cloud.storage")
    fake_client_cls = MagicMock(name="Client")
    fake_module.Client = fake_client_cls

    fake_google = sys.modules.get("google") or types.ModuleType("google")
    fake_google_cloud = types.ModuleType("google.cloud")
    fake_google_cloud.storage = fake_module
    fake_google.cloud = fake_google_cloud

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_google_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.storage", fake_module)

    return fake_client_cls


def test_put_document_sets_gzip_content_encoding(fake_google_cloud_storage):
    from reporting_etl.storage.base import Document
    from reporting_etl.storage.gcs_adapter import GCSAdapter

    fake_bucket = MagicMock()
    fake_blob = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_google_cloud_storage.return_value.bucket.return_value = fake_bucket

    adapter = GCSAdapter(bucket_name="my-bucket")
    document = Document(
        schema_version=1,
        project_id="p1",
        source="dummy",
        report_key="channels_overview",
        granularity="daily",
        period="2026-08",
        reporting_identity=None,
        generated_at="2026-08-26T00:00:00Z",
        rows=[],
        totals=None,
        unattributed=None,
        excluded_row_count=0,
    )

    adapter.put_document("acme/dummy/channels_overview/daily/2026-08.json.gz", document)

    fake_bucket.blob.assert_called_once_with("acme/dummy/channels_overview/daily/2026-08.json.gz")
    assert fake_blob.content_encoding == "gzip"
    assert fake_blob.content_type == "application/json"
    fake_blob.upload_from_string.assert_called_once()


def test_list_keys_with_prefix_returns_blob_names(fake_google_cloud_storage):
    from reporting_etl.storage.gcs_adapter import GCSAdapter

    fake_client = fake_google_cloud_storage.return_value
    fake_blob_a = MagicMock(name="acme/dummy/x/daily/2026-08.json.gz")
    fake_blob_a.name = "acme/dummy/x/daily/2026-08.json.gz"
    fake_blob_b = MagicMock()
    fake_blob_b.name = "acme/dummy/x/daily/2026-07.json.gz"
    fake_client.list_blobs.return_value = [fake_blob_a, fake_blob_b]

    adapter = GCSAdapter(bucket_name="my-bucket")
    keys = adapter.list_keys_with_prefix("acme/")

    assert keys == ["acme/dummy/x/daily/2026-08.json.gz", "acme/dummy/x/daily/2026-07.json.gz"]


def test_delete_keys_deletes_each_blob_inside_a_batch(fake_google_cloud_storage):
    from reporting_etl.storage.gcs_adapter import GCSAdapter

    fake_bucket = MagicMock()
    fake_blob = MagicMock()
    fake_bucket.blob.return_value = fake_blob
    fake_client = fake_google_cloud_storage.return_value
    fake_client.bucket.return_value = fake_bucket
    fake_client.batch.return_value.__enter__ = MagicMock(return_value=None)
    fake_client.batch.return_value.__exit__ = MagicMock(return_value=False)

    adapter = GCSAdapter(bucket_name="my-bucket")
    adapter.delete_keys(["a.json.gz", "b.json.gz"])

    fake_bucket.blob.assert_any_call("a.json.gz")
    fake_bucket.blob.assert_any_call("b.json.gz")
    assert fake_blob.delete.call_count == 2
