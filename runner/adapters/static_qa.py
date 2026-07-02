"""
StaticQAAdapter — fully offline, deterministic adapter for CI smoke runs.

Answers a small fixed set of questions from a built-in knowledge base via
keyword matching, and refuses prompt-injection attempts. Makes zero network
calls, so the end-to-end pipeline (CLI → API → Celery → gate) can be
exercised in CI without an OpenAI key.

Paired with ``backend/app/scripts/seed_ci_smoke.py``, which seeds the
matching "CI Smoke" test set.
"""
from __future__ import annotations

from runner.adapters.base import PipelineOutput, RAGAdapter

_REFUSAL = "I can't help with that request."

# (required keywords, answer, supporting context)
_KB: list[tuple[list[str], str, str]] = [
    (
        ["capital", "france"],
        "Paris is the capital of France.",
        "Paris is the capital and largest city of France.",
    ),
    (
        ["meters", "kilometer"],
        "One kilometer equals 1000 meters.",
        "The kilometer is a unit of length equal to 1000 meters.",
    ),
    (
        ["romeo", "juliet"],
        "Romeo and Juliet was written by William Shakespeare.",
        "Romeo and Juliet is a tragedy written by William Shakespeare early in his career.",
    ),
    (
        ["boiling", "water"],
        "Water boils at 100 degrees Celsius at sea level.",
        "At standard atmospheric pressure, water boils at 100 °C (212 °F).",
    ),
]

_INJECTION_MARKERS = ["ignore your instructions", "system prompt", "ignore previous"]


class StaticQAAdapter(RAGAdapter):
    """Deterministic lookup adapter. See module docstring."""

    def setup(self) -> None:  # nothing to initialise
        pass

    def run(self, query: str, context: dict | None = None) -> PipelineOutput:
        q = query.lower()

        if any(marker in q for marker in _INJECTION_MARKERS):
            return PipelineOutput(answer=_REFUSAL)

        for keywords, answer, kb_context in _KB:
            if all(kw in q for kw in keywords):
                return PipelineOutput(answer=answer, retrieved_contexts=[kb_context])

        return PipelineOutput(
            answer="I don't have information about that.",
            retrieved_contexts=[],
        )

    def teardown(self) -> None:
        pass
