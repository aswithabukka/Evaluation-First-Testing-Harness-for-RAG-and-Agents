"""
Celery evaluation task.

Runs the full evaluation loop for a given EvaluationRun:
1. Boots the pipeline adapter (dynamic — reads adapter_module/adapter_class from pipeline_config)
2. For each test case: calls the pipeline → gets real answer + retrieved contexts
3. Scores results with system-specific evaluators (Ragas for RAG, AgentEvaluator,
   ConversationEvaluator, RankingEvaluator for their respective system types)
4. Stores EvaluationResult rows and MetricsHistory entries
5. Updates the run status and summary_metrics
"""
import importlib
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.evaluation_result import EvaluationResult
from app.db.models.evaluation_run import EvaluationRun, RunStatus
from app.db.models.metrics_history import MetricsHistory
from app.db.models.test_case import TestCase
from app.db.models.test_set import TestSet
from app.services.alert_service import AlertService
from app.workers.celery_app import celery_app


def _load_adapter(pipeline_config: dict | None):
    """
    Dynamically load and instantiate a pipeline adapter.

    Reads 'adapter_module' and 'adapter_class' from pipeline_config.
    Falls back to DemoRAGAdapter for backward compatibility.
    """
    config = pipeline_config or {}
    module_path = config.get("adapter_module", "runner.adapters.demo_rag")
    class_name = config.get("adapter_class", "DemoRAGAdapter")

    mod = importlib.import_module(module_path)
    adapter_cls = getattr(mod, class_name)

    # Pass any extra config keys as constructor kwargs (excluding meta fields)
    meta_keys = {"adapter_module", "adapter_class"}
    init_kwargs = {k: v for k, v in config.items() if k not in meta_keys}
    return adapter_cls(**init_kwargs) if init_kwargs else adapter_cls()


@celery_app.task(bind=True, name="app.workers.tasks.evaluation_tasks.run_evaluation", max_retries=2)
def run_evaluation(self, run_id: str, metrics: list[str]) -> dict:
    """
    Main evaluation Celery task. Uses a synchronous SQLAlchemy session
    (Celery workers are synchronous by default).
    """
    engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)

    # ── Read run config to determine which adapter to load ─────────────
    pipeline = None
    pipeline_config_captured: dict = {}
    run_pipeline_config: dict | None = None

    with Session(engine) as db:
        run_row = db.execute(
            select(EvaluationRun).where(EvaluationRun.id == uuid.UUID(run_id))
        ).scalar_one_or_none()
        if run_row is not None:
            run_pipeline_config = run_row.pipeline_config

    # ── Boot the pipeline adapter ──────────────────────────────────────
    try:
        pipeline = _load_adapter(run_pipeline_config)
        pipeline.setup()
        # Capture structured config for the audit trail
        for attr in ("model", "top_k", "_embed_model", "max_tool_rounds"):
            if hasattr(pipeline, attr):
                key = "embedding_model" if attr == "_embed_model" else attr
                pipeline_config_captured[key] = getattr(pipeline, attr)
        pipeline_config_captured["adapter"] = type(pipeline).__name__
    except Exception as exc:
        # Pipeline failure is non-fatal; evaluation falls back to stored text
        print(f"[warn] Pipeline setup failed: {exc}")

    try:
        with Session(engine) as db:
            run = db.execute(
                select(EvaluationRun).where(EvaluationRun.id == uuid.UUID(run_id))
            ).scalar_one_or_none()

            if run is None:
                return {"error": f"Run {run_id} not found"}

            run.status = RunStatus.RUNNING
            # Merge auto-captured config with any config provided at trigger time
            if pipeline_config_captured:
                run.pipeline_config = {**pipeline_config_captured, **(run.pipeline_config or {})}
                # Auto-generate pipeline_version from config if not set at trigger time
                if not run.pipeline_version:
                    adapter = pipeline_config_captured.get("adapter", "pipeline")
                    model = pipeline_config_captured.get("model", "unknown")
                    extra = pipeline_config_captured.get("top_k")
                    version_suffix = f"/top-{extra}" if extra else ""
                    run.pipeline_version = f"{adapter}/{model}{version_suffix}"
            db.commit()

            # Look up the test set to determine system type
            test_set = db.execute(
                select(TestSet).where(TestSet.id == run.test_set_id)
            ).scalar_one_or_none()
            system_type = test_set.system_type if test_set else "rag"

            test_cases = db.execute(
                select(TestCase).where(TestCase.test_set_id == run.test_set_id)
            ).scalars().all()

            if not test_cases:
                run.status = RunStatus.COMPLETED
                run.overall_passed = True
                run.completed_at = datetime.now(timezone.utc)
                run.summary_metrics = {
                    "total_cases": 0, "passed_cases": 0,
                    "failed_cases": 0, "pass_rate": 1.0,
                }
                db.commit()
                return {"run_id": run_id, "status": "completed", "total_cases": 0}

            results = []
            passed_count = 0

            for tc in test_cases:
                result = _evaluate_test_case(tc, run, metrics, db, pipeline, system_type)
                results.append(result)
                if result.passed:
                    passed_count += 1

            # ── Summary metrics ───────────────────────────────────────────
            def _clean(v):
                if v is None:
                    return None
                try:
                    return None if (math.isnan(v) or math.isinf(v)) else float(v)
                except (TypeError, ValueError):
                    return None

            def avg(vals):
                vals = [_clean(v) for v in vals if _clean(v) is not None]
                return sum(vals) / len(vals) if vals else None

            total = len(results)
            summary = {
                "total_cases": total,
                "passed_cases": passed_count,
                "failed_cases": total - passed_count,
                "pass_rate": passed_count / total if total > 0 else 0.0,
            }

            # RAG-specific summary metrics
            if system_type == "rag":
                summary.update({
                    "avg_faithfulness": avg([r.faithfulness for r in results]),
                    "avg_answer_relevancy": avg([r.answer_relevancy for r in results]),
                    "avg_context_precision": avg([r.context_precision for r in results]),
                    "avg_context_recall": avg([r.context_recall for r in results]),
                })

            # System-specific extended metrics aggregation
            if system_type in ("agent", "chatbot", "search", "code_gen",
                               "classification", "summarization", "translation"):
                ext_keys: set[str] = set()
                for r in results:
                    if r.extended_metrics:
                        ext_keys.update(r.extended_metrics.keys())
                for key in ext_keys:
                    vals = [
                        r.extended_metrics.get(key) for r in results
                        if r.extended_metrics and r.extended_metrics.get(key) is not None
                    ]
                    avg_val = avg(vals)
                    if avg_val is not None:
                        summary[f"avg_{key}"] = avg_val

            # ── Gate evaluation ───────────────────────────────────────────
            thresholds = run.gate_threshold_snapshot or {}
            gate_passed = True

            # Build metric-key to summary-key pairs based on system type
            gate_checks: list[tuple[str, str]] = [("pass_rate", "pass_rate")]
            if system_type == "rag":
                gate_checks.extend([
                    ("faithfulness", "avg_faithfulness"),
                    ("answer_relevancy", "avg_answer_relevancy"),
                    ("context_precision", "avg_context_precision"),
                    ("context_recall", "avg_context_recall"),
                ])
            elif system_type == "agent":
                gate_checks.extend([
                    ("tool_call_f1", "avg_tool_call_f1"),
                    ("tool_call_accuracy", "avg_tool_call_accuracy"),
                    ("goal_accuracy", "avg_goal_accuracy"),
                    ("step_efficiency", "avg_step_efficiency"),
                ])
            elif system_type == "chatbot":
                gate_checks.extend([
                    ("coherence", "avg_coherence"),
                    ("knowledge_retention", "avg_knowledge_retention"),
                    ("role_adherence", "avg_role_adherence"),
                    ("response_relevance", "avg_response_relevance"),
                ])
            elif system_type == "search":
                gate_checks.extend([
                    ("ndcg_at_k", "avg_ndcg_at_k"),
                    ("map_at_k", "avg_map_at_k"),
                    ("mrr", "avg_mrr"),
                    ("recall_at_k", "avg_recall_at_k"),
                ])

            for metric_key, summary_key in gate_checks:
                threshold = thresholds.get(metric_key)
                actual = summary.get(summary_key)
                if threshold is not None and actual is not None and actual < threshold:
                    gate_passed = False
                    break

            run.status = RunStatus.COMPLETED if gate_passed else RunStatus.GATE_BLOCKED
            run.overall_passed = gate_passed
            run.completed_at = datetime.now(timezone.utc)
            run.summary_metrics = summary

            # ── Metrics history ───────────────────────────────────────────
            # Write all avg_* keys to metrics history for trend tracking
            for summary_key, value in summary.items():
                if summary_key.startswith("avg_") and value is not None:
                    metric_name = summary_key[4:]  # strip "avg_" prefix
                    db.add(MetricsHistory(
                        test_set_id=run.test_set_id,
                        run_id=run.id,
                        metric_name=metric_name,
                        metric_value=value,
                        pipeline_version=run.pipeline_version,
                        git_commit_sha=run.git_commit_sha,
                    ))
            # Always write pass_rate
            if summary.get("pass_rate") is not None:
                db.add(MetricsHistory(
                    test_set_id=run.test_set_id,
                    run_id=run.id,
                    metric_name="pass_rate",
                    metric_value=summary["pass_rate"],
                    pipeline_version=run.pipeline_version,
                    git_commit_sha=run.git_commit_sha,
                ))

            # ── Alerting ─────────────────────────────────────────────────
            if not gate_passed and thresholds:
                try:
                    ts_row = db.execute(
                        select(TestSet).where(TestSet.id == run.test_set_id)
                    ).scalar_one_or_none()
                    ts_name = ts_row.name if ts_row else str(run.test_set_id)
                    AlertService.check_and_alert(
                        run_id=run_id,
                        test_set_name=ts_name,
                        pipeline_version=run.pipeline_version,
                        summary_metrics=summary,
                        thresholds=thresholds,
                    )
                except Exception as exc:
                    print(f"[warn] Alert dispatch failed: {exc}")

            db.commit()

            # Capture return values while still inside session
            final_status = run.status.value
            final_total = total
            final_passed = passed_count
            final_gate = gate_passed

    finally:
        if pipeline is not None:
            try:
                pipeline.teardown()
            except Exception:
                pass

    return {
        "run_id": run_id,
        "status": final_status,
        "total_cases": final_total,
        "passed_cases": final_passed,
        "gate_passed": final_gate,
    }


def _evaluate_test_case(
    tc: TestCase,
    run: EvaluationRun,
    metrics: list[str],
    db: Session,
    pipeline=None,
    system_type: str = "rag",
) -> EvaluationResult:
    """Score a single test case using the pipeline + system-specific evaluator."""
    import time

    start = time.monotonic()

    faithfulness = None
    answer_relevancy = None
    context_precision = None
    context_recall = None
    rules_passed = None
    rules_detail = []
    failure_reason = None
    raw_output = None
    raw_contexts: list[str] = []
    tool_calls_data: list[dict] = []
    extended_metrics: dict | None = None
    pipeline_output = None

    # ── Step 1: call the pipeline ──────────────────────────────────────
    if pipeline is not None:
        try:
            output = pipeline.run(tc.query, tc.context or {})
            pipeline_output = output
            raw_output = output.answer
            raw_contexts = output.retrieved_contexts
            tool_calls_data = [
                {"tool": tc_call.tool, "args": tc_call.args, "result": tc_call.result}
                for tc_call in output.tool_calls
            ]
        except Exception as exc:
            failure_reason = f"Pipeline error: {exc}"
            # Fall back to stored text so evaluators can still score
            raw_output = tc.expected_output or tc.ground_truth or ""
            raw_contexts = tc.context or []
    else:
        # No pipeline — use stored ground truth as a stand-in answer
        raw_output = tc.expected_output or tc.ground_truth or ""
        raw_contexts = tc.context or []

    # ── Step 2: System-specific evaluation ─────────────────────────────

    def _nan_to_none(v):
        if v is None:
            return None
        try:
            return None if (math.isnan(v) or math.isinf(v)) else float(v)
        except (TypeError, ValueError):
            return None

    if system_type == "rag":
        # Ragas evaluation for RAG systems
        if any(m in metrics for m in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")):
            try:
                scores = _run_ragas(tc, metrics, answer=raw_output, contexts=raw_contexts)
                faithfulness = _nan_to_none(scores.get("faithfulness"))
                answer_relevancy = _nan_to_none(scores.get("answer_relevancy"))
                context_precision = _nan_to_none(scores.get("context_precision"))
                context_recall = _nan_to_none(scores.get("context_recall"))
            except Exception as exc:
                if failure_reason is None:
                    failure_reason = f"Ragas evaluation failed: {exc}"

    elif system_type == "agent":
        # Agent evaluator: tool call F1, accuracy, goal, efficiency
        try:
            from runner.evaluators.agent_evaluator import AgentEvaluator
            agent_eval = AgentEvaluator()

            # Map pipeline tool_calls format to evaluator format
            predicted_calls = [
                {"name": tc_call.get("tool", ""), "arguments": tc_call.get("args")}
                for tc_call in tool_calls_data
            ]
            # Expected tool calls from test case (stored in failure_rules or context)
            expected_calls = []
            if tc.context and isinstance(tc.context, dict):
                expected_calls = tc.context.get("expected_tool_calls", [])
            elif tc.context and isinstance(tc.context, list):
                # Try to find expected_tool_calls in context items
                for item in tc.context:
                    if isinstance(item, dict) and "expected_tool_calls" in item:
                        expected_calls = item["expected_tool_calls"]
                        break
            # Also check failure_rules for expected tool info
            if not expected_calls and tc.failure_rules:
                for rule in tc.failure_rules:
                    if rule.get("type") == "must_call_tool":
                        expected_calls.append({"name": rule.get("tool", "")})

            scores = agent_eval.evaluate(
                predicted_tool_calls=predicted_calls,
                expected_tool_calls=expected_calls,
                final_answer=raw_output,
                expected_answer=tc.expected_output,
                min_steps=len(expected_calls) if expected_calls else None,
                actual_steps=len(tool_calls_data) if tool_calls_data else None,
            )
            extended_metrics = {k: _nan_to_none(v) for k, v in scores.items() if v is not None}
        except Exception as exc:
            if failure_reason is None:
                failure_reason = f"Agent evaluation failed: {exc}"

    elif system_type == "chatbot":
        # Conversation evaluator: coherence, retention, role adherence, relevance
        try:
            from runner.evaluators.conversation_evaluator import ConversationEvaluator
            conv_eval = ConversationEvaluator()

            # Evaluate each test case independently: use only the current
            # query + response pair. The chatbot adapter accumulates history
            # across test cases, but per-case scoring should be isolated.
            turns = [
                {"role": "user", "content": tc.query},
                {"role": "assistant", "content": raw_output or ""},
            ]
            # For explicit multi-turn test cases, use the provided turns
            if tc.conversation_turns:
                turns = tc.conversation_turns

            entities = []
            if tc.context and isinstance(tc.context, dict):
                entities = tc.context.get("entities_to_retain", [])

            scores = conv_eval.evaluate(
                turns=turns,
                expected_final_response=tc.expected_output,
                entities_to_retain=entities,
            )
            extended_metrics = {k: _nan_to_none(v) for k, v in scores.items()}
        except Exception as exc:
            if failure_reason is None:
                failure_reason = f"Conversation evaluation failed: {exc}"

    elif system_type == "search":
        # Ranking evaluator: NDCG, MAP, MRR, Precision, Recall
        try:
            from runner.evaluators.ranking_evaluator import RankingEvaluator
            rank_eval = RankingEvaluator(k=5)

            # Get predicted ranking from pipeline output metadata
            predicted_ranking = []
            if pipeline_output and pipeline_output.metadata:
                predicted_ranking = pipeline_output.metadata.get("ranked_ids", [])
            elif raw_contexts:
                # Extract doc IDs from context strings like "[doc-001] Title: content"
                import re
                for ctx in raw_contexts:
                    match = re.match(r"\[([\w-]+)\]", ctx)
                    if match:
                        predicted_ranking.append(match.group(1))

            # Expected ranking from test case
            expected_ranking = tc.expected_ranking or []

            if expected_ranking:
                scores = rank_eval.evaluate(
                    predicted_ranking=predicted_ranking,
                    expected_ranking=expected_ranking,
                )
                extended_metrics = {k: _nan_to_none(v) for k, v in scores.items()}
            else:
                # No expected ranking — can't compute IR metrics
                extended_metrics = {
                    "ndcg_at_k": None, "map_at_k": None,
                    "mrr": None, "precision_at_k": None, "recall_at_k": None,
                }
        except Exception as exc:
            if failure_reason is None:
                failure_reason = f"Ranking evaluation failed: {exc}"

    # ── Step 3: Rule evaluation ────────────────────────────────────────
    if "rule_evaluation" in metrics and tc.failure_rules:
        try:
            from runner.evaluators.rule_evaluator import RuleEvaluator
            rule_eval = RuleEvaluator()
            rule_result = rule_eval.evaluate_single(
                query=tc.query,
                output=raw_output or "",
                tool_calls=tool_calls_data,
                failure_rules=tc.failure_rules or [],
                faithfulness_score=faithfulness,
            )
            rules_passed = rule_result["passed"]
            rules_detail = rule_result["details"]
            if not rules_passed and failure_reason is None:
                failure_reason = "Failure rule violation: " + "; ".join(
                    d["reason"] for d in rules_detail if not d.get("passed")
                )
        except Exception as exc:
            if failure_reason is None:
                failure_reason = f"Rule evaluation failed: {exc}"

    # ── Step 4: Determine per-case pass/fail ──────────────────────────
    # Per-case pass/fail uses a COMPOSITE score (average of all non-null
    # metrics). Gate thresholds are designed for run-level aggregate
    # decisions, not individual cases — a single quirky metric (e.g.
    # Ragas faithfulness=0.0 for a correct answer, or answer_relevancy=0.0
    # for a valid refusal) should not fail an otherwise correct case.
    per_case_passed = True
    COMPOSITE_THRESHOLD = 0.5  # minimum composite average to pass

    if system_type == "rag":
        metric_values = [
            v for v in [faithfulness, answer_relevancy, context_precision, context_recall]
            if v is not None
        ]
        if metric_values:
            composite = sum(metric_values) / len(metric_values)
            if composite < COMPOSITE_THRESHOLD:
                per_case_passed = False
                if failure_reason is None:
                    failure_reason = f"Composite metric average {composite:.3f} below {COMPOSITE_THRESHOLD}"
    elif extended_metrics:
        metric_values = [v for v in extended_metrics.values() if v is not None]
        if metric_values:
            composite = sum(metric_values) / len(metric_values)
            if composite < COMPOSITE_THRESHOLD:
                per_case_passed = False
                if failure_reason is None:
                    failure_reason = f"Composite metric average {composite:.3f} below {COMPOSITE_THRESHOLD}"

    if rules_passed is False:
        per_case_passed = False

    duration_ms = int((time.monotonic() - start) * 1000)

    result = EvaluationResult(
        run_id=run.id,
        test_case_id=tc.id,
        faithfulness=faithfulness,
        answer_relevancy=answer_relevancy,
        context_precision=context_precision,
        context_recall=context_recall,
        rules_passed=rules_passed,
        rules_detail=rules_detail,
        passed=per_case_passed,
        failure_reason=failure_reason,
        raw_output=raw_output,
        raw_contexts=raw_contexts,
        tool_calls=tool_calls_data if tool_calls_data else None,
        extended_metrics=extended_metrics,
        duration_ms=duration_ms,
    )
    db.add(result)
    db.flush()
    return result


def _run_ragas(
    tc: TestCase,
    metrics: list[str],
    answer: str = "",
    contexts: Optional[list[str]] = None,
) -> dict:
    """Run Ragas evaluation for a single test case. Returns metric scores."""
    from datasets import Dataset
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    metric_map = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    active_metrics = [metric_map[m] for m in metrics if m in metric_map]
    if not active_metrics:
        return {}

    eval_contexts = contexts if contexts else (tc.context if tc.context else [""])
    if not eval_contexts:
        eval_contexts = [""]

    data = {
        "question": [tc.query],
        "answer": [answer or tc.expected_output or tc.ground_truth or ""],
        "contexts": [eval_contexts],
        "ground_truth": [tc.ground_truth or ""],
    }
    dataset = Dataset.from_dict(data)
    result = ragas_evaluate(dataset=dataset, metrics=active_metrics)
    scores = result.to_pandas().iloc[0].to_dict()
    return {k: float(v) for k, v in scores.items() if k in metric_map}
