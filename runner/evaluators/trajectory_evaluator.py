"""
Trajectory evaluator for agents.

Beyond the existing AgentEvaluator's set-based tool F1, this scores the
*sequence* of tool calls and the *arguments* of each call:

* **trajectory_similarity** — 1 - normalised Levenshtein distance over the
  predicted vs. expected tool-call sequence (order matters).
* **argument_schema_valid**  — fraction of predicted calls whose arguments
  validate against an optional JSON schema.
* **argument_semantic_match**— fraction of argument values that match the
  expected values (fuzzy: exact, numeric, or normalised-string equality).

No new deps required. If ``jsonschema`` is installed, schema validation is
used; otherwise it's skipped gracefully.

Expected test_case shape:
    {
        "predicted_tool_calls": [{"name": "...", "arguments": {...}}, ...],
        "expected_tool_calls":  [{"name": "...", "arguments": {...}}, ...],
        "tool_schemas":         {"tool_name": <json_schema>, ...}   # optional
    }
"""
from __future__ import annotations

from runner.evaluators.base_evaluator import BaseEvaluator, EvalError, MetricScores


class TrajectoryEvaluator(BaseEvaluator):
    name = "trajectory"
    version = "1"

    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        return [self._score(tc) for tc in test_cases]

    # ------------------------------------------------------------------ score

    def _score(self, tc: dict) -> MetricScores:
        pred = tc.get("predicted_tool_calls") or []
        exp = tc.get("expected_tool_calls") or []
        schemas = tc.get("tool_schemas") or {}

        if not pred and not exp:
            return MetricScores(
                scores={
                    "trajectory_similarity": 1.0,
                    "argument_schema_valid": 1.0,
                    "argument_semantic_match": 1.0,
                },
                version=self.version,
                metadata={"length_pred": 0, "length_exp": 0},
            )

        traj = self._trajectory_similarity(pred, exp)
        schema_rate = self._schema_valid_rate(pred, schemas)
        arg_sem = self._argument_semantic_match(pred, exp)

        return MetricScores(
            scores={
                "trajectory_similarity": traj,
                "argument_schema_valid": schema_rate,
                "argument_semantic_match": arg_sem,
            },
            version=self.version,
            metadata={
                "length_pred": len(pred),
                "length_exp": len(exp),
                "edit_distance": _levenshtein(
                    [str(c.get("name", "")) for c in pred],
                    [str(c.get("name", "")) for c in exp],
                ),
            },
        )

    # ------------------------------------------------------------------ metrics

    @staticmethod
    def _trajectory_similarity(pred: list[dict], exp: list[dict]) -> float:
        pred_names = [str(c.get("name", "")) for c in pred]
        exp_names = [str(c.get("name", "")) for c in exp]
        if not pred_names and not exp_names:
            return 1.0
        dist = _levenshtein(pred_names, exp_names)
        denom = max(len(pred_names), len(exp_names))
        return 1.0 - dist / denom

    @staticmethod
    def _schema_valid_rate(pred: list[dict], schemas: dict) -> float:
        if not pred:
            return 1.0
        if not schemas:
            return 1.0  # no schemas provided — not a failure signal
        try:
            import jsonschema
        except ImportError:
            return 1.0

        valid = 0
        for call in pred:
            schema = schemas.get(call.get("name"))
            if schema is None:
                valid += 1
                continue
            try:
                jsonschema.validate(instance=call.get("arguments") or {}, schema=schema)
                valid += 1
            except Exception:
                pass
        return valid / len(pred)

    @staticmethod
    def _argument_semantic_match(pred: list[dict], exp: list[dict]) -> float:
        """Match predicted and expected calls by name (multi-set); for each
        matched pair, fraction of expected argument values that are present
        and equal (with numeric + string-normalised tolerance)."""
        if not exp:
            return 1.0

        # Greedy match by name, preserving order.
        exp_by_name: dict[str, list[dict]] = {}
        for c in exp:
            exp_by_name.setdefault(c.get("name", ""), []).append(c.get("arguments") or {})
        pred_by_name: dict[str, list[dict]] = {}
        for c in pred:
            pred_by_name.setdefault(c.get("name", ""), []).append(c.get("arguments") or {})

        total = 0
        matched = 0
        for name, exp_args_list in exp_by_name.items():
            pred_args_list = pred_by_name.get(name, [])
            for i, exp_args in enumerate(exp_args_list):
                if not exp_args:
                    continue
                pred_args = pred_args_list[i] if i < len(pred_args_list) else {}
                for key, val in exp_args.items():
                    total += 1
                    if key in pred_args and _values_equal(pred_args[key], val):
                        matched += 1

        return matched / total if total > 0 else 1.0


# ---------------------------------------------------------------- helpers


def _levenshtein(a: list[str], b: list[str]) -> int:
    """Classic DP edit distance over sequences of strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _values_equal(a, b) -> bool:
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        pass
    return str(a).strip().lower() == str(b).strip().lower()
