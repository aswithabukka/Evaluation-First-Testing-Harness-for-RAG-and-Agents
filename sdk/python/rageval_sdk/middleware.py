"""
ASGI middleware for auto-logging AI system responses.

Usage with FastAPI:
    from rageval_sdk import RagEvalClient, FastAPIMiddleware

    client = RagEvalClient(api_url="...", api_key="...")
    app.add_middleware(
        FastAPIMiddleware,
        client=client,
        source="my-api",
        query_path="query",          # JSON field name for the query
        answer_path="answer",        # JSON field name for the answer
        route_filter="/api/chat",    # Only log requests to this route
    )
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from rageval_sdk.client import RagEvalClient


class FastAPIMiddleware:
    """
    ASGI middleware that auto-logs request/response pairs to the eval harness.

    Only logs POST requests whose path starts with route_filter.
    Extracts query from request body and answer from response body
    using configurable field paths.
    """

    def __init__(
        self,
        app,
        client: RagEvalClient,
        source: str = "api",
        query_path: str = "query",
        answer_path: str = "answer",
        contexts_path: str | None = "contexts",
        route_filter: str = "/api/",
    ):
        self.app = app
        self.client = client
        self.source = source
        self.query_path = query_path
        self.answer_path = answer_path
        self.contexts_path = contexts_path
        self.route_filter = route_filter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        if method != "POST" or not path.startswith(self.route_filter):
            await self.app(scope, receive, send)
            return

        start_time = time.monotonic()

        # Capture request body
        request_body = b""
        async def receive_wrapper():
            nonlocal request_body
            message = await receive()
            if message.get("type") == "http.request":
                request_body += message.get("body", b"")
            return message

        # Capture response body
        response_body = b""
        response_status = 200

        async def send_wrapper(message):
            nonlocal response_body, response_status
            if message.get("type") == "http.response.start":
                response_status = message.get("status", 200)
            elif message.get("type") == "http.response.body":
                response_body += message.get("body", b"")
            await send(message)

        await self.app(scope, receive_wrapper, send_wrapper)

        # Log the interaction
        latency_ms = int((time.monotonic() - start_time) * 1000)
        try:
            req_data = json.loads(request_body) if request_body else {}
            res_data = json.loads(response_body) if response_body else {}

            query = self._extract(req_data, self.query_path) or ""
            answer = self._extract(res_data, self.answer_path) or ""
            contexts = None
            if self.contexts_path:
                raw = self._extract(res_data, self.contexts_path)
                if isinstance(raw, list):
                    contexts = [str(c) for c in raw]

            if query and answer:
                self.client.log(
                    source=self.source,
                    query=query,
                    answer=answer,
                    contexts=contexts,
                    latency_ms=latency_ms,
                    is_error=response_status >= 400,
                    metadata={"path": path, "status": response_status},
                )
        except Exception:
            pass  # Never break the request pipeline

    @staticmethod
    def _extract(data: dict, path: str) -> Any:
        current = data
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current
