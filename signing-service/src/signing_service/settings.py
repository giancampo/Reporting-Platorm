"""Runtime configuration. A plain dataclass (not read-from-env-at-import)
so tests can construct arbitrary `Settings` values directly, and only the
production entrypoint (`asgi.py`) ever calls `from_env()`."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    supabase_jwt_secret: str
    gcs_bucket: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            supabase_url=os.environ["SUPABASE_URL"],
            supabase_anon_key=os.environ["SUPABASE_ANON_KEY"],
            supabase_jwt_secret=os.environ["SUPABASE_JWT_SECRET"],
            gcs_bucket=os.environ["GCS_BUCKET"],
        )
