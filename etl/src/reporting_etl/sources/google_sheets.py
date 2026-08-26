"""Google Sheets override source (action-plan.md §9). The sheet must have
columns `project_id, date, dimension_key, metric_name, value` in row 1 —
this is the fixed schema every override backend shares, so switching from
Sheets to BigQuery for a given project is a `connections` row change, not a
code change."""

from __future__ import annotations

from datetime import date, datetime

from ..overrides import OverrideRow


class GoogleSheetsOverrideSource:
    def __init__(self, spreadsheet_id: str, sheet_range: str = "Overrides!A2:E") -> None:
        self._spreadsheet_id = spreadsheet_id
        self._sheet_range = sheet_range

    def fetch(self, project_id: str, start: date, end: date) -> list[OverrideRow]:
        from googleapiclient.discovery import build  # deferred: no network/creds needed to import this module

        service = build("sheets", "v4")
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range=self._sheet_range)
            .execute()
        )
        rows = result.get("values", [])

        overrides: list[OverrideRow] = []
        for raw_row in rows:
            if len(raw_row) < 5:
                continue  # skip incomplete rows rather than failing the whole batch
            row_project_id, date_str, dimension_key, metric_name, value_str = raw_row[:5]
            if row_project_id != project_id:
                continue
            row_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            if not (start <= row_date <= end):
                continue
            overrides.append(
                OverrideRow(
                    project_id=row_project_id,
                    date=row_date,
                    dimension_key=dimension_key,
                    metric_name=metric_name,
                    value=float(value_str),
                )
            )
        return overrides
