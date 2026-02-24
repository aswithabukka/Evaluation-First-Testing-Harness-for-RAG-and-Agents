"""
ClassificationAdapter -- HTTP adapter for classification and moderation systems.

This adapter sends text to a classification endpoint and parses the returned
labels and confidence scores.  It is useful for evaluating content-moderation
APIs, intent classifiers, sentiment analysers, and similar label-producing
systems.

Usage in pipeline_config::

    {
        "adapter_module": "runner.adapters.classification_adapter",
        "adapter_class": "ClassificationAdapter",
        "endpoint_url": "https://my-classifier.com/api/classify",
        "auth_token": "Bearer sk-...",
        "request_template": {"text": "{{query}}"},
        "response_labels_path": "data.labels",
        "response_scores_path": "data.scores",
        "timeout": 30
    }
"""
from __future__ import annotations

from typing import Any

import httpx

from runner.adapters.base import PipelineOutput, RAGAdapter


def _extract_nested(data: dict | list, path: str) -> Any:
    """Extract a nested value using dot-notation path (e.g., 'data.labels')."""
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


class ClassificationAdapter(RAGAdapter):
    """
    HTTP adapter for classification / moderation systems.

    Sends the query text to the configured endpoint and parses the response
    to extract predicted labels and their confidence scores.  The answer
    field of ``PipelineOutput`` is set to a comma-joined string of labels,
    and the full scores mapping is placed in ``metadata``.
    """

    def __init__(
        self,
        endpoint_url: str = "",
        auth_token: str = "",
        request_template: dict[str, Any] | None = None,
        response_labels_path: str = "labels",
        response_scores_path: str = "scores",
        timeout: int = 30,
        **kwargs,
    ):
        self.endpoint_url = endpoint_url
        self.auth_token = auth_token
        self.request_template = request_template or {"text": "{{query}}"}
        self.response_labels_path = response_labels_path
        self.response_scores_path = response_scores_path
        self.timeout = timeout
        self._client: httpx.Client | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        if not self.endpoint_url:
            raise ValueError(
                "ClassificationAdapter requires 'endpoint_url' in pipeline_config"
            )
        headers: dict[str, str] = {}
        if self.auth_token:
            headers["Authorization"] = self.auth_token

        self._client = httpx.Client(timeout=self.timeout, headers=headers)

    def teardown(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # Request building
    # ------------------------------------------------------------------

    def _build_request_body(self, query: str, context: dict) -> dict:
        """Replace ``{{query}}`` and ``{{context.*}}`` placeholders in the template."""

        def _replace(value: Any) -> Any:
            if isinstance(value, str):
                value = value.replace("{{query}}", query)
                for key, val in context.items():
                    value = value.replace(f"{{{{context.{key}}}}}", str(val))
                return value
            if isinstance(value, dict):
                return {k: _replace(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_replace(v) for v in value]
            return value

        return _replace(self.request_template)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, query: str, context: dict) -> PipelineOutput:
        if self._client is None:
            raise RuntimeError(
                "ClassificationAdapter.setup() must be called before run()"
            )

        body = self._build_request_body(query, context)
        response = self._client.post(self.endpoint_url, json=body)
        response.raise_for_status()
        data = response.json()

        # Extract labels
        raw_labels = _extract_nested(data, self.response_labels_path)
        if isinstance(raw_labels, list):
            labels = [str(lbl) for lbl in raw_labels]
        elif raw_labels is not None:
            labels = [str(raw_labels)]
        else:
            labels = []

        # Extract scores
        raw_scores = _extract_nested(data, self.response_scores_path)
        if isinstance(raw_scores, dict):
            scores = {str(k): v for k, v in raw_scores.items()}
        elif isinstance(raw_scores, list):
            # Pair scores with labels positionally when scores is a list
            scores = {
                labels[i] if i < len(labels) else str(i): s
                for i, s in enumerate(raw_scores)
            }
        else:
            scores = {}

        answer = ", ".join(labels) if labels else ""

        return PipelineOutput(
            answer=answer,
            metadata={
                "endpoint_url": self.endpoint_url,
                "status_code": response.status_code,
                "latency_ms": int(response.elapsed.total_seconds() * 1000),
                "labels": labels,
                "scores": scores,
            },
        )
