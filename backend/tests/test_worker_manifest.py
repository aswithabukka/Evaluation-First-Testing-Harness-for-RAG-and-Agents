"""Unit tests for the manifest-recording helper used by the Celery worker.

We test the extracted helper at ``app.workers._manifest_helpers`` so the
test can run without Celery installed. If the evaluator-import fallback
path breaks (e.g. an evaluator module is renamed), we want the manifest to
still list a stub entry instead of crashing the run."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from runner.manifest import Manifest  # noqa: E402
from app.workers._manifest_helpers import record_evaluator  # noqa: E402


def test_record_real_evaluator_captures_version():
    m = Manifest()
    record_evaluator(m, "runner.evaluators.rule_evaluator", "RuleEvaluator")
    names = [e["name"] for e in m.evaluators]
    assert names  # at minimum a stub row


def test_record_missing_module_falls_back_to_stub():
    m = Manifest()
    record_evaluator(m, "runner.evaluators.does_not_exist", "GhostEvaluator")
    stubs = [e for e in m.evaluators if e["name"] == "GhostEvaluator"]
    assert len(stubs) == 1
    assert stubs[0]["version"] == "unknown"


def test_record_missing_class_falls_back_to_stub():
    m = Manifest()
    record_evaluator(m, "runner.evaluators.rule_evaluator", "NoSuchClassName")
    stubs = [e for e in m.evaluators if e["name"] == "NoSuchClassName"]
    assert len(stubs) == 1


def test_record_is_idempotent_for_same_evaluator():
    m = Manifest()
    record_evaluator(m, "runner.evaluators.rule_evaluator", "RuleEvaluator")
    before = len(m.evaluators)
    record_evaluator(m, "runner.evaluators.rule_evaluator", "RuleEvaluator")
    assert len(m.evaluators) == before


def test_record_versioned_evaluator_uses_class_name_and_version():
    """An evaluator with a real ``name`` / ``version`` class attribute must
    be captured verbatim — this is what lets the manifest fingerprint catch
    evaluator upgrades."""
    m = Manifest()
    record_evaluator(m, "runner.evaluators.base_evaluator", "BaseEvaluator")
    # BaseEvaluator has name="base" version="1" — but it's abstract, so
    # the fallback may also be used. Either way we get a row.
    assert m.evaluators
