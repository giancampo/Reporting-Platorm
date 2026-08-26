import time

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from signing_service.main import create_app
from signing_service.settings import Settings

JWT_SECRET = "test-secret-at-least-32-bytes-long!!"

SETTINGS = Settings(
    supabase_url="https://example.supabase.co",
    supabase_anon_key="anon-key",
    supabase_jwt_secret=JWT_SECRET,
    gcs_bucket="my-bucket",
)

VALID_PATH = "/objects/pilot/dummy/channels_overview/daily/2026-08"


class FakeUrlSigner:
    def __init__(self):
        self.calls: list[tuple[str, str, int]] = []

    def sign(self, bucket: str, key: str, ttl_seconds: int) -> str:
        self.calls.append((bucket, key, ttl_seconds))
        return f"https://storage.googleapis.com/{bucket}/{key}?signed=true"


def make_token(sub: str = "user-1", expired: bool = False) -> str:
    now = int(time.time())
    exp = now - 60 if expired else now + 3600
    return jwt.encode({"sub": sub, "exp": exp}, JWT_SECRET, algorithm="HS256")


def build_client(signer: FakeUrlSigner) -> TestClient:
    app = create_app(signer, SETTINGS)
    return TestClient(app)


def _mock_supabase_response(monkeypatch, rows: list[dict], status_code: int = 200):
    def fake_get(url, params=None, headers=None, timeout=None):
        return httpx.Response(status_code, json=rows, request=httpx.Request("GET", url))

    monkeypatch.setattr("signing_service.access_control.httpx.get", fake_get)


def test_rejects_requests_with_no_authorization_header():
    client = build_client(FakeUrlSigner())
    response = client.get(VALID_PATH)
    assert response.status_code == 401


def test_rejects_an_expired_token():
    client = build_client(FakeUrlSigner())
    token = make_token(expired=True)
    response = client.get(VALID_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_rejects_a_path_with_the_wrong_number_of_segments():
    # No route matches at all (fewer path segments than /objects/{...}x5) —
    # a genuine Starlette 404, distinct from a well-formed-but-invalid value.
    client = build_client(FakeUrlSigner())
    token = make_token()
    response = client.get(
        "/objects/pilot/dummy",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_rejects_an_invalid_granularity_value():
    # Route matches structurally, but 'hourly' fails the granularity Path
    # pattern constraint — FastAPI responds 422, not 404, since this is a
    # validation failure on an otherwise well-formed request.
    client = build_client(FakeUrlSigner())
    token = make_token()
    response = client.get(
        "/objects/pilot/dummy/channels_overview/hourly/2026-08",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_returns_403_when_caller_has_no_access_to_the_project(monkeypatch):
    _mock_supabase_response(monkeypatch, rows=[])  # RLS denies: empty result
    client = build_client(FakeUrlSigner())
    token = make_token()
    response = client.get(VALID_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_returns_a_signed_url_when_authorized(monkeypatch):
    _mock_supabase_response(monkeypatch, rows=[{"id": "proj-1"}])
    signer = FakeUrlSigner()
    client = build_client(signer)
    token = make_token()

    response = client.get(VALID_PATH, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "https://storage.googleapis.com/my-bucket/pilot/dummy/channels_overview/daily/2026-08.json.gz?signed=true"
    assert signer.calls == [("my-bucket", "pilot/dummy/channels_overview/daily/2026-08.json.gz", 300)]


def test_returns_403_when_supabase_check_itself_errors(monkeypatch):
    _mock_supabase_response(monkeypatch, rows=[], status_code=500)
    client = build_client(FakeUrlSigner())
    token = make_token()
    response = client.get(VALID_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
