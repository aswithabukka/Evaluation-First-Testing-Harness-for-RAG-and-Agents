"""Tests for cost budget and flakiness detection."""
from __future__ import annotations

import pytest

from runner.budget import Budget, BudgetExceeded
from runner.flakiness import detect_flaky


def test_budget_passes_within_limit():
    b = Budget(max_usd=1.0)
    for _ in range(3):
        b.record(0.10)
    b.check()
    assert b.spent_usd == pytest.approx(0.30)


def test_budget_fails_over_limit():
    b = Budget(max_usd=0.25)
    b.record(0.10)
    b.record(0.10)
    b.record(0.10)  # now 0.30 > 0.25
    with pytest.raises(BudgetExceeded):
        b.check()


def test_budget_accepts_metric_scores_object():
    class FakeMS:
        cost_usd = 0.2
    b = Budget(max_usd=1.0)
    b.record(FakeMS())
    assert b.spent_usd == pytest.approx(0.2)


def test_flakiness_flags_unstable_case():
    """Score function returns different values per call — must be flagged."""
    counter = {"n": 0}

    def unstable_score(_case):
        counter["n"] += 1
        return 0.9 if counter["n"] % 2 == 0 else 0.1

    cases = [{"id": "c1"}]
    flaky = detect_flaky(cases=cases, score_fn=unstable_score, k=4, variance_threshold=0.05)
    assert len(flaky) == 1
    assert flaky[0].id == "c1"


def test_flakiness_ignores_stable_case():
    flaky = detect_flaky(
        cases=[{"id": "c1"}],
        score_fn=lambda _: 0.85,
        k=3,
        variance_threshold=0.05,
    )
    assert flaky == []
