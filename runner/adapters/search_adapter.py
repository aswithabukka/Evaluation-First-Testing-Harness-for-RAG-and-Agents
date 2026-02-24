"""
SearchAdapter -- HTTP adapter for search and retrieval systems.

This adapter sends a query to a search endpoint and parses the ranked list
of results from the response.  It maps each result's text into
``retrieved_contexts`` and stores document IDs and relevance scores in
``metadata`` so downstream evaluators can assess retrieval quality.

Usage in pipeline_config::

    {
        "adapter_module": "runner.adapters.search_adapter",
        "adapter_class": "SearchAdapter",
        "endpoint_url": "https://my-search.com/api/search",
        "auth_token": "Bearer sk-...",
        "request_template": {"q": "{{query}}", "top_k": 10},
        "response_results_path": "data.results",
        "response_id_field": "doc_id",
        "response_score_field": "relevance_score",
        "timeout": 30
    }
"""
from __future__ import annotations

from typing import Any

import httpx

from runner.adapters.base import PipelineOutput, RAGAdapter


def _extract_nested(data: dict | list, path: str) -> Any:
    """Extract a nested value using dot-notation path (e.g., 'data.results')."""
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


class SearchAdapter(RAGAdapter):
    """
    HTTP adapter for search / retrieval systems.

    Sends the query to the configured search endpoint and parses the ranked
    result list.  The top result's text becomes ``answer``, all result texts
    populate ``retrieved_contexts`` (preserving rank order), and document IDs
    plus relevance scores are stored in ``metadata``.
    """

    def __init__(
        self,
        endpoint_url: str = "",
        auth_token: str = "",
        request_template: dict[str, Any] | None = None,
        response_results_path: str = "results",
        response_id_field: str = "id",
        response_score_field: str = "score",
        timeout: int = 30,
        **kwargs,
    ):
        self.endpoint_url = endpoint_url
        self.auth_token = auth_token
        self.request_template = request_template or {"query": "{{query}}"}
        self.response_results_path = response_results_path
        self.response_id_field = response_id_field
        self.response_score_field = response_score_field
        self.timeout = timeout
        self._client: httpx.Client | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        if not self.endpoint_url:
            raise ValueError(
                "SearchAdapter requires 'endpoint_url' in pipeline_config"
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
    # Result text extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _result_text(result: Any) -> str:
        """Best-effort extraction of a readable string from a single result item."""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            # Try common text field names in order of preference
            for field in ("text", "content", "snippet", "body", "description", "title"):
                if field in result and result[field]:
                    return str(result[field])
            return str(result)
        return str(result)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, query: str, context: dict) -> PipelineOutput:
        if self._client is None:
            raise RuntimeError(
                "SearchAdapter.setup() must be called before run()"
            )

        body = self._build_request_body(query, context)
        response = self._client.post(self.endpoint_url, json=body)
        response.raise_for_status()
        data = response.json()

        # Extract the results list
        raw_results = _extract_nested(data, self.response_results_path)
        if not isinstance(raw_results, list):
            raw_results = []

        # Build parallel lists of texts, IDs, and scores
        contexts: list[str] = []
        ranked_ids: list[str] = []
        ranked_scores: list[float | None] = []

        for item in raw_results:
            contexts.append(self._result_text(item))
            if isinstance(item, dict):
                ranked_ids.append(str(item.get(self.response_id_field, "")))
                score = item.get(self.response_score_field)
                ranked_scores.append(float(score) if score is not None else None)
            else:
                ranked_ids.append("")
                ranked_scores.append(None)

        answer = contexts[0] if contexts else ""

        return PipelineOutput(
            answer=answer,
            retrieved_contexts=contexts,
            metadata={
                "endpoint_url": self.endpoint_url,
                "status_code": response.status_code,
                "latency_ms": int(response.elapsed.total_seconds() * 1000),
                "total_results": len(contexts),
                "ranked_ids": ranked_ids,
                "ranked_scores": ranked_scores,
            },
        )
