"""Reads the control-plane config tables from Supabase (PostgREST) so the ETL
never hardcodes project/query/report definitions (action-plan.md §4). Uses
the service_role key, which bypasses RLS by design — the ETL is a trusted
backend process, not a per-user session.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from .connectors.base import Connection, QueryDef


@dataclass(frozen=True)
class ProjectConfig:
    id: str
    slug: str
    display_name: str
    timezone: str
    currency_code: str
    hostname_allowlist: list[str]
    retention_calendar_years: int
    reextraction_window_days: int
    resting_reporting_identity: str
    archive_summary_on_purge: bool


class ConfigClient:
    def __init__(self, base_url: str, service_role_key: str) -> None:
        self._client = httpx.Client(
            base_url=f"{base_url}/rest/v1",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
            },
            timeout=30.0,
        )

    @classmethod
    def from_env(cls) -> "ConfigClient":
        return cls(
            base_url=os.environ["SUPABASE_URL"],
            service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )

    def list_active_projects(self) -> list[ProjectConfig]:
        response = self._client.get("/projects", params={"select": "*"})
        response.raise_for_status()
        return [self._to_project_config(row) for row in response.json()]

    def get_project_by_slug(self, slug: str) -> ProjectConfig:
        response = self._client.get("/projects", params={"slug": f"eq.{slug}", "select": "*"})
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise LookupError(f"No project with slug={slug!r}")
        return self._to_project_config(rows[0])

    def list_connections(self, project_id: str) -> list[Connection]:
        response = self._client.get(
            "/connections",
            params={"project_id": f"eq.{project_id}", "is_active": "eq.true", "select": "*"},
        )
        response.raise_for_status()
        return [
            Connection(
                id=row["id"],
                project_id=row["project_id"],
                source=row["source"],
                resource_id=row["resource_id"],
                secret_ref=row.get("secret_ref"),
                metadata=row.get("metadata") or {},
            )
            for row in response.json()
        ]

    def list_query_defs(self, project_id: str, source: str) -> list[QueryDef]:
        response = self._client.get(
            "/query_defs",
            params={
                "or": f"(project_id.eq.{project_id},project_id.is.null)",
                "source": f"eq.{source}",
                "is_active": "eq.true",
                "select": "*",
            },
        )
        response.raise_for_status()
        return [
            QueryDef(
                id=row["id"],
                project_id=row.get("project_id"),
                source=row["source"],
                report_key=row["report_key"],
                dimensions=row["dimensions"],
                metrics=row["metrics"],
                granularity=row["granularity"],
                high_cardinality=row["high_cardinality"],
                top_n=row["top_n"],
            )
            for row in response.json()
        ]

    def record_etl_run_start(self, project_id: str, source: str) -> str:
        response = self._client.post(
            "/etl_runs",
            json={"project_id": project_id, "source": source, "status": "running"},
            headers={"Prefer": "return=representation"},
        )
        response.raise_for_status()
        return response.json()[0]["id"]

    def record_etl_run_end(
        self,
        run_id: str,
        status: str,
        rows_extracted: int | None = None,
        error_message: str | None = None,
        reporting_identity_initial: str | None = None,
        reporting_identity_final: str | None = None,
        identity_restore_ok: bool | None = None,
    ) -> None:
        response = self._client.patch(
            "/etl_runs",
            params={"id": f"eq.{run_id}"},
            json={
                "status": status,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "rows_extracted": rows_extracted,
                "error_message": error_message,
                "reporting_identity_initial": reporting_identity_initial,
                "reporting_identity_final": reporting_identity_final,
                "identity_restore_ok": identity_restore_ok,
            },
        )
        response.raise_for_status()

    @staticmethod
    def _to_project_config(row: dict) -> ProjectConfig:
        return ProjectConfig(
            id=row["id"],
            slug=row["slug"],
            display_name=row["display_name"],
            timezone=row["timezone"],
            currency_code=row["currency_code"],
            hostname_allowlist=row.get("hostname_allowlist") or [],
            retention_calendar_years=row["retention_calendar_years"],
            reextraction_window_days=row["reextraction_window_days"],
            resting_reporting_identity=row["resting_reporting_identity"],
            archive_summary_on_purge=row["archive_summary_on_purge"],
        )
