"""
Celery tasks for auto-evaluating sampled production traffic.

Runs periodically (via Celery Beat) to find sampled-but-unevaluated
production test cases and trigger evaluation runs for them.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, create_engine, func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.evaluation_run import EvaluationRun, RunStatus
from app.db.models.production_log import IngestionStatus, ProductionLog
from app.db.models.test_case import TestCase
from app.db.models.test_set import TestSet
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.ingestion_tasks.evaluate_sampled_traffic")
def evaluate_sampled_traffic() -> dict:
    """
    Periodic task: find all sampled production logs that haven't been
    evaluated yet, group them by test set, and trigger evaluation runs.
    """
    engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
    runs_created = 0

    with Session(engine) as db:
        # Find test sets that have sampled-but-unevaluated production logs
        test_set_ids = db.execute(
            select(ProductionLog.sampled_into_test_set_id)
            .where(ProductionLog.status == IngestionStatus.SAMPLED)
            .where(ProductionLog.sampled_into_test_set_id.isnot(None))
            .group_by(ProductionLog.sampled_into_test_set_id)
        ).scalars().all()

        for ts_id in test_set_ids:
            if ts_id is None:
                continue

            # Count pending cases
            case_count = db.execute(
                select(func.count()).select_from(TestCase).where(
                    TestCase.test_set_id == ts_id
                )
            ).scalar() or 0

            if case_count == 0:
                continue

            # Create evaluation run
            threshold_snapshot = {
                "faithfulness": settings.DEFAULT_FAITHFULNESS_THRESHOLD,
                "answer_relevancy": settings.DEFAULT_ANSWER_RELEVANCY_THRESHOLD,
                "context_precision": settings.DEFAULT_CONTEXT_PRECISION_THRESHOLD,
                "context_recall": settings.DEFAULT_CONTEXT_RECALL_THRESHOLD,
                "pass_rate": settings.DEFAULT_PASS_RATE_THRESHOLD,
            }

            run = EvaluationRun(
                id=uuid.uuid4(),
                test_set_id=ts_id,
                status=RunStatus.PENDING,
                triggered_by="auto-sample",
                gate_threshold_snapshot=threshold_snapshot,
            )
            db.add(run)
            db.flush()

            # Mark production logs as evaluated
            db.execute(
                update(ProductionLog)
                .where(
                    and_(
                        ProductionLog.sampled_into_test_set_id == ts_id,
                        ProductionLog.status == IngestionStatus.SAMPLED,
                    )
                )
                .values(
                    status=IngestionStatus.EVALUATED,
                    evaluation_run_id=run.id,
                )
            )
            db.commit()

            # Dispatch evaluation
            from app.workers.tasks.evaluation_tasks import run_evaluation
            run_evaluation.apply_async(
                args=[str(run.id), [
                    "faithfulness",
                    "answer_relevancy",
                    "context_precision",
                    "context_recall",
                    "rule_evaluation",
                ]],
                queue="evaluations",
            )
            runs_created += 1

    return {"runs_created": runs_created}
