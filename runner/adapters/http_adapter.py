"""
HTTPAdapter — calls any deployed AI system via HTTP for evaluation.

This adapter sends queries to a deployed endpoint and parses the response.
It supports configurable request/response field mappings so it can work
with any REST API shape.

Usage in pipeline_config:
    {
        "adapter_module": "runner.adapters.http_adapter",
        "adapter_class": "HTTPAdapter",
        "endpoint_url": "https://my-ai-system.com/api/chat",
        "method": "POST",
        "headers": {"Authorization": "Bearer sk-..."},
        "request_body_template": {"message": "{{query}}"},
        "response_answer_path": "data.answer",
        "response_contexts_path": "data.sources",
        "response_tool_calls_path": "data.tool_calls",
        "timeout": 30
    }
"""
from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from runner.adapters.base import PipelineOutput, RAGAdapter, ToolCall


def _extract_nested(data: dict | list, path: str) -> Any:
    """Extract a nested value using dot-notation path (e.g., 'data.answer')."""
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


class HTTPAdapter(RAGAdapter):
    """
    Generic HTTP adapter for evaluating any deployed AI system.

    Sends the test query to a configured HTTP endpoint and maps
    the response fields back to PipelineOutput.
    """

    def __init__(
        self,
        endpoint_url: str = "",
        method: str = "POST",
        headers: dict[str, str] | None = None,
        request_body_template: dict[str, Any] | None = None,
        response_answer_path: str = "answer",
        response_contexts_path: str | None = None,
        response_tool_calls_path: str | None = None,
        timeout: int = 30,
        **kwargs,
    ):
        self.endpoint_url = endpoint_url
        self.method = method.upper()
        self.headers = headers or {}
        self.request_body_template = request_body_template or {"query": "{{query}}"}
        self.response_answer_path = response_answer_path
        self.response_contexts_path = response_contexts_path
        self.response_tool_calls_path = response_tool_calls_path
        self.timeout = timeout
        self._client: httpx.Client | None = None

    def setup(self) -> None:
        if not self.endpoint_url:
            raise ValueError("HTTPAdapter requires 'endpoint_url' in pipeline_config")
        self._client = httpx.Client(timeout=self.timeout, headers=self.headers)

    def _build_request_body(self, query: str, context: dict) -> dict:
        """Replace {{query}} and {{context.*}} placeholders in the template."""
        def _replace(value: Any) -> Any:
            if isinstance(value, str):
                value = value.replace("{{query}}", query)
                # Replace {{context.key}} placeholders
                for key, val in context.items():
                    value = value.replace(f"{{{{context.{key}}}}}", str(val))
                return value
            if isinstance(value, dict):
                return {k: _replace(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_replace(v) for v in value]
            return value

        return _replace(self.request_body_template)

    def run(self, query: str, context: dict) -> PipelineOutput:
        if self._client is None:
            raise RuntimeError("HTTPAdapter.setup() must be called before run()")

        body = self._build_request_body(query, context)

        if self.method == "POST":
            response = self._client.post(self.endpoint_url, json=body)
        elif self.method == "GET":
            response = self._client.get(self.endpoint_url, params=body)
        else:
            raise ValueError(f"Unsupported HTTP method: {self.method}")

        response.raise_for_status()
        data = response.json()

        # Extract answer
        answer = _extract_nested(data, self.response_answer_path)
        if answer is None:
            answer = str(data)

        # Extract contexts
        contexts = []
        if self.response_contexts_path:
            raw_contexts = _extract_nested(data, self.response_contexts_path)
            if isinstance(raw_contexts, list):
                contexts = [str(c) for c in raw_contexts]
            elif raw_contexts is not None:
                contexts = [str(raw_contexts)]

        # Extract tool calls
        tool_calls = []
        if self.response_tool_calls_path:
            raw_tc = _extract_nested(data, self.response_tool_calls_path)
            if isinstance(raw_tc, list):
                for tc in raw_tc:
                    if isinstance(tc, dict):
                        tool_calls.append(ToolCall(
                            tool=tc.get("tool", tc.get("name", "unknown")),
                            args=tc.get("args", tc.get("arguments", {})),
                            result=tc.get("result"),
                        ))

        return PipelineOutput(
            answer=str(answer),
            retrieved_contexts=contexts,
            tool_calls=tool_calls,
            metadata={
                "endpoint_url": self.endpoint_url,
                "status_code": response.status_code,
                "latency_ms": int(response.elapsed.total_seconds() * 1000),
            },
        )

    def teardown(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
