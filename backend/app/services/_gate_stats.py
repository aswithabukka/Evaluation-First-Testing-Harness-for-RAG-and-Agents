"""
Statistical helpers for the release gate.

Deliberately mirrors ``runner/gate/stats.py`` rather than importing it —
the backend and runner are separate deployables and we don't want a
cross-package import dependency. The two implementations must stay in sync
on the math; the top-level tests in ``runner/tests/test_gate_stats.py`` pin
the contract.

Pure Python, no numpy / scipy, deterministic seeds — so gate decisions are
auditable and reproducible.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class GateStat:
    passed: bool
    reason: str
    point_estimate: float
    ci_lower: float | None = None
    ci_upper: float | None = None
    p_value: float | None = None
    sample_size: int = 0
    baseline_size: int = 0


def bootstrap_ci(
    values: list[float],
    *,
    confidence: float = 0.95,
    iterations: int = 2000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI for the mean of ``values``.
    Returns ``(point, lo, hi)``; empty input returns zeros.
    """
    clean = [v for v in values if v is not None and not _isnan(v)]
    if not clean:
        return 0.0, 0.0, 0.0

    rng = random.Random(seed)
    n = len(clean)
    means: list[float] = []
    for _ in range(iterations):
        sample = [clean[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)

    means.sort()
    alpha = 1.0 - confidence
    lo = means[int((alpha / 2.0) * iterations)]
    hi = means[min(int((1.0 - alpha / 2.0) * iterations), iterations - 1)]
    point = sum(clean) / n
    return point, lo, hi


def mann_whitney_u(current: list[float], baseline: list[float]) -> tuple[float, float]:
    """Two-sided Mann-Whitney U test with tie correction. Returns ``(U, p)``."""
    c = [v for v in current if v is not None and not _isnan(v)]
    b = [v for v in baseline if v is not None and not _isnan(v)]
    n1, n2 = len(c), len(b)
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0

    combined = [(v, 0) for v in c] + [(v, 1) for v in b]
    combined.sort(key=lambda x: x[0])

    ranks: list[float] = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1

    r1 = sum(ranks[i] for i in range(len(combined)) if combined[i][1] == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    mu = n1 * n2 / 2.0
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    if sigma == 0:
        return u, 1.0
    z = (u - mu) / sigma
    p = 2.0 * (1.0 - _normal_cdf(abs(z)))
    return u, max(0.0, min(1.0, p))


def significance_gate(
    current: list[float],
    baseline: list[float] | None,
    *,
    threshold: float,
    higher_is_better: bool = True,
    p_threshold: float = 0.05,
    confidence: float = 0.95,
) -> GateStat:
    """See ``runner/gate/stats.py::significance_gate`` for full rationale."""
    point, lo, hi = bootstrap_ci(current, confidence=confidence)
    n_curr = len([v for v in current if v is not None])

    if higher_is_better:
        abs_pass = lo >= threshold
        abs_reason = f"ci_lower={lo:.3f} {'>=' if abs_pass else '<'} threshold={threshold:.3f}"
    else:
        abs_pass = hi <= threshold
        abs_reason = f"ci_upper={hi:.3f} {'<=' if abs_pass else '>'} threshold={threshold:.3f}"

    p_value: float | None = None
    baseline_reason = ""
    baseline_size = 0
    baseline_regression = False
    if baseline:
        baseline_size = len([v for v in baseline if v is not None])
        if baseline_size:
            b_point = sum(v for v in baseline if v is not None) / baseline_size
        else:
            b_point = 0.0
        _, p_value = mann_whitney_u(current, baseline)
        regressed = point < b_point if higher_is_better else point > b_point
        baseline_regression = regressed and p_value is not None and p_value < p_threshold
        baseline_reason = (
            f"baseline_mean={b_point:.3f} current_mean={point:.3f} p={p_value:.3f}"
        )

    if baseline_regression:
        return GateStat(
            passed=False,
            reason=f"significant regression vs. baseline ({baseline_reason})",
            point_estimate=point,
            ci_lower=lo, ci_upper=hi, p_value=p_value,
            sample_size=n_curr, baseline_size=baseline_size,
        )
    if not abs_pass:
        return GateStat(
            passed=False,
            reason=f"threshold violated ({abs_reason})",
            point_estimate=point,
            ci_lower=lo, ci_upper=hi, p_value=p_value,
            sample_size=n_curr, baseline_size=baseline_size,
        )
    return GateStat(
        passed=True,
        reason=f"ok ({abs_reason}{'; ' + baseline_reason if baseline_reason else ''})",
        point_estimate=point,
        ci_lower=lo, ci_upper=hi, p_value=p_value,
        sample_size=n_curr, baseline_size=baseline_size,
    )


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _isnan(x: float) -> bool:
    return isinstance(x, float) and math.isnan(x)
