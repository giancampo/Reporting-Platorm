"""Production ASGI entrypoint: `uvicorn signing_service.asgi:app`. Kept
separate from main.py so importing `main.create_app` for tests never
requires real Supabase/GCP credentials — only importing *this* module does."""

from __future__ import annotations

from .main import create_app
from .settings import Settings
from .signer import GcsV4UrlSigner

_settings = Settings.from_env()
app = create_app(GcsV4UrlSigner(_settings.gcs_bucket), _settings)
