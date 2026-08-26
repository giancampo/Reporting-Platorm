"""Concrete AlertSink implementations. Kept separate from alerting.py so the
rules/logic in that module stays testable without any network dependency."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("reporting_etl.alerting")


class WebhookAlertSink:
    """Posts to a generic incoming webhook (Slack/Discord/email-via-Zapier
    all accept this shape). URL comes from `ALERT_WEBHOOK_URL`; if unset,
    alerts are logged only — a missing webhook must never silently swallow
    an alert, so this logs at ERROR level rather than no-op-ing quietly."""

    def __init__(self, webhook_url: str | None) -> None:
        self._webhook_url = webhook_url

    @classmethod
    def from_env(cls) -> "WebhookAlertSink":
        return cls(webhook_url=os.environ.get("ALERT_WEBHOOK_URL"))

    def send(self, subject: str, body: str, project_slug: str) -> None:
        logger.error("ALERT [%s] %s: %s", project_slug, subject, body)
        if not self._webhook_url:
            logger.error("ALERT_WEBHOOK_URL is not set; alert was only logged.")
            return
        try:
            httpx.post(self._webhook_url, json={"text": f"*{subject}*\n{body}"}, timeout=10.0)
        except httpx.HTTPError:
            logger.exception("Failed to deliver alert webhook for project=%s", project_slug)
