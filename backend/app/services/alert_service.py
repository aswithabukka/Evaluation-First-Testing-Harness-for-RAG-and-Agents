"""
Alert service — sends notifications when evaluation metrics breach thresholds.

Supports:
  - Slack/Teams/generic webhook (ALERT_WEBHOOK_URL)
  - Rich Slack Block Kit formatting for breach and completion alerts
  - Extensible for email, PagerDuty, etc.
"""
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AlertService:
    """Sends threshold breach alerts and run completion notifications."""

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
            AlertService._send_breach_alert(
                run_id=run_id,
                test_set_name=test_set_name,
                pipeline_version=pipeline_version,
                breaches=breaches,
            )

        return breaches

    @staticmethod
    def send_completion_alert(
        run_id: str,
        test_set_name: str,
        pipeline_version: str | None,
        summary_metrics: dict[str, Any],
        gate_passed: bool,
    ) -> None:
        """Send a run-completed notification (for all runs when ALERT_ON_SUCCESS is on)."""
        if not settings.ALERT_WEBHOOK_URL:
            return
        if not settings.ALERT_ON_SUCCESS and gate_passed:
            return

        pass_rate = summary_metrics.get("pass_rate", 0)
        total = summary_metrics.get("total_cases", 0)
        passed = summary_metrics.get("passed_cases", 0)
        status_emoji = ":white_check_mark:" if gate_passed else ":x:"
        status_text = "Passed" if gate_passed else "Gate Blocked"

        # Build metric fields for the summary
        metric_fields = []
        for key, value in summary_metrics.items():
            if key.startswith("avg_") and value is not None:
                label = key[4:].replace("_", " ").title()
                metric_fields.append({"type": "mrkdwn", "text": f"*{label}*\n{value:.2%}"})

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{status_emoji} Evaluation Run {status_text}", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Test Set*\n{test_set_name}"},
                    {"type": "mrkdwn", "text": f"*Pipeline*\n{pipeline_version or 'unknown'}"},
                    {"type": "mrkdwn", "text": f"*Pass Rate*\n{pass_rate:.1%} ({passed}/{total})"},
                    {"type": "mrkdwn", "text": f"*Run ID*\n`{run_id[:8]}...`"},
                ],
            },
        ]

        if metric_fields:
            # Slack limits section fields to 10; chunk if needed
            for i in range(0, len(metric_fields), 10):
                blocks.append({"type": "section", "fields": metric_fields[i:i + 10]})

        blocks.append({"type": "divider"})

        payload = {
            "text": f"Evaluation {status_text}: {test_set_name} — {pass_rate:.1%} pass rate",
            "blocks": blocks,
        }
        AlertService._post_webhook(payload)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _send_breach_alert(
        run_id: str,
        test_set_name: str,
        pipeline_version: str | None,
        breaches: list[dict],
    ) -> None:
        """Send a rich Slack Block Kit alert for threshold breaches."""
        if not settings.ALERT_WEBHOOK_URL:
            return

        breach_lines = []
        for b in breaches:
            breach_lines.append(
                f":warning: *{b['metric']}*: {b['actual']:.2%} "
                f"(threshold {b['threshold']:.2%}, deficit -{b['deficit']:.2%})"
            )

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": ":rotating_light: Threshold Breach Alert", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Test Set*\n{test_set_name}"},
                    {"type": "mrkdwn", "text": f"*Pipeline*\n{pipeline_version or 'unknown'}"},
                    {"type": "mrkdwn", "text": f"*Run ID*\n`{run_id[:8]}...`"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(breach_lines)},
            },
            {"type": "divider"},
        ]

        fallback = (
            f"Threshold Breach — {test_set_name} / {pipeline_version or 'unknown'}: "
            + ", ".join(f"{b['metric']} {b['actual']:.2%}" for b in breaches)
        )

        payload = {"text": fallback, "blocks": blocks}
        AlertService._post_webhook(payload)

    @staticmethod
    def _post_webhook(payload: dict) -> None:
        """POST a JSON payload to the configured webhook URL."""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    settings.ALERT_WEBHOOK_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code >= 400:
                    logger.warning(f"Alert webhook returned {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.error(f"Failed to send alert webhook: {exc}")
