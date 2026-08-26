"""Supabase JWT validation — mirrors the signature-check the deleted
Cloudflare Worker (`worker/src/index.ts`, HS256 via `jose`) used to do,
now on the Python side (`PyJWT`) since the data-access chokepoint moved
from a Worker to this Cloud Run service (action-plan.md §3, §10)."""

from __future__ import annotations

import jwt


class InvalidTokenError(Exception):
    pass


def decode_supabase_jwt(token: str, secret: str) -> dict:
    """Raises InvalidTokenError for anything wrong with the token —
    expired, malformed, or a signature mismatch — so the caller has one
    thing to catch and always responds 401, never leaking which case it was."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
