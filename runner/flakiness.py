"""
Flakiness detection.

Before counting a failed case as a regression signal, re-run the top-N
lowest-scoring cases `k` times and check whether the score is stable.
High-variance cases are marked flaky and excluded from gate decisions —
they're real quality signal, just not gate-able.

Design: this module is *evaluator-agnostic*. It takes a callable that scores
a single case and returns a float, plus the list of cases to re-check. It
runs each case ``k`` times and returns per-case variance.

Usage:
    from runner.flakiness import detect_flaky

    flaky = detect_flaky(
        cases=top_n_failing_cases,
        score_fn=lambda tc: evaluator.evaluate_batch([tc])[0].scores.get("llm_judge"),
        k=3,
        variance_threshold=0.05,
    )
    gate_candidates = [c for c in all_cases if c["id"] not in {f["id"] for f in flaky}]
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable


@dataclass
class FlakyCase:
    id: str
    scores: list[float | None]
    mean: float
    variance: float


def detect_flaky(
    *,
    cases: list[dict],
    score_fn: Callable[[dict], float | None],
    k: int = 3,
    variance_threshold: float = 0.05,
    id_key: str = "id",
) -> list[FlakyCase]:
    """Re-run each case ``k`` times and flag those with variance above threshold.

    Cases missing an ``id_key`` get auto-indexed ids.
    """
    flaky: list[FlakyCase] = []
    for i, case in enumerate(cases):
        case_id = str(case.get(id_key, f"case_{i}"))
        runs: list[float | None] = []
        for _ in range(k):
            try:
                runs.append(score_fn(case))
            except Exception:
                runs.append(None)

        clean = [s for s in runs if s is not None]
        if len(clean) < 2:
            continue  # not enough signal to declare flaky

        var = statistics.pvariance(clean)
        if var > variance_threshold:
            flaky.append(FlakyCase(
                id=case_id,
                scores=runs,
                mean=statistics.mean(clean),
                variance=var,
            ))
    return flaky


def rank_lowest_scoring(
    results: list[tuple[str, float | None]], top_n: int
) -> list[str]:
    """Return the top-N lowest-scoring case ids (None scores last)."""
    ranked = sorted(
        results,
        key=lambda x: (x[1] is None, x[1] if x[1] is not None else 0.0),
    )
    return [cid for cid, _ in ranked[:top_n]]
