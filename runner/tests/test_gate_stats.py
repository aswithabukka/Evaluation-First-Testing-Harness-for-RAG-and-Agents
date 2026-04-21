"""Tests for runner/gate/stats.py — significance-gate decisions."""
from __future__ import annotations

from runner.gate.stats import bootstrap_ci, mann_whitney_u, significance_gate


def test_bootstrap_ci_brackets_mean():
    vals = [0.8, 0.82, 0.79, 0.81, 0.83, 0.78, 0.80, 0.81, 0.82, 0.79]
    point, lo, hi = bootstrap_ci(vals, iterations=1000, seed=1)
    assert lo <= point <= hi
    assert hi - lo < 0.1  # tight dataset -> tight CI


def test_bootstrap_ci_empty_input():
    p, lo, hi = bootstrap_ci([])
    assert (p, lo, hi) == (0.0, 0.0, 0.0)


def test_bootstrap_ci_ignores_nones():
    vals = [None, 0.8, 0.9, None, 0.85]
    p, _, _ = bootstrap_ci(vals, iterations=500)
    assert 0.8 <= p <= 0.9


def test_mann_whitney_detects_shift():
    lower = [0.60] * 10
    higher = [0.90] * 10
    _, p = mann_whitney_u(lower, higher)
    assert p < 0.01


def test_mann_whitney_no_shift():
    a = [0.80, 0.82, 0.81, 0.83, 0.79, 0.80, 0.82, 0.81, 0.80, 0.83]
    b = [0.81, 0.80, 0.82, 0.79, 0.83, 0.81, 0.80, 0.82, 0.81, 0.80]
    _, p = mann_whitney_u(a, b)
    assert p > 0.05  # should NOT flag noise as a regression


def test_gate_passes_above_threshold():
    current = [0.85, 0.88, 0.87, 0.86, 0.89, 0.85, 0.87, 0.86, 0.88, 0.87]
    d = significance_gate(current, baseline=None, threshold=0.80)
    assert d.passed
    assert d.ci_lower >= 0.80


def test_gate_fails_below_threshold():
    current = [0.60, 0.62, 0.58, 0.61, 0.59] * 2
    d = significance_gate(current, baseline=None, threshold=0.80)
    assert not d.passed
    assert "threshold violated" in d.reason


def test_gate_passes_small_noise_regression():
    """Noise-level drop vs baseline should NOT fail the gate."""
    baseline = [0.85, 0.86, 0.85, 0.87, 0.86, 0.85, 0.86, 0.85, 0.87, 0.86]
    current = [0.85, 0.85, 0.84, 0.86, 0.85, 0.86, 0.85, 0.86, 0.85, 0.86]
    d = significance_gate(current, baseline=baseline, threshold=0.80)
    assert d.passed


def test_gate_fails_significant_regression():
    baseline = [0.85, 0.86, 0.87, 0.85, 0.86, 0.87, 0.85, 0.86, 0.87, 0.85]
    current = [0.60, 0.62, 0.61, 0.59, 0.63, 0.60, 0.61, 0.62, 0.60, 0.61]
    d = significance_gate(current, baseline=baseline, threshold=0.50)
    assert not d.passed
    assert d.p_value is not None and d.p_value < 0.05
