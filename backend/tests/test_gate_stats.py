"""Contract parity tests between backend/_gate_stats.py and runner/gate/stats.py.

The two copies MUST behave identically. If this test drifts, the drift is a
real bug: two services will disagree about whether a release is shipping."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.services._gate_stats import (  # noqa: E402
    bootstrap_ci as backend_boot,
    mann_whitney_u as backend_mwu,
    significance_gate as backend_gate,
)
from runner.gate.stats import (  # noqa: E402
    bootstrap_ci as runner_boot,
    mann_whitney_u as runner_mwu,
    significance_gate as runner_gate,
)


def test_bootstrap_agrees():
    vals = [0.8, 0.82, 0.79, 0.81, 0.83, 0.78, 0.80, 0.81, 0.82, 0.79]
    assert backend_boot(vals, iterations=1000, seed=1) == runner_boot(
        vals, iterations=1000, seed=1
    )


def test_mwu_agrees():
    a = [0.6] * 10
    b = [0.9] * 10
    assert backend_mwu(a, b) == runner_mwu(a, b)


def test_gate_agrees_absolute_threshold():
    current = [0.60] * 10
    d1 = backend_gate(current, None, threshold=0.80)
    d2 = runner_gate(current, None, threshold=0.80)
    assert d1.passed == d2.passed
    assert d1.ci_lower == d2.ci_lower
    assert d1.ci_upper == d2.ci_upper


def test_gate_agrees_with_baseline():
    baseline = [0.85] * 10
    current = [0.60] * 10
    d1 = backend_gate(current, baseline, threshold=0.50)
    d2 = runner_gate(current, baseline, threshold=0.50)
    assert d1.passed == d2.passed
    assert (d1.p_value or 0) == (d2.p_value or 0)
