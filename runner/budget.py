"""
Per-run cost + latency budgets.

The worst LLM-eval outage is a silent 10x cost spike — a prompt change
doubles tokens, self-consistency is left on, and the nightly eval bill
detonates. This module gives the runner a hard ceiling and a fast-fail
behaviour.

Usage:
    budget = Budget(max_usd=5.00, max_seconds=600)
    for case in cases:
        budget.check()         # raises BudgetExceeded if over
        scores = evaluator.evaluate_batch([case])[0]
        budget.record(scores)  # uses MetricScores.cost_usd and .latency_ms

``BudgetExceeded`` is a soft signal — the runner can catch it and mark the
run as ``partial`` rather than ``failed``, preserving whatever was evaluated
up to the limit.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    pass


@dataclass
class Budget:
    max_usd: float | None = None
    max_seconds: float | None = None
    spent_usd: float = 0.0
    started_at: float = field(default_factory=time.time)
    exceeded_reason: str | None = None

    def record(self, scores) -> None:
        """Accept either a MetricScores or a float cost."""
        if hasattr(scores, "cost_usd"):
            self.spent_usd += float(getattr(scores, "cost_usd", 0.0) or 0.0)
        else:
            self.spent_usd += float(scores or 0.0)

    def check(self) -> None:
        if self.max_usd is not None and self.spent_usd > self.max_usd:
            self.exceeded_reason = (
                f"cost ${self.spent_usd:.2f} exceeds budget ${self.max_usd:.2f}"
            )
            raise BudgetExceeded(self.exceeded_reason)
        if self.max_seconds is not None:
            elapsed = time.time() - self.started_at
            if elapsed > self.max_seconds:
                self.exceeded_reason = (
                    f"elapsed {elapsed:.0f}s exceeds budget {self.max_seconds:.0f}s"
                )
                raise BudgetExceeded(self.exceeded_reason)

    def summary(self) -> dict:
        return {
            "spent_usd": round(self.spent_usd, 4),
            "max_usd": self.max_usd,
            "elapsed_seconds": round(time.time() - self.started_at, 2),
            "max_seconds": self.max_seconds,
            "exceeded": self.exceeded_reason is not None,
            "exceeded_reason": self.exceeded_reason,
        }
