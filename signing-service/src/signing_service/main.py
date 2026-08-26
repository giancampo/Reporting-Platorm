"""Cloud Run service replacing the deleted Cloudflare Worker
(`worker/src/index.ts`) as the data-plane chokepoint (action-plan.md §6,
§10): "There must exist no path where the frontend reaches an object
without going through the signing service, and the bucket must never
expose public objects."

`create_app()` is a factory taking an injected `UrlSigner` so this module
has zero import-time side effects and is fully unit-testable without real
GCP/Supabase credentials — see `asgi.py` for the production wiring and
`tests/test_main.py` for the test suite.
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Path
from pydantic import BaseModel

from .access_control import caller_can_access_project
from .auth import InvalidTokenError, decode_supabase_jwt
from .settings import Settings
from .signer import UrlSigner

# Short-lived, per action-plan.md §3 ("Signed URLs are short-lived (minutes,
# not hours)") — long enough for one page load, short enough that a leaked
# URL (browser history, a proxy log) is worthless within the hour.
SIGNED_URL_TTL_SECONDS = 300


class SignedUrlResponse(BaseModel):
    url: str


def create_app(signer: UrlSigner, settings: Settings) -> FastAPI:
    app = FastAPI(title="reporting-platform-signing-service")

    @app.get(
        "/objects/{project_slug}/{source}/{report_key}/{granularity}/{period}",
        response_model=SignedUrlResponse,
    )
    def get_signed_url(
        project_slug: str = Path(..., pattern=r"^[a-z0-9-]+$"),
        source: str = Path(..., pattern=r"^[a-z0-9_]+$"),
        report_key: str = Path(..., pattern=r"^[a-z0-9_]+$"),
        granularity: str = Path(..., pattern=r"^(daily|monthly)$"),
        period: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
        authorization: str | None = Header(default=None),
    ) -> SignedUrlResponse:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.removeprefix("Bearer ")

        try:
            decode_supabase_jwt(token, settings.supabase_jwt_secret)
        except InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid or expired token") from None

        allowed = caller_can_access_project(
            settings.supabase_url, settings.supabase_anon_key, token, project_slug
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Forbidden")

        # Mirrors etl/src/reporting_etl/storage/base.py's build_object_key —
        # changing one without the other breaks every existing object.
        key = f"{project_slug}/{source}/{report_key}/{granularity}/{period}.json.gz"
        url = signer.sign(settings.gcs_bucket, key, SIGNED_URL_TTL_SECONDS)
        return SignedUrlResponse(url=url)

    return app
