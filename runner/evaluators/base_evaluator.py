"""
Base evaluator contract.

`MetricScores` keeps legacy RAG fields (faithfulness, answer_relevancy,
context_precision, context_recall) for backward compatibility with existing
callers, AND carries a generic `scores` dict so non-RAG evaluators stop
dumping everything into `custom`.

Every result also carries:

* ``error``     — non-None when the evaluator could not produce a score
                  (distinguishes "judge failed" from "score is legitimately 0.0").
* ``version``   — evaluator version; pinned in the run manifest for reproducibility.
* ``cost_usd``  — dollars spent by this evaluator on this case (LLM judges only).
* ``latency_ms``— wall-clock spent in the evaluator for this case.
* ``metadata``  — free-form bag (prompt hash, judge model id, seed, etc.).

Callers that only look at legacy attributes continue to work unchanged.
New evaluators should write into ``scores`` and leave legacy fields ``None``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EvalError:
    """Why an evaluation failed. None score + this object = do not gate on this row."""

    type: str
    message: str
    retryable: bool = False


@dataclass
class MetricScores:
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    custom: dict = field(default_factory=dict)

    scores: dict[str, float | None] = field(default_factory=dict)
    error: EvalError | None = None
    version: str = "1"
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    def get(self, name: str) -> float | None:
        if name in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
            return getattr(self, name)
        if name in self.scores:
            return self.scores[name]
        return self.custom.get(name)


class BaseEvaluator(ABC):
    name: str = "base"
    version: str = "1"

    @abstractmethod
    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        """Evaluate a batch of test cases. Returns one MetricScores per case."""
        ...
