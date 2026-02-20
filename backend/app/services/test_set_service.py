import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.schemas.test_set import TestSetCreate, TestSetResponse, TestSetUpdate
from app.core.exceptions import NotFoundError
from app.db.models.evaluation_run import EvaluationRun, RunStatus
from app.db.models.test_case import TestCase
from app.db.models.test_set import TestSet


class TestSetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: TestSetCreate) -> TestSetResponse:
        ts = TestSet(name=payload.name, description=payload.description)
        self.db.add(ts)
        await self.db.flush()
        await self.db.refresh(ts)
        return self._to_response(ts, test_case_count=0, last_run_status=None)

    async def list(self, skip: int = 0, limit: int = 50) -> list[TestSetResponse]:
        result = await self.db.execute(
            select(TestSet).order_by(TestSet.created_at.desc()).offset(skip).limit(limit)
        )
        test_sets = result.scalars().all()
        return [await self._enrich(ts) for ts in test_sets]

    async def get(self, test_set_id: uuid.UUID) -> TestSetResponse:
        ts = await self._get_or_404(test_set_id)
        return await self._enrich(ts)

    async def update(self, test_set_id: uuid.UUID, payload: TestSetUpdate) -> TestSetResponse:
        ts = await self._get_or_404(test_set_id)
        if payload.name is not None:
            ts.name = payload.name
        if payload.description is not None:
            ts.description = payload.description
        await self.db.flush()
        await self.db.refresh(ts)
        return await self._enrich(ts)

    async def delete(self, test_set_id: uuid.UUID) -> None:
        ts = await self._get_or_404(test_set_id)
        await self.db.delete(ts)

    async def export(self, test_set_id: uuid.UUID) -> dict:
        ts = await self._get_or_404(test_set_id)
        cases_result = await self.db.execute(
            select(TestCase).where(TestCase.test_set_id == test_set_id)
        )
        cases = cases_result.scalars().all()
        return {
            "test_set": {
                "id": str(ts.id),
                "name": ts.name,
                "description": ts.description,
                "version": ts.version,
            },
            "cases": [
                {
                    "id": str(c.id),
                    "query": c.query,
                    "expected_output": c.expected_output,
                    "ground_truth": c.ground_truth,
                    "context": c.context,
                    "failure_rules": c.failure_rules,
                    "tags": c.tags,
                }
                for c in cases
            ],
        }

    async def _get_or_404(self, test_set_id: uuid.UUID) -> TestSet:
        result = await self.db.execute(
            select(TestSet).where(TestSet.id == test_set_id)
        )
        ts = result.scalar_one_or_none()
        if ts is None:
            raise NotFoundError("TestSet", str(test_set_id))
        return ts

    async def _enrich(self, ts: TestSet) -> TestSetResponse:
        count_result = await self.db.execute(
            select(func.count()).where(TestCase.test_set_id == ts.id)
        )
        test_case_count = count_result.scalar() or 0

        last_run_result = await self.db.execute(
            select(EvaluationRun.status)
            .where(EvaluationRun.test_set_id == ts.id)
            .order_by(EvaluationRun.started_at.desc())
            .limit(1)
        )
        last_run_status = last_run_result.scalar_one_or_none()

        return self._to_response(
            ts,
            test_case_count=test_case_count,
            last_run_status=last_run_status.value if last_run_status else None,
        )

    @staticmethod
    def _to_response(
        ts: TestSet, test_case_count: int, last_run_status: str | None
    ) -> TestSetResponse:
        return TestSetResponse(
            id=ts.id,
            name=ts.name,
            description=ts.description,
            version=ts.version,
            created_at=ts.created_at,
            updated_at=ts.updated_at,
            test_case_count=test_case_count,
            last_run_status=last_run_status,
        )
