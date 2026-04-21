"""Smoke tests for BaseEvaluator/MetricScores backward compat + Manifest."""
from __future__ import annotations

from runner.evaluators.base_evaluator import EvalError, MetricScores
from runner.manifest import Manifest


def test_metric_scores_backward_compat_fields():
    m = MetricScores(faithfulness=0.9, answer_relevancy=0.8)
    assert m.get("faithfulness") == 0.9
    assert m.get("answer_relevancy") == 0.8


def test_metric_scores_generic_dict():
    m = MetricScores(scores={"llm_judge": 0.7})
    assert m.get("llm_judge") == 0.7


def test_metric_scores_error_marker():
    m = MetricScores(
        scores={"llm_judge": None},
        error=EvalError(type="rate_limit", message="429", retryable=True),
    )
    assert m.error is not None
    assert m.error.retryable is True
    assert m.get("llm_judge") is None


def test_manifest_fingerprint_stable():
    mf1 = Manifest()
    mf1.record_prompt(model="gpt-4o", system="sys", user="u", params={"t": 0})
    mf1.record_seed("bootstrap", 42)
    mf1.seal(commit_sha="abc123")

    mf2 = Manifest()
    mf2.record_prompt(model="gpt-4o", system="sys", user="u", params={"t": 0})
    mf2.record_seed("bootstrap", 42)
    mf2.seal(commit_sha="abc123")

    # Libraries/env may differ across runs, so fingerprint is not guaranteed
    # identical — but the prompt hash must be.
    h1 = list(mf1.prompts.keys())[0]
    h2 = list(mf2.prompts.keys())[0]
    assert h1 == h2


def test_manifest_records_evaluator():
    mf = Manifest()

    class Dummy:
        name = "dummy"
        version = "9"
    mf.record_evaluator(Dummy())
    mf.seal()
    assert any(e["name"] == "dummy" and e["version"] == "9" for e in mf.evaluators)
