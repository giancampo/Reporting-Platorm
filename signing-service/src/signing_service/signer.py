"""V4 signed URL generation (action-plan.md §3 "Cost control on Google
Cloud", §6 "Read path"). `UrlSigner` is a small Protocol so the FastAPI
route in main.py can be unit-tested with a fake signer, never touching
real GCP credentials — the same dependency-injection style already used in
etl/src/reporting_etl/identity_switch.py and overrides.py.

`GcsV4UrlSigner` is the production implementation, signing via the IAM
signBlob API under this Cloud Run service's own attached identity rather
than a downloadable private key file — that identity must hold
`roles/iam.serviceAccountTokenCreator` on itself (see README "Setup from
scratch"). This class cannot be exercised in a unit test without real GCP
credentials, same situation as the GA4 Admin/Data API calls in
etl/src/reporting_etl/connectors/ga4.py — it is validated by the fake
signer's contract test plus manual verification against a real deployment,
not a mocked-out unit test.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol


class UrlSigner(Protocol):
    def sign(self, bucket: str, key: str, ttl_seconds: int) -> str: ...


class GcsV4UrlSigner:
    def __init__(self, bucket_name: str) -> None:
        # Deferred imports: keeps this module importable — and therefore
        # main.py's route/auth logic testable via a fake UrlSigner — without
        # any GCP credentials present.
        import google.auth
        from google.auth.iam import Signer
        from google.auth.transport import requests as google_requests
        from google.cloud import storage
        from google.oauth2 import service_account

        credentials, project_id = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_request = google_requests.Request()
        credentials.refresh(auth_request)  # populates credentials.service_account_email

        iam_signer = Signer(auth_request, credentials, credentials.service_account_email)
        self._signing_credentials = service_account.Credentials(
            signer=iam_signer,
            service_account_email=credentials.service_account_email,
            token_uri="https://oauth2.googleapis.com/token",
        )
        self._client = storage.Client(project=project_id, credentials=credentials)
        self._bucket = self._client.bucket(bucket_name)

    def sign(self, bucket: str, key: str, ttl_seconds: int) -> str:
        blob = self._bucket.blob(key)
        return blob.generate_signed_url(
            version="v4",
            expiration=dt.timedelta(seconds=ttl_seconds),
            method="GET",
            credentials=self._signing_credentials,
        )
