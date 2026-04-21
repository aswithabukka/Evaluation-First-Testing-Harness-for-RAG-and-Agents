"""Tests for the trajectory (agent) evaluator."""
from __future__ import annotations

from runner.evaluators.trajectory_evaluator import TrajectoryEvaluator


def test_perfect_trajectory():
    tc = {
        "predicted_tool_calls": [{"name": "search"}, {"name": "fetch"}, {"name": "answer"}],
        "expected_tool_calls":  [{"name": "search"}, {"name": "fetch"}, {"name": "answer"}],
    }
    ms = TrajectoryEvaluator().evaluate_batch([tc])[0]
    assert ms.scores["trajectory_similarity"] == 1.0
    assert ms.scores["argument_semantic_match"] == 1.0


def test_wrong_order_penalised():
    tc = {
        "predicted_tool_calls": [{"name": "fetch"}, {"name": "search"}, {"name": "answer"}],
        "expected_tool_calls":  [{"name": "search"}, {"name": "fetch"}, {"name": "answer"}],
    }
    ms = TrajectoryEvaluator().evaluate_batch([tc])[0]
    assert 0.0 < ms.scores["trajectory_similarity"] < 1.0


def test_argument_semantic_match():
    tc = {
        "predicted_tool_calls": [{"name": "search", "arguments": {"q": "hello"}}],
        "expected_tool_calls":  [{"name": "search", "arguments": {"q": "Hello"}}],
    }
    ms = TrajectoryEvaluator().evaluate_batch([tc])[0]
    # "hello" vs "Hello" should match (string-normalised).
    assert ms.scores["argument_semantic_match"] == 1.0


def test_argument_mismatch_partial():
    tc = {
        "predicted_tool_calls": [{"name": "search", "arguments": {"q": "a", "limit": 10}}],
        "expected_tool_calls":  [{"name": "search", "arguments": {"q": "a", "limit": 20}}],
    }
    ms = TrajectoryEvaluator().evaluate_batch([tc])[0]
    assert ms.scores["argument_semantic_match"] == 0.5  # 1 of 2 args match


def test_empty_trajectories():
    ms = TrajectoryEvaluator().evaluate_batch([{"predicted_tool_calls": [], "expected_tool_calls": []}])[0]
    assert ms.scores["trajectory_similarity"] == 1.0
