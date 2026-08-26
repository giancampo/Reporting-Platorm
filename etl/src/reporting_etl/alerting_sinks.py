"""Concrete AlertSink implementations. Kept separate from alerting.py so the
rules/logic in that module stays testable without any network dependency.

action-plan.md §3: "ETL alerts must go through Cloud Monitoring
notification channels rather than a third-party email API" — a webhook
sink would be an extra vendor and, more to the point, an implicit new
payment-method risk (§2.1's binding constraint). Cloud Monitoring is
already inside the existing GCP project.

This class only WRITES the structured log entry; routing that to an actual
email requires a log-based metric + alerting policy configured once via
`gcloud` (documented in README.md, "Setup from scratch" — infrastructure
config, not application code, same treatment as the budget alert)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("reporting_etl.alerting")

# The log-based alerting policy (set up via gcloud/console, see README)
# filters on this exact label to avoid catching unrelated ERROR-severity
# logs from elsewhere in the container.
ALERT_LOG_FILTER_LABEL = "reporting_etl_alert"


class CloudMonitoringAlertSink:
    """Writes a structured, severity=ERROR log entry via Cloud Logging. A
    log-based alerting policy watching for `labels.{ALERT_LOG_FILTER_LABEL}
    = "true"` is what actually notifies a human, through a Cloud Monitoring
    notification channel (email) — no third-party API, no card."""

    def __init__(self, gcp_project_id: str | None) -> None:
        self._gcp_project_id = gcp_project_id

    @classmethod
    def from_env(cls) -> "CloudMonitoringAlertSink":
        return cls(gcp_project_id=os.environ.get("GCP_PROJECT_ID"))

    def send(self, subject: str, body: str, project_slug: str) -> None:
        logger.error("ALERT [%s] %s: %s", project_slug, subject, body)
        if not self._gcp_project_id:
            logger.error("GCP_PROJECT_ID is not set; alert was only logged locally.")
            return
        try:
            from google.cloud import logging as gcp_logging  # deferred: no credentials needed to import this module

            client = gcp_logging.Client(project=self._gcp_project_id)
            cloud_logger = client.logger("reporting-etl")
            cloud_logger.log_struct(
                {"subject": subject, "body": body, "project_slug": project_slug},
                severity="ERROR",
                labels={ALERT_LOG_FILTER_LABEL: "true"},
            )
        except Exception:
            logger.exception("Failed to write alert to Cloud Logging for project=%s", project_slug)
