"""
ChatbotAdapter -- multi-turn HTTP adapter for conversational AI systems.

This adapter manages session state across multiple turns, sending the full
conversation history with each request.  It is designed for chatbot endpoints
that expect a ``session_id`` (or equivalent) header and a list of prior
messages in the request body.

Usage in pipeline_config::

    {
        "adapter_module": "runner.adapters.chatbot_adapter",
        "adapter_class": "ChatbotAdapter",
        "endpoint_url": "https://my-chatbot.com/api/chat",
        "auth_token": "Bearer sk-...",
        "session_header": "X-Session-Id",
        "request_template": {
            "message": "{{query}}",
            "history": "{{history}}"
        },
        "response_answer_path": "data.reply",
        "timeout": 30
    }
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx

from runner.adapters.base import PipelineOutput, RAGAdapter


def _extract_nested(data: dict | list, path: str) -> Any:
    """Extract a nested value using dot-notation path (e.g., 'data.reply')."""
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


class ChatbotAdapter(RAGAdapter):
    """
    Multi-turn HTTP adapter for conversational AI systems.

    Maintains a running conversation history and a session identifier that
    are sent with every request so the remote endpoint can track dialogue
    state.  After each call the user query and assistant reply are appended
    to ``turn_history`` which is returned inside ``PipelineOutput``.
    """

    def __init__(
        self,
        endpoint_url: str = "",
        auth_token: str = "",
        session_header: str = "X-Session-Id",
        request_template: dict[str, Any] | None = None,
        response_answer_path: str = "answer",
        timeout: int = 30,
        **kwargs,
    ):
        self.endpoint_url = endpoint_url
        self.auth_token = auth_token
        self.session_header = session_header
        self.request_template = request_template or {
            "message": "{{query}}",
            "history": "{{history}}",
        }
        self.response_answer_path = response_answer_path
        self.timeout = timeout

        # Mutable state -- reset on each setup()
        self.session_id: str = ""
        self._history: list[dict] = []
        self._client: httpx.Client | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        if not self.endpoint_url:
            raise ValueError(
                "ChatbotAdapter requires 'endpoint_url' in pipeline_config"
            )
        self.session_id = uuid.uuid4().hex
        self._history = []

        headers: dict[str, str] = {}
        if self.auth_token:
            headers["Authorization"] = self.auth_token
        headers[self.session_header] = self.session_id

        self._client = httpx.Client(timeout=self.timeout, headers=headers)

    def teardown(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
        self._history = []

    # ------------------------------------------------------------------
    # Request building
    # ------------------------------------------------------------------

    def _build_request_body(self, query: str, context: dict) -> dict:
        """Replace ``{{query}}``, ``{{history}}``, and ``{{context.*}}`` placeholders."""

        def _replace(value: Any) -> Any:
            if isinstance(value, str):
                if value == "{{history}}":
                    return list(self._history)
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
                "ChatbotAdapter.setup() must be called before run()"
            )

        body = self._build_request_body(query, context)
        response = self._client.post(self.endpoint_url, json=body)
        response.raise_for_status()
        data = response.json()

        # Extract answer
        answer = _extract_nested(data, self.response_answer_path)
        if answer is None:
            answer = str(data)

        # Append this turn to the running history
        self._history.append({"role": "user", "content": query})
        self._history.append({"role": "assistant", "content": str(answer)})

        return PipelineOutput(
            answer=str(answer),
            turn_history=list(self._history),
            metadata={
                "endpoint_url": self.endpoint_url,
                "session_id": self.session_id,
                "status_code": response.status_code,
                "latency_ms": int(response.elapsed.total_seconds() * 1000),
                "turn_number": len(self._history) // 2,
            },
        )
