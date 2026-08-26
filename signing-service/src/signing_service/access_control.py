"""Re-validates project access via PostgREST, under the caller's own JWT so
RLS (project_users membership, see supabase/migrations/0002_rls_policies.sql)
decides — this service never has its own elevated view of who can see what.
Same trick the deleted Cloudflare Worker used (`callerCanAccessProject` in
`worker/src/index.ts`), ported here since the Worker no longer exists."""

from __future__ import annotations

import httpx


def caller_can_access_project(
    supabase_url: str,
    anon_key: str,
    token: str,
    project_slug: str,
) -> bool:
    url = f"{supabase_url}/rest/v1/projects"
    try:
        response = httpx.get(
            url,
            params={"slug": f"eq.{project_slug}", "select": "id"},
            headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    return len(response.json()) > 0
