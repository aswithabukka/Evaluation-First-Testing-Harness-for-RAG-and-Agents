"""Tests for the new confusion matrix + MCC in ClassificationEvaluator."""
from __future__ import annotations

import pytest

from runner.evaluators.classification_evaluator import ClassificationEvaluator


def test_perfect_mcc_is_one():
    ev = ClassificationEvaluator()
    out = ev.evaluate_batch(
        ["cat", "dog", "cat", "dog"],
        ["cat", "dog", "cat", "dog"],
    )
    assert out["matthews_corrcoef"] == pytest.approx(1.0)


def test_worst_mcc_is_minus_one_ish():
    """Always-wrong binary classifier — MCC should approach -1."""
    ev = ClassificationEvaluator()
    out = ev.evaluate_batch(
        ["cat", "dog", "cat", "dog", "cat", "dog"],
        ["dog", "cat", "dog", "cat", "dog", "cat"],
    )
    assert out["matthews_corrcoef"] <= -0.9


def test_confusion_matrix_counts():
    ev = ClassificationEvaluator()
    out = ev.evaluate_batch(
        ["cat", "cat", "dog", "dog"],
        ["cat", "dog", "dog", "dog"],
    )
    cm = out["confusion_matrix"]
    # Row "cat" in ground truth: 1 predicted cat correctly.
    assert cm["cat"]["cat"] == 1
    # Row "dog" in ground truth: 1 predicted cat (wrong), 2 predicted dog.
    assert cm["dog"]["cat"] == 1
    assert cm["dog"]["dog"] == 2
