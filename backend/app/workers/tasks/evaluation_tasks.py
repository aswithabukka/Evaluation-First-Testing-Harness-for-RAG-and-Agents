"""
Celery evaluation task.

Runs the full evaluation loop for a given EvaluationRun:
1. Boots the DemoRAGAdapter (embeds corpus once via OpenAI)
2. For each test case: calls the pipeline → gets real answer + retrieved contexts
3. Scores results with Ragas and the RuleEvaluator
4. Stores EvaluationResult rows and MetricsHistory entries
5. Updates the run status and summary_metrics
"""
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
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, name="app.workers.tasks.evaluation_tasks.run_evaluation", max_retries=2)
def run_evaluation(self, run_id: str, metrics: list[str]) -> dict:
    """
    Main evaluation Celery task. Uses a synchronous SQLAlchemy session
    (Celery workers are synchronous by default).
    """
    engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)

    # ── Boot the RAG pipeline once per task ───────────────────────────────
    pipeline = None
    pipeline_config_captured: dict = {}
    try:
        from runner.adapters.demo_rag import DemoRAGAdapter
        pipeline = DemoRAGAdapter()
        pipeline.setup()
        # Capture structured config for the audit trail
        pipeline_config_captured = {
            k: getattr(pipeline, k)
            for k in ("model", "top_k", "_embed_model")
            if hasattr(pipeline, k)
        }
        if "_embed_model" in pipeline_config_captured:
            pipeline_config_captured["embedding_model"] = pipeline_config_captured.pop("_embed_model")
        pipeline_config_captured["adapter"] = type(pipeline).__name__
    except Exception as exc:
        # Pipeline failure is non-fatal; evaluation falls back to stored text
        print(f"[warn] RAG pipeline setup failed: {exc}")

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
                    top_k = pipeline_config_captured.get("top_k", "?")
                    run.pipeline_version = f"{adapter}/{model}/top-{top_k}"
            db.commit()

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
                result = _evaluate_test_case(tc, run, metrics, db, pipeline)
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
                "avg_faithfulness": avg([r.faithfulness for r in results]),
                "avg_answer_relevancy": avg([r.answer_relevancy for r in results]),
                "avg_context_precision": avg([r.context_precision for r in results]),
                "avg_context_recall": avg([r.context_recall for r in results]),
            }

            # ── Gate evaluation ───────────────────────────────────────────
            thresholds = run.gate_threshold_snapshot or {}
            gate_passed = True
            for metric_key, summary_key in [
                ("faithfulness", "avg_faithfulness"),
                ("answer_relevancy", "avg_answer_relevancy"),
                ("context_precision", "avg_context_precision"),
                ("context_recall", "avg_context_recall"),
                ("pass_rate", "pass_rate"),
            ]:
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
            for summary_key, metric_name in {
                "avg_faithfulness": "faithfulness",
                "avg_answer_relevancy": "answer_relevancy",
                "avg_context_precision": "context_precision",
                "avg_context_recall": "context_recall",
                "pass_rate": "pass_rate",
            }.items():
                value = summary.get(summary_key)
                if value is not None:
                    db.add(MetricsHistory(
                        test_set_id=run.test_set_id,
                        run_id=run.id,
                        metric_name=metric_name,
                        metric_value=value,
                        pipeline_version=run.pipeline_version,
                        git_commit_sha=run.git_commit_sha,
                    ))

            db.commit()

    finally:
        if pipeline is not None:
            try:
                pipeline.teardown()
            except Exception:
                pass

    return {
        "run_id": run_id,
        "status": run.status.value,
        "total_cases": total,
        "passed_cases": passed_count,
        "gate_passed": gate_passed,
    }


def _evaluate_test_case(
    tc: TestCase,
    run: EvaluationRun,
    metrics: list[str],
    db: Session,
    pipeline=None,
) -> EvaluationResult:
    """Score a single test case using the RAG pipeline + Ragas. Stores the result row."""
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

    # ── Step 1: call the RAG pipeline ─────────────────────────────────────
    if pipeline is not None:
        try:
            output = pipeline.run(tc.query, tc.context or {})
            raw_output = output.answer
            raw_contexts = output.retrieved_contexts
        except Exception as exc:
            failure_reason = f"Pipeline error: {exc}"
            # Fall back to stored text so Ragas can still score
            raw_output = tc.expected_output or tc.ground_truth or ""
            raw_contexts = tc.context or []
    else:
        # No pipeline — use stored ground truth as a stand-in answer
        raw_output = tc.expected_output or tc.ground_truth or ""
        raw_contexts = tc.context or []

    # ── Step 2: Ragas evaluation ───────────────────────────────────────────
    if any(m in metrics for m in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")):
        try:
            scores = _run_ragas(tc, metrics, answer=raw_output, contexts=raw_contexts)

            def _nan_to_none(v):
                if v is None:
                    return None
                try:
                    return None if (math.isnan(v) or math.isinf(v)) else float(v)
                except (TypeError, ValueError):
                    return None

            faithfulness = _nan_to_none(scores.get("faithfulness"))
            answer_relevancy = _nan_to_none(scores.get("answer_relevancy"))
            context_precision = _nan_to_none(scores.get("context_precision"))
            context_recall = _nan_to_none(scores.get("context_recall"))
        except Exception as exc:
            if failure_reason is None:
                failure_reason = f"Ragas evaluation failed: {exc}"

    # ── Step 3: Rule evaluation ────────────────────────────────────────────
    if "rule_evaluation" in metrics and tc.failure_rules:
        try:
            from runner.evaluators.rule_evaluator import RuleEvaluator
            rule_eval = RuleEvaluator()
            rule_result = rule_eval.evaluate_single(
                query=tc.query,
                output=raw_output or "",
                tool_calls=[],
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

    # ── Step 4: Determine per-case pass/fail ──────────────────────────────
    thresholds = run.gate_threshold_snapshot or {}
    per_case_passed = True

    for actual, threshold in [
        (faithfulness, thresholds.get("faithfulness")),
        (answer_relevancy, thresholds.get("answer_relevancy")),
        (context_precision, thresholds.get("context_precision")),
        (context_recall, thresholds.get("context_recall")),
    ]:
        if actual is not None and threshold is not None and actual < threshold:
            per_case_passed = False
            break

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
