"""Tests for ECE (CalibrationEvaluator)."""
from __future__ import annotations

from runner.evaluators.calibration_evaluator import CalibrationEvaluator


def test_perfect_calibration():
    cases = (
        [{"confidence": 0.1, "correct": 0}] * 10
        + [{"confidence": 0.9, "correct": 1}] * 10
    )
    ms = CalibrationEvaluator(num_bins=10).evaluate_batch(cases)[0]
    assert ms.scores["ece"] < 0.15


def test_overconfident_model():
    """Model claims 0.95 confidence, only right 50% of the time — high ECE."""
    cases = []
    for i in range(20):
        cases.append({"confidence": 0.95, "correct": 1 if i % 2 == 0 else 0})
    ms = CalibrationEvaluator(num_bins=10).evaluate_batch(cases)[0]
    assert ms.scores["ece"] > 0.4
    assert ms.scores["overconfidence_rate"] > 0.9


def test_missing_fields_produces_error():
    ms = CalibrationEvaluator().evaluate_batch([{"foo": "bar"}])[0]
    assert ms.error is not None
    assert ms.error.type == "missing_input"
