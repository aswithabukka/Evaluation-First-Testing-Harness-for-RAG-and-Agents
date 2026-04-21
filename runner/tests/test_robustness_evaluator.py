"""Tests for RobustnessEvaluator."""
from __future__ import annotations

from runner.evaluators.robustness_evaluator import (
    RobustnessEvaluator,
    adversarial_injection_suffix,
    paraphrase_typo,
)


def test_identical_paraphrase_perfect():
    tc = {"answer": "Paris is the capital of France.",
          "paraphrase_answers": ["Paris is the capital of France."]}
    ms = RobustnessEvaluator().evaluate_batch([tc])[0]
    assert ms.scores["paraphrase_consistency"] == 1.0


def test_different_paraphrase_low():
    tc = {"answer": "Paris is the capital of France.",
          "paraphrase_answers": ["I don't know."]}
    ms = RobustnessEvaluator().evaluate_batch([tc])[0]
    assert ms.scores["paraphrase_consistency"] < 0.3


def test_typo_perturber_deterministic():
    out1 = paraphrase_typo("this is a simple sentence with words", seed=1)
    out2 = paraphrase_typo("this is a simple sentence with words", seed=1)
    assert out1 == out2


def test_injection_suffix_contains_original():
    out = adversarial_injection_suffix("what is 2+2")
    assert "what is 2+2" in out
    assert "ignore all previous" in out.lower()


def test_missing_baseline_returns_error():
    ms = RobustnessEvaluator().evaluate_batch([{}])[0]
    assert ms.error is not None
