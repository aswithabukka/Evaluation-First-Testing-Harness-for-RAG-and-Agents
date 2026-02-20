import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.evaluation_result import EvaluationResultResponse, ResultSummary
from app.api.v1.schemas.evaluation_run import EvaluationRunCreate, EvaluationRunResponse, RunStatusResponse
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.db.models.evaluation_result import EvaluationResult
from app.db.models.evaluation_run import EvaluationRun, RunStatus
from app.db.models.test_case import TestCase
from app.db.models.test_set import TestSet


class EvaluationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_run(self, payload: EvaluationRunCreate) -> EvaluationRunResponse:
        # Verify test set exists
        ts_result = await self.db.execute(
            select(TestSet).where(TestSet.id == payload.test_set_id)
        )
        if ts_result.scalar_one_or_none() is None:
            raise NotFoundError("TestSet", str(payload.test_set_id))

        thresholds = payload.thresholds
        threshold_snapshot = {
            "faithfulness": thresholds.faithfulness if thresholds else settings.DEFAULT_FAITHFULNESS_THRESHOLD,
            "answer_relevancy": thresholds.answer_relevancy if thresholds else settings.DEFAULT_ANSWER_RELEVANCY_THRESHOLD,
            "context_precision": thresholds.context_precision if thresholds else settings.DEFAULT_CONTEXT_PRECISION_THRESHOLD,
            "context_recall": thresholds.context_recall if thresholds else settings.DEFAULT_CONTEXT_RECALL_THRESHOLD,
            "pass_rate": thresholds.pass_rate if thresholds else settings.DEFAULT_PASS_RATE_THRESHOLD,
        }

        run = EvaluationRun(
            test_set_id=payload.test_set_id,
            pipeline_version=payload.pipeline_version,
            git_commit_sha=payload.git_commit_sha,
            git_branch=payload.git_branch,
            git_pr_number=payload.git_pr_number,
            triggered_by=payload.triggered_by,
            status=RunStatus.PENDING,
            gate_threshold_snapshot=threshold_snapshot,
            notes=payload.notes,
            pipeline_config=payload.pipeline_config,
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)

        # Dispatch async Celery task
        try:
            from app.workers.tasks.evaluation_tasks import run_evaluation
            run_evaluation.apply_async(
                args=[str(run.id), payload.metrics],
                queue="evaluations",
            )
        except Exception:
            # Gracefully degrade if Celery is unavailable (e.g., local dev without worker)
            pass

        return EvaluationRunResponse.model_validate(run)

    async def list_runs(
        self,
        test_set_id: uuid.UUID | None = None,
        status: str | None = None,
        git_branch: str | None = None,
        git_commit_sha: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[EvaluationRunResponse]:
        query = select(EvaluationRun).order_by(EvaluationRun.started_at.desc())
        if test_set_id:
            query = query.where(EvaluationRun.test_set_id == test_set_id)
        if status:
            query = query.where(EvaluationRun.status == status)
        if git_branch:
            query = query.where(EvaluationRun.git_branch == git_branch)
        if git_commit_sha:
            query = query.where(EvaluationRun.git_commit_sha == git_commit_sha)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return [EvaluationRunResponse.model_validate(r) for r in result.scalars().all()]

    async def get_run(self, run_id: uuid.UUID) -> EvaluationRunResponse:
        run = await self._get_run_or_404(run_id)
        return EvaluationRunResponse.model_validate(run)

    async def get_run_status(self, run_id: uuid.UUID) -> RunStatusResponse:
        run = await self._get_run_or_404(run_id)
        return RunStatusResponse(
            run_id=run.id,
            status=run.status,
            overall_passed=run.overall_passed,
            completed_at=run.completed_at,
        )

    async def cancel_run(self, run_id: uuid.UUID) -> None:
        run = await self._get_run_or_404(run_id)
        if run.status in (RunStatus.PENDING, RunStatus.RUNNING):
            run.status = RunStatus.FAILED
            run.completed_at = datetime.now(timezone.utc)
            await self.db.flush()

    async def list_results(
        self,
        run_id: uuid.UUID,
        passed: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[EvaluationResultResponse]:
        query = select(EvaluationResult).where(EvaluationResult.run_id == run_id)
        if passed is not None:
            query = query.where(EvaluationResult.passed == passed)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return [EvaluationResultResponse.model_validate(r) for r in result.scalars().all()]

    async def get_result(self, result_id: uuid.UUID) -> EvaluationResultResponse:
        result = await self.db.execute(
            select(EvaluationResult).where(EvaluationResult.id == result_id)
        )
        er = result.scalar_one_or_none()
        if er is None:
            raise NotFoundError("EvaluationResult", str(result_id))
        return EvaluationResultResponse.model_validate(er)

    async def get_results_summary(self, run_id: uuid.UUID) -> ResultSummary:
        run = await self._get_run_or_404(run_id)

        agg = await self.db.execute(
            select(
                func.count().label("total"),
                func.sum(EvaluationResult.passed.cast(int)).label("passed"),
                func.avg(EvaluationResult.faithfulness).label("avg_faithfulness"),
                func.avg(EvaluationResult.answer_relevancy).label("avg_answer_relevancy"),
                func.avg(EvaluationResult.context_precision).label("avg_context_precision"),
                func.avg(EvaluationResult.context_recall).label("avg_context_recall"),
            ).where(EvaluationResult.run_id == run_id)
        )
        row = agg.one()
        total = row.total or 0
        passed = row.passed or 0
        return ResultSummary(
            run_id=run_id,
            total_cases=total,
            passed_cases=passed,
            failed_cases=total - passed,
            pass_rate=passed / total if total > 0 else 0.0,
            avg_faithfulness=row.avg_faithfulness,
            avg_answer_relevancy=row.avg_answer_relevancy,
            avg_context_precision=row.avg_context_precision,
            avg_context_recall=row.avg_context_recall,
        )

    async def _get_run_or_404(self, run_id: uuid.UUID) -> EvaluationRun:
        result = await self.db.execute(
            select(EvaluationRun).where(EvaluationRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise NotFoundError("EvaluationRun", str(run_id))
        return run
