"""
Registry-driven evaluator dispatch for the Celery worker.

Lets ``rageval.yaml`` turn on new evaluators by name:

    metrics:
      - faithfulness          # classic Ragas metric
      - g_eval                # new — GEvalEvaluator
      - citation              # new — CitationEvaluator
      - trajectory            # new — TrajectoryEvaluator
      - robustness            # new — RobustnessEvaluator
      - safety                # new — SafetyEvaluator (regex by default)
      - llm_judge             # hardened LLMJudgeEvaluator

Per-evaluator config lives under ``pipeline_config.evaluators.<name>``, e.g.:

    pipeline_config:
      evaluators:
        g_eval:
          aspect: coherence
          description: "Is the response logically consistent?"
          samples: 3
        safety:
          use_presidio: true

Legacy system-type branches (Ragas / Agent / Conversation / Ranking) keep
working — this module only fires for names in ``EVALUATOR_REGISTRY``.

The dispatch is deliberately narrow: we build a per-evaluator test-case
dict from the current run state (pipeline output, tool calls, test case
fields), run ``evaluate_batch`` with a single case, and merge the
resulting ``MetricScores.scores`` into a flat metrics dict. Cost and
latency flow to the run Budget. Evaluators that don't fit the per-case
shape (``pairwise``, ``calibration``) are skipped here and handled
elsewhere.
"""
from __future__ import annotations

import math
from typing import Any


# Evaluators that don't fit the per-case loop:
#   - pairwise:    needs answer_a + answer_b (multi-model comparison flow)
#   - calibration: batch-level, needs (confidence, correct) pairs
_SKIP_PER_CASE = frozenset({"pairwise", "calibration"})


def _nan_to_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _build_case_dict(
    *,
    evaluator_name: str,
    tc,
    raw_output: str,
    raw_contexts: list[str],
    tool_calls_data: list[dict],
) -> dict:
    """Shape a per-case dict for whichever evaluator wants it.

    Each evaluator reads only the keys it needs; unknown keys are ignored.
    """
    # Expected tool calls: prefer explicit context.expected_tool_calls, fall
    # back to must_call_tool rules.
    expected_tool_calls: list[dict] = []
    if isinstance(tc.context, dict):
        expected_tool_calls = tc.context.get("expected_tool_calls", []) or []
    if not expected_tool_calls and tc.failure_rules:
        for rule in tc.failure_rules:
            if rule.get("type") == "must_call_tool":
                expected_tool_calls.append({"name": rule.get("tool", "")})

    predicted_tool_calls = [
        {"name": tc_call.get("tool", ""), "arguments": tc_call.get("args")}
        for tc_call in tool_calls_data
    ]

    case: dict = {
        "question": tc.query,
        "query": tc.query,
        "answer": raw_output or "",
        "ground_truth": tc.ground_truth,
        "contexts": raw_contexts,
        # Trajectory evaluator keys:
        "predicted_tool_calls": predicted_tool_calls,
        "expected_tool_calls": expected_tool_calls,
    }

    # Robustness pulls paraphrase_answers / adversarial_answers out of
    # test-case context — these have to be pre-computed and stored with the
    # case (or injected by a custom runner). Empty lists are fine; the
    # evaluator then reports None for that axis.
    if isinstance(tc.context, dict):
        if "paraphrase_answers" in tc.context:
            case["paraphrase_answers"] = tc.context["paraphrase_answers"]
        if "adversarial_answers" in tc.context:
            case["adversarial_answers"] = tc.context["adversarial_answers"]
        if "tool_schemas" in tc.context:
            case["tool_schemas"] = tc.context["tool_schemas"]

    return case


def _instantiate(
    evaluator_name: str, evaluator_cls, config: dict, openai_api_key: str | None
):
    """Instantiate an evaluator with config from ``pipeline_config.evaluators``.

    Swallows init errors so a bad config line can't kill the run — callers
    get ``None`` and should skip the evaluator.
    """
    cfg = dict(config or {})
    # LLM-based evaluators accept an api key kwarg; others ignore it.
    if openai_api_key and "openai_api_key" not in cfg:
        cfg["openai_api_key"] = openai_api_key
    try:
        return evaluator_cls(**cfg)
    except TypeError:
        # Common cause: evaluator doesn't take openai_api_key. Retry without.
        cfg.pop("openai_api_key", None)
        try:
            return evaluator_cls(**cfg)
        except Exception:
            return None
    except Exception:
        return None


def run_registry_evaluators(
    *,
    tc,
    metrics: list[str],
    pipeline_config: dict | None,
    raw_output: str,
    raw_contexts: list[str],
    tool_calls_data: list[dict],
    openai_api_key: str | None,
    manifest=None,
    budget=None,
    record_evaluator_fn=None,
) -> tuple[dict, list[str]]:
    """Run every ``EVALUATOR_REGISTRY`` evaluator listed in ``metrics``.

    Returns ``(scores, errors)``:
      - ``scores``: flat dict ``{metric_name: float | None}`` merged from every
        evaluator's ``MetricScores.scores``.
      - ``errors``: list of human-readable error strings for evaluators that
        failed to produce any score. Use the first one as ``failure_reason``.
    """
    try:
        from runner.evaluators import EVALUATOR_REGISTRY
    except ImportError:
        return {}, []

    evaluator_configs = ((pipeline_config or {}).get("evaluators") or {})
    out_scores: dict[str, float | None] = {}
    out_errors: list[str] = []

    for name in metrics:
        if name in _SKIP_PER_CASE:
            continue
        cls = EVALUATOR_REGISTRY.get(name)
        if cls is None:
            continue

        ev = _instantiate(name, cls, evaluator_configs.get(name, {}), openai_api_key)
        if ev is None:
            out_errors.append(f"{name}: init failed")
            continue

        if manifest is not None and record_evaluator_fn is not None:
            record_evaluator_fn(manifest, cls.__module__, cls.__name__)

        case = _build_case_dict(
            evaluator_name=name,
            tc=tc,
            raw_output=raw_output,
            raw_contexts=raw_contexts,
            tool_calls_data=tool_calls_data,
        )

        try:
            # SafetyEvaluator isn't a BaseEvaluator — it has its own
            # evaluate(text) / evaluate_batch([text]) API.
            if name == "safety":
                safety_result = ev.evaluate(raw_output or "")
                for k, v in safety_result.items():
                    if isinstance(v, (int, float, bool)):
                        out_scores[f"safety_{k}"] = float(v)
                continue

            results = ev.evaluate_batch([case])
        except Exception as e:
            out_errors.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            continue

        if not results:
            out_errors.append(f"{name}: no results returned")
            continue

        ms = results[0]
        # Budget bookkeeping — cost is only populated by LLM-based evaluators.
        if budget is not None and getattr(ms, "cost_usd", 0.0):
            budget.record(ms)

        # If the evaluator errored for this row, surface it but don't poison
        # the run — a None score with an EvalError just means "can't gate
        # on this row".
        if getattr(ms, "error", None) is not None:
            out_errors.append(f"{name}: {ms.error.type} — {ms.error.message[:100]}")

        # Merge scores. Also honour the legacy RAG fields so Ragas-shaped
        # evaluators (our hardened RagasEvaluator, if someone enables it via
        # the registry) still surface faithfulness / answer_relevancy etc.
        for legacy_field in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
            legacy_val = _nan_to_none(getattr(ms, legacy_field, None))
            if legacy_val is not None:
                out_scores[legacy_field] = legacy_val
        for k, v in (ms.scores or {}).items():
            out_scores[k] = _nan_to_none(v)

    return out_scores, out_errors


def extract_calibration_batch(
    results: list, test_cases: list
) -> list[dict]:
    """Shape a (confidence, correct) batch for CalibrationEvaluator.

    Pulls ``confidence`` from the pipeline output's extended_metrics (if
    present) and ``correct`` from the per-case pass/fail. Returns [] when
    nothing is available — the calibration evaluator then reports an
    EvalError, which the summary aggregator knows to skip.
    """
    batch: list[dict] = []
    for r in results:
        ext = r.extended_metrics or {}
        conf = ext.get("confidence")
        if conf is None:
            continue
        batch.append({"confidence": conf, "correct": 1 if r.passed else 0})
    return batch
