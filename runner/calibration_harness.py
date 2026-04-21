"""
Judge calibration harness.

Every LLM judge drifts — model updates, prompt tweaks, or sampling changes
silently move its scores relative to human judgement. This harness runs the
judge against a small human-labeled gold set and reports correlation.

Workflow:
    1. Maintain a gold file: list of {query, answer, contexts?, human_score}.
       Human scores are 0..1.
    2. Run ``calibrate(evaluator, gold_file)`` — returns Spearman + Kendall
       correlation and per-case deltas.
    3. Fail CI (or post a warning) when correlation drops below a threshold.

Gold file is JSONL (one JSON object per line) for easy appending:
    {"id": "q_042", "query": "...", "answer": "...", "contexts": [...], "human_score": 0.8}

Correlation functions are pure Python — no scipy. Spearman and Kendall are
both implemented because they catch different failure modes:

* Spearman — monotonic agreement.
* Kendall — concordant-pair agreement; more robust on small samples.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CalibrationResult:
    n: int
    judge_scores: list[float | None]
    human_scores: list[float]
    spearman: float | None
    kendall: float | None
    mean_abs_error: float | None
    per_case: list[dict]


def load_gold(path: str | Path) -> list[dict]:
    cases: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def calibrate(
    evaluator: Any,
    *,
    gold_cases: list[dict],
    metric_key: str = "llm_judge",
) -> CalibrationResult:
    """Score every gold case with ``evaluator`` and compare to human scores.

    ``evaluator`` must expose ``evaluate_batch(test_cases) -> list[MetricScores]``.
    ``metric_key`` is the key on ``MetricScores.scores`` to pull.
    """
    results = evaluator.evaluate_batch(gold_cases)
    judge_scores: list[float | None] = []
    human_scores: list[float] = []
    per_case: list[dict] = []

    for case, ms in zip(gold_cases, results):
        j = ms.scores.get(metric_key) if hasattr(ms, "scores") else None
        h = float(case.get("human_score", 0.0))
        judge_scores.append(j)
        human_scores.append(h)
        per_case.append({
            "id": case.get("id"),
            "judge": j,
            "human": h,
            "delta": (j - h) if j is not None else None,
        })

    paired = [(j, h) for j, h in zip(judge_scores, human_scores) if j is not None]
    if len(paired) < 3:
        return CalibrationResult(
            n=len(gold_cases),
            judge_scores=judge_scores,
            human_scores=human_scores,
            spearman=None, kendall=None, mean_abs_error=None,
            per_case=per_case,
        )

    j_vals = [p[0] for p in paired]
    h_vals = [p[1] for p in paired]

    return CalibrationResult(
        n=len(gold_cases),
        judge_scores=judge_scores,
        human_scores=human_scores,
        spearman=_spearman(j_vals, h_vals),
        kendall=_kendall_tau(j_vals, h_vals),
        mean_abs_error=sum(abs(j - h) for j, h in paired) / len(paired),
        per_case=per_case,
    )


# ---------------------------------------------------------------- correlations


def _rank(values: list[float]) -> list[float]:
    """Average-rank on ties — the standard Spearman-friendly ranking."""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _spearman(x: list[float], y: list[float]) -> float:
    rx = _rank(x)
    ry = _rank(y)
    return _pearson(rx, ry)


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n == 0:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = sum((xi - mx) ** 2 for xi in x)
    dy = sum((yi - my) ** 2 for yi in y)
    if dx == 0 or dy == 0:
        return 0.0
    return num / ((dx ** 0.5) * (dy ** 0.5))


def _kendall_tau(x: list[float], y: list[float]) -> float:
    """Tau-b: handles ties. Pure-Python O(n²) — fine for gold sets of a few hundred."""
    n = len(x)
    if n < 2:
        return 0.0
    concordant = 0
    discordant = 0
    ties_x = 0
    ties_y = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[i] - x[j]
            dy = y[i] - y[j]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                ties_x += 1
            elif dy == 0:
                ties_y += 1
            elif (dx > 0) == (dy > 0):
                concordant += 1
            else:
                discordant += 1
    denom = ((concordant + discordant + ties_x) * (concordant + discordant + ties_y)) ** 0.5
    if denom == 0:
        return 0.0
    return (concordant - discordant) / denom
