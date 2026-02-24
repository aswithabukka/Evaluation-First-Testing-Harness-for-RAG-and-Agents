"""
Agent Evaluator.

Computes metrics for AI agent and tool-use systems:

* **Tool Call F1** -- precision, recall, and F1 of the tools actually called
  vs. the expected tool calls.  Matches on tool name; optionally also on
  arguments.
* **Tool Call Accuracy** -- exact-match: did the agent call exactly the right
  tools in exactly the right order?
* **Argument Accuracy** -- for each correctly-called tool, what fraction of
  arguments matched the expected values?
* **Goal Accuracy** -- whether the agent achieved the stated goal (final
  answer match or task completion flag).
* **Step Efficiency** -- ratio of minimum required steps to actual steps
  taken (higher is better; >1.0 means the agent was more efficient than
  expected, which is fine).
* **Error Recovery Rate** -- fraction of error states from which the agent
  successfully recovered.

Returns:
    {"tool_call_precision": float, "tool_call_recall": float,
     "tool_call_f1": float, "tool_call_accuracy": float,
     "argument_accuracy": float, "goal_accuracy": float,
     "step_efficiency": float, "error_recovery_rate": float | None}

References:
    - Patil et al., "Gorilla: Large Language Model Connected with Massive
      APIs" (arXiv:2305.15334)
    - Qin et al., "ToolLLM: Facilitating Large Language Models to Master
      16000+ Real-world APIs" (ICLR 2024)
    - Yao et al., "ReAct: Synergizing Reasoning and Acting in Language
      Models" (ICLR 2023)
    - Jimenez et al., "SWE-bench: Can Language Models Resolve Real-World
      GitHub Issues?" (ICLR 2024) — resolved rate metric
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """Representation of a single tool/function call."""

    name: str
    arguments: dict | None = None


@dataclass
class AgentResult:
    """Container for agent evaluation scores."""

    tool_call_precision: float = 0.0
    tool_call_recall: float = 0.0
    tool_call_f1: float = 0.0
    tool_call_accuracy: float = 0.0
    argument_accuracy: float = 0.0
    goal_accuracy: float = 0.0
    step_efficiency: float = 0.0
    error_recovery_rate: float | None = None


class AgentEvaluator:
    """Evaluate AI agent behaviour: tool selection, argument passing, and
    goal completion.

    All checks use Python stdlib only — no external dependencies.

    Args:
        match_arguments: If ``True``, tool-call matching also checks that
            arguments are identical (default ``False`` — name-only matching).
        ordered: If ``True``, ``tool_call_accuracy`` requires the order to
            match (default ``False``).
    """

    def __init__(
        self,
        match_arguments: bool = False,
        ordered: bool = False,
    ) -> None:
        self._match_arguments = match_arguments
        self._ordered = ordered

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        predicted_tool_calls: list[dict],
        expected_tool_calls: list[dict],
        final_answer: str | None = None,
        expected_answer: str | None = None,
        min_steps: int | None = None,
        actual_steps: int | None = None,
        error_states: int | None = None,
        recovered_states: int | None = None,
    ) -> dict:
        """Evaluate a single agent execution trace.

        Args:
            predicted_tool_calls: Tools the agent actually called.
                Each dict has ``"name": str`` and optional ``"arguments": dict``.
            expected_tool_calls: Ground-truth tool calls.
            final_answer: The agent's final textual answer (if any).
            expected_answer: The expected final answer for goal-accuracy.
            min_steps: Minimum number of steps needed (for step efficiency).
            actual_steps: Number of steps the agent actually took.
            error_states: Total number of error states encountered.
            recovered_states: Number of error states successfully recovered from.

        Returns:
            Full metric dict.
        """
        pred_calls = [self._parse_call(c) for c in predicted_tool_calls]
        exp_calls = [self._parse_call(c) for c in expected_tool_calls]

        precision, recall, f1 = self._tool_call_f1(pred_calls, exp_calls)
        accuracy = self._tool_call_accuracy(pred_calls, exp_calls)
        arg_acc = self._argument_accuracy(pred_calls, exp_calls)
        goal = self._goal_accuracy(final_answer, expected_answer)
        efficiency = self._step_efficiency(min_steps, actual_steps)
        recovery = self._error_recovery(error_states, recovered_states)

        return {
            "tool_call_precision": precision,
            "tool_call_recall": recall,
            "tool_call_f1": f1,
            "tool_call_accuracy": accuracy,
            "argument_accuracy": arg_acc,
            "goal_accuracy": goal,
            "step_efficiency": efficiency,
            "error_recovery_rate": recovery,
        }

    def evaluate_batch(
        self,
        traces: list[dict],
    ) -> dict:
        """Evaluate multiple agent traces and return averaged metrics.

        Args:
            traces: List of dicts, each passed as kwargs to :meth:`evaluate`.

        Returns:
            Averaged metric dict.
        """
        if not traces:
            return {
                "tool_call_precision": 0.0, "tool_call_recall": 0.0,
                "tool_call_f1": 0.0, "tool_call_accuracy": 0.0,
                "argument_accuracy": 0.0, "goal_accuracy": 0.0,
                "step_efficiency": 0.0, "error_recovery_rate": None,
            }

        totals: dict[str, float] = {}
        recovery_scores: list[float] = []

        for trace in traces:
            result = self.evaluate(**trace)
            for k, v in result.items():
                if k == "error_recovery_rate":
                    if v is not None:
                        recovery_scores.append(v)
                else:
                    totals[k] = totals.get(k, 0.0) + v

        n = len(traces)
        averaged = {k: v / n for k, v in totals.items()}
        averaged["error_recovery_rate"] = (
            sum(recovery_scores) / len(recovery_scores)
            if recovery_scores
            else None
        )
        return averaged

    # ------------------------------------------------------------------
    # Tool Call F1 (precision, recall, F1)
    # ------------------------------------------------------------------

    def _tool_call_f1(
        self,
        predicted: list[ToolCall],
        expected: list[ToolCall],
    ) -> tuple[float, float, float]:
        """Compute precision, recall, F1 of tool calls."""
        if not predicted and not expected:
            return (1.0, 1.0, 1.0)
        if not predicted:
            return (0.0, 0.0, 0.0)
        if not expected:
            return (0.0, 0.0, 0.0)

        pred_names = Counter(self._call_key(c) for c in predicted)
        exp_names = Counter(self._call_key(c) for c in expected)

        tp = sum(
            min(pred_names[k], exp_names[k])
            for k in pred_names
            if k in exp_names
        )
        precision = tp / sum(pred_names.values()) if pred_names else 0.0
        recall = tp / sum(exp_names.values()) if exp_names else 0.0

        if precision + recall == 0.0:
            return (0.0, 0.0, 0.0)
        f1 = 2.0 * precision * recall / (precision + recall)
        return (precision, recall, f1)

    # ------------------------------------------------------------------
    # Tool Call Accuracy (exact match)
    # ------------------------------------------------------------------

    def _tool_call_accuracy(
        self,
        predicted: list[ToolCall],
        expected: list[ToolCall],
    ) -> float:
        """1.0 if the predicted tool calls exactly match the expected set/sequence."""
        if not predicted and not expected:
            return 1.0

        pred_keys = [self._call_key(c) for c in predicted]
        exp_keys = [self._call_key(c) for c in expected]

        if self._ordered:
            return 1.0 if pred_keys == exp_keys else 0.0
        else:
            return 1.0 if sorted(pred_keys) == sorted(exp_keys) else 0.0

    # ------------------------------------------------------------------
    # Argument Accuracy
    # ------------------------------------------------------------------

    def _argument_accuracy(
        self,
        predicted: list[ToolCall],
        expected: list[ToolCall],
    ) -> float:
        """For tools that were correctly called, what fraction of arguments match?"""
        if not expected:
            return 1.0

        # Build map: tool name -> list of expected argument dicts
        exp_by_name: dict[str, list[dict]] = {}
        for c in expected:
            exp_by_name.setdefault(c.name, []).append(c.arguments or {})

        pred_by_name: dict[str, list[dict]] = {}
        for c in predicted:
            pred_by_name.setdefault(c.name, []).append(c.arguments or {})

        total_args = 0
        matching_args = 0

        for name, exp_arg_list in exp_by_name.items():
            pred_arg_list = pred_by_name.get(name, [])
            for i, exp_args in enumerate(exp_arg_list):
                if not exp_args:
                    continue
                pred_args = pred_arg_list[i] if i < len(pred_arg_list) else {}
                for key, val in exp_args.items():
                    total_args += 1
                    if key in pred_args and self._values_match(pred_args[key], val):
                        matching_args += 1

        return matching_args / total_args if total_args > 0 else 1.0

    # ------------------------------------------------------------------
    # Goal Accuracy
    # ------------------------------------------------------------------

    @staticmethod
    def _goal_accuracy(
        final_answer: str | None, expected_answer: str | None
    ) -> float:
        """Score the agent's final answer against the expected answer."""
        if expected_answer is None:
            return 1.0  # No expectation set
        if final_answer is None:
            return 0.0

        final_lower = final_answer.strip().lower()
        expected_lower = expected_answer.strip().lower()

        # Exact match
        if final_lower == expected_lower:
            return 1.0

        # Containment match
        if expected_lower in final_lower:
            return 0.9

        # Token overlap
        final_tokens = set(final_lower.split())
        expected_tokens = set(expected_lower.split())
        if not expected_tokens:
            return 0.0
        overlap = len(final_tokens & expected_tokens) / len(expected_tokens)
        return min(overlap, 1.0) * 0.7

    # ------------------------------------------------------------------
    # Step Efficiency
    # ------------------------------------------------------------------

    @staticmethod
    def _step_efficiency(
        min_steps: int | None, actual_steps: int | None
    ) -> float:
        """Ratio of minimum required steps to actual steps taken.

        Returns 1.0 if not applicable. Higher is better (1.0 = optimal).
        """
        if min_steps is None or actual_steps is None:
            return 1.0
        if actual_steps == 0:
            return 1.0 if min_steps == 0 else 0.0
        return min(min_steps / actual_steps, 1.0)

    # ------------------------------------------------------------------
    # Error Recovery Rate
    # ------------------------------------------------------------------

    @staticmethod
    def _error_recovery(
        error_states: int | None, recovered_states: int | None
    ) -> float | None:
        """Fraction of errors the agent recovered from."""
        if error_states is None or recovered_states is None:
            return None
        if error_states == 0:
            return None  # No errors to recover from
        return min(recovered_states / error_states, 1.0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_call(call: dict) -> ToolCall:
        """Parse a dict into a ToolCall dataclass."""
        return ToolCall(
            name=call.get("name", ""),
            arguments=call.get("arguments"),
        )

    def _call_key(self, call: ToolCall) -> str:
        """Generate a matching key for a tool call."""
        if self._match_arguments and call.arguments:
            # Sort arguments for consistent comparison
            arg_str = str(sorted(call.arguments.items()))
            return f"{call.name}:{arg_str}"
        return call.name

    @staticmethod
    def _values_match(a: object, b: object) -> bool:
        """Check if two argument values match (with type tolerance)."""
        if a == b:
            return True
        # Try string comparison for numeric tolerance
        try:
            return float(a) == float(b)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            pass
        return str(a).strip().lower() == str(b).strip().lower()
