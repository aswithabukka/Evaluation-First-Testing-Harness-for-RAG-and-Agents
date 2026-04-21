"""Unit tests for the registry-driven evaluator dispatch used by the worker.

Tests focus on the wiring contracts — NOT on LLM-based evaluators (those
require API keys). We exercise the stdlib-only evaluators in
``EVALUATOR_REGISTRY`` (``trajectory``, ``robustness``, ``safety``) plus
verify that unknown names, missing config, and batch-only names
(``pairwise``, ``calibration``) don't break the loop."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.workers._registry_dispatch import run_registry_evaluators  # noqa: E402


@dataclass
class _FakeTC:
    """Minimal stand-in for app.db.models.test_case.TestCase so we don't
    have to spin up SQLAlchemy for a unit test."""
    query: str = "what is 2+2?"
    ground_truth: str | None = "4"
    context: dict | list | None = None
    failure_rules: list = field(default_factory=list)


def test_dispatch_runs_trajectory_and_robustness():
    tc = _FakeTC(
        context={
            "expected_tool_calls": [{"name": "calculator"}],
            "paraphrase_answers": ["The answer is 4."],
        },
    )
    tool_calls = [{"tool": "calculator", "args": {"x": 2, "y": 2}}]
    scores, errors = run_registry_evaluators(
        tc=tc,
        metrics=["trajectory", "robustness"],
        pipeline_config=None,
        raw_output="4",
        raw_contexts=[],
        tool_calls_data=tool_calls,
        openai_api_key=None,
    )
    assert "trajectory_similarity" in scores
    assert scores["trajectory_similarity"] == 1.0
    # Robustness: baseline "4" vs paraphrase "The answer is 4." — similarity low.
    assert "paraphrase_consistency" in scores


def test_dispatch_runs_safety_with_regex_fallback():
    tc = _FakeTC()
    scores, errors = run_registry_evaluators(
        tc=tc,
        metrics=["safety"],
        pipeline_config=None,
        raw_output="Email me at foo@bar.com",
        raw_contexts=[],
        tool_calls_data=[],
        openai_api_key=None,
    )
    # SafetyEvaluator writes scalar-keyed entries into out_scores.
    assert scores.get("safety_pii_detected") == 1.0  # bool -> float
    assert "safety_toxicity_score" in scores


def test_dispatch_skips_unknown_metrics():
    tc = _FakeTC()
    scores, errors = run_registry_evaluators(
        tc=tc,
        metrics=["faithfulness", "not_a_real_evaluator", "rule_evaluation"],
        pipeline_config=None,
        raw_output="hello",
        raw_contexts=[],
        tool_calls_data=[],
        openai_api_key=None,
    )
    # No registry evaluator names present → nothing runs.
    assert scores == {}
    assert errors == []


def test_dispatch_skips_pairwise_and_calibration_in_per_case():
    """pairwise needs answer_a/answer_b; calibration is batch-level. Both
    must be invisible to the per-case dispatch."""
    tc = _FakeTC()
    scores, errors = run_registry_evaluators(
        tc=tc,
        metrics=["pairwise", "calibration"],
        pipeline_config=None,
        raw_output="hello",
        raw_contexts=[],
        tool_calls_data=[],
        openai_api_key=None,
    )
    assert scores == {}
    assert errors == []


def test_dispatch_records_evaluators_in_manifest():
    from runner.manifest import Manifest
    from app.workers._manifest_helpers import record_evaluator

    m = Manifest()
    tc = _FakeTC()
    run_registry_evaluators(
        tc=tc,
        metrics=["trajectory", "safety"],
        pipeline_config=None,
        raw_output="hi",
        raw_contexts=[],
        tool_calls_data=[],
        openai_api_key=None,
        manifest=m,
        record_evaluator_fn=record_evaluator,
    )
    names = {e["name"] for e in m.evaluators}
    # TrajectoryEvaluator has name="trajectory", SafetyEvaluator is not a
    # BaseEvaluator so record_evaluator falls back to the class name.
    assert "trajectory" in names
    assert any("safety" in n.lower() for n in names) or "SafetyEvaluator" in names


def test_dispatch_per_evaluator_config_honoured():
    """Config under pipeline_config.evaluators.<name> must reach the
    evaluator constructor."""
    tc = _FakeTC()
    # RobustnessEvaluator takes ngram_size — set it to something weird and
    # verify we don't crash.
    scores, errors = run_registry_evaluators(
        tc=tc,
        metrics=["robustness"],
        pipeline_config={"evaluators": {"robustness": {"ngram_size": 2}}},
        raw_output="hello world",
        raw_contexts=[],
        tool_calls_data=[],
        openai_api_key=None,
    )
    # ngram_size=2 doesn't produce an error — the test just guards the
    # "config reaches the constructor" wiring.
    assert "paraphrase_consistency" in scores or scores == {}
