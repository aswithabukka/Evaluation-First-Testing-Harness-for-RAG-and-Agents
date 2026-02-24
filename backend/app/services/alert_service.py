"""
Alert service — sends notifications when evaluation metrics breach thresholds.

Supports:
  - Slack/Teams/generic webhook (ALERT_WEBHOOK_URL)
  - Extensible for email, PagerDuty, etc.
"""
import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AlertService:
    """Sends threshold breach alerts to configured channels."""

    @staticmethod
    def check_and_alert(
        run_id: str,
        test_set_name: str,
        pipeline_version: str | None,
        summary_metrics: dict[str, Any],
        thresholds: dict[str, float],
    ) -> list[dict]:
        """
        Compare summary metrics against thresholds and send alerts for breaches.
        Returns list of breach details.
        """
        breaches = []
        metric_labels = {
            "avg_faithfulness": ("faithfulness", "Faithfulness"),
            "avg_answer_relevancy": ("answer_relevancy", "Answer Relevancy"),
            "avg_context_precision": ("context_precision", "Context Precision"),
            "avg_context_recall": ("context_recall", "Context Recall"),
            "pass_rate": ("pass_rate", "Pass Rate"),
        }

        for summary_key, (threshold_key, label) in metric_labels.items():
            actual = summary_metrics.get(summary_key)
            threshold = thresholds.get(threshold_key)
            if actual is not None and threshold is not None and actual < threshold:
                breaches.append({
                    "metric": label,
                    "actual": round(actual, 4),
                    "threshold": threshold,
                    "deficit": round(threshold - actual, 4),
                })

        if breaches:
            AlertService._send_alert(
                run_id=run_id,
                test_set_name=test_set_name,
                pipeline_version=pipeline_version,
                breaches=breaches,
            )

        return breaches

    @staticmethod
    def _send_alert(
        run_id: str,
        test_set_name: str,
        pipeline_version: str | None,
        breaches: list[dict],
    ) -> None:
        """Send alert to all configured channels."""
        if settings.ALERT_WEBHOOK_URL:
            AlertService._send_webhook(
                run_id=run_id,
                test_set_name=test_set_name,
                pipeline_version=pipeline_version,
                breaches=breaches,
            )

    @staticmethod
    def _send_webhook(
        run_id: str,
        test_set_name: str,
        pipeline_version: str | None,
        breaches: list[dict],
    ) -> None:
        """Send alert to Slack/Teams/generic webhook."""
        breach_lines = []
        for b in breaches:
            breach_lines.append(
                f"  - {b['metric']}: {b['actual']:.2%} (threshold: {b['threshold']:.2%}, deficit: -{b['deficit']:.2%})"
            )

        message = (
            f"*Evaluation Alert — Threshold Breach*\n"
            f"Test Set: {test_set_name}\n"
            f"Pipeline: {pipeline_version or 'unknown'}\n"
            f"Run ID: `{run_id}`\n\n"
            f"Breached metrics:\n" + "\n".join(breach_lines)
        )

        # Slack-compatible payload (also works with many generic webhooks)
        payload = {"text": message}

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    settings.ALERT_WEBHOOK_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code >= 400:
                    logger.warning(
                        f"Alert webhook returned {resp.status_code}: {resp.text}"
                    )
        except Exception as exc:
            logger.error(f"Failed to send alert webhook: {exc}")
