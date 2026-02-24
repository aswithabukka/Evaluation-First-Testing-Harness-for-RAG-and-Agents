"""
CodeGenAdapter -- HTTP adapter for code generation systems.

This adapter sends a code prompt (or natural-language description) to a code
generation endpoint (e.g. Copilot, CodeGen, StarCoder APIs) and returns the
generated code as the answer.  The target programming language is carried in
``metadata`` so downstream evaluators can apply language-specific checks.

Usage in pipeline_config::

    {
        "adapter_module": "runner.adapters.code_gen_adapter",
        "adapter_class": "CodeGenAdapter",
        "endpoint_url": "https://my-codegen.com/api/generate",
        "auth_token": "Bearer sk-...",
        "language": "python",
        "request_template": {
            "prompt": "{{query}}",
            "language": "{{language}}"
        },
        "response_code_path": "data.code",
        "timeout": 60
    }
"""
from __future__ import annotations

from typing import Any

import httpx

from runner.adapters.base import PipelineOutput, RAGAdapter


def _extract_nested(data: dict | list, path: str) -> Any:
    """Extract a nested value using dot-notation path (e.g., 'data.code')."""
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


class CodeGenAdapter(RAGAdapter):
    """
    HTTP adapter for code generation systems (Copilot, CodeGen, StarCoder, etc.).

    Sends a code prompt to the configured endpoint, extracts the generated
    code from the response, and returns it as the ``answer`` in
    ``PipelineOutput``.  The target ``language`` is stored in ``metadata``
    so evaluators can apply language-aware checks (syntax validation, style
    linting, test execution).
    """

    def __init__(
        self,
        endpoint_url: str = "",
        auth_token: str = "",
        language: str = "python",
        request_template: dict[str, Any] | None = None,
        response_code_path: str = "code",
        timeout: int = 60,
        **kwargs,
    ):
        self.endpoint_url = endpoint_url
        self.auth_token = auth_token
        self.language = language
        self.request_template = request_template or {
            "prompt": "{{query}}",
            "language": "{{language}}",
        }
        self.response_code_path = response_code_path
        self.timeout = timeout
        self._client: httpx.Client | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        if not self.endpoint_url:
            raise ValueError(
                "CodeGenAdapter requires 'endpoint_url' in pipeline_config"
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
        """Replace ``{{query}}``, ``{{language}}``, and ``{{context.*}}`` placeholders."""

        def _replace(value: Any) -> Any:
            if isinstance(value, str):
                value = value.replace("{{query}}", query)
                value = value.replace("{{language}}", self.language)
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
                "CodeGenAdapter.setup() must be called before run()"
            )

        body = self._build_request_body(query, context)
        response = self._client.post(self.endpoint_url, json=body)
        response.raise_for_status()
        data = response.json()

        # Extract generated code
        code = _extract_nested(data, self.response_code_path)
        if code is None:
            code = str(data)

        return PipelineOutput(
            answer=str(code),
            metadata={
                "endpoint_url": self.endpoint_url,
                "status_code": response.status_code,
                "latency_ms": int(response.elapsed.total_seconds() * 1000),
                "language": self.language,
            },
        )
