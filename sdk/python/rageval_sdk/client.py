"""
Core SDK client for logging production AI traffic to the eval harness.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("rageval_sdk")


@dataclass
class Trace:
    """Mutable trace object for capturing Q&A data within a context manager."""
    source: str = ""
    query: str = ""
    answer: str = ""
    contexts: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: int | None = None
    confidence_score: float | None = None
    user_feedback: str | None = None
    is_error: bool = False
    error_message: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    pipeline_version: str | None = None
    _start_time: float = field(default_factory=time.monotonic)


class RagEvalClient:
    """
    Lightweight client for logging production AI traffic to the eval harness.

    Supports:
    - Single log() calls
    - Bulk log_batch() calls
    - Context manager trace() for auto-timing
    - Background async flushing (non-blocking)
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8000/api/v1",
        api_key: str | None = None,
        source: str = "default",
        pipeline_version: str | None = None,
        batch_size: int = 50,
        flush_interval: float = 10.0,
        async_mode: bool = True,
        timeout: int = 10,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.default_source = source
        self.default_pipeline_version = pipeline_version
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.timeout = timeout

        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["X-API-Key"] = api_key

        self._client = httpx.Client(
            base_url=self.api_url,
            headers=self._headers,
            timeout=self.timeout,
        )

        # Async batching
        self._queue: queue.Queue[dict] = queue.Queue()
        self._flush_thread: threading.Thread | None = None
        if async_mode:
            self._start_flush_thread()

    def _start_flush_thread(self) -> None:
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(self.flush_interval)
            self._flush_batch()

    def _flush_batch(self) -> None:
        items = []
        while not self._queue.empty() and len(items) < 500:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if not items:
            return

        try:
            self._client.post("/ingest/bulk", json={"items": items})
        except Exception as exc:
            logger.warning(f"Failed to flush batch: {exc}")
            # Re-queue items on failure
            for item in items:
                self._queue.put(item)

    def log(
        self,
        query: str,
        answer: str,
        source: str | None = None,
        contexts: list[str] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        latency_ms: int | None = None,
        confidence_score: float | None = None,
        user_feedback: str | None = None,
        is_error: bool = False,
        error_message: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        pipeline_version: str | None = None,
    ) -> None:
        """Log a single Q&A pair. Non-blocking if async_mode=True."""
        payload = {
            "source": source or self.default_source,
            "pipeline_version": pipeline_version or self.default_pipeline_version,
            "query": query,
            "answer": answer,
            "contexts": contexts,
            "tool_calls": tool_calls,
            "latency_ms": latency_ms,
            "confidence_score": confidence_score,
            "user_feedback": user_feedback,
            "is_error": is_error,
            "error_message": error_message,
            "tags": tags,
            "metadata": metadata,
            "produced_at": datetime.now(timezone.utc).isoformat(),
        }

        if self._flush_thread is not None:
            self._queue.put(payload)
            if self._queue.qsize() >= self.batch_size:
                self._flush_batch()
        else:
            # Synchronous mode
            try:
                self._client.post("/ingest", json=payload)
            except Exception as exc:
                logger.warning(f"Failed to log: {exc}")

    def log_batch(self, items: list[dict[str, Any]]) -> None:
        """Log multiple Q&A pairs at once (synchronous)."""
        try:
            self._client.post("/ingest/bulk", json={"items": items})
        except Exception as exc:
            logger.warning(f"Failed to log batch: {exc}")

    @contextmanager
    def trace(self, source: str | None = None):
        """
        Context manager that auto-captures timing.

        Usage:
            with client.trace(source="my-bot") as t:
                t.query = user_question
                answer = my_system(user_question)
                t.answer = answer
        """
        t = Trace(source=source or self.default_source)
        yield t
        # Auto-compute latency if not set
        if t.latency_ms is None:
            t.latency_ms = int((time.monotonic() - t._start_time) * 1000)
        self.log(
            query=t.query,
            answer=t.answer,
            source=t.source,
            contexts=t.contexts if t.contexts else None,
            tool_calls=t.tool_calls if t.tool_calls else None,
            latency_ms=t.latency_ms,
            confidence_score=t.confidence_score,
            user_feedback=t.user_feedback,
            is_error=t.is_error,
            error_message=t.error_message,
            tags=t.tags if t.tags else None,
            metadata=t.metadata if t.metadata else None,
            pipeline_version=t.pipeline_version or self.default_pipeline_version,
        )

    def feedback(self, query: str, answer: str, feedback: str, source: str | None = None) -> None:
        """Convenience method for logging user feedback on a response."""
        self.log(
            query=query,
            answer=answer,
            source=source,
            user_feedback=feedback,
        )

    def flush(self) -> None:
        """Force flush any pending items."""
        self._flush_batch()

    def close(self) -> None:
        """Flush remaining items and close the client."""
        self._running = False
        self.flush()
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
