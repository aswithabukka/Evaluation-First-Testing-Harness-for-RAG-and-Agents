import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.test_case import TestCaseCreate, TestCaseResponse, TestCaseUpdate
from app.core.exceptions import NotFoundError
from app.db.models.test_case import TestCase
from app.db.models.test_set import TestSet


class TestCaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, test_set_id: uuid.UUID, payload: TestCaseCreate) -> TestCaseResponse:
        await self._assert_test_set_exists(test_set_id)
        tc = TestCase(
            test_set_id=test_set_id,
            query=payload.query,
            expected_output=payload.expected_output,
            ground_truth=payload.ground_truth,
            context=payload.context,
            failure_rules=[r.model_dump(exclude_none=True) for r in payload.failure_rules]
            if payload.failure_rules
            else [],
            tags=payload.tags or [],
        )
        self.db.add(tc)
        await self.db.flush()
        await self.db.refresh(tc)
        await self._bump_version(test_set_id)
        return TestCaseResponse.model_validate(tc)

    async def bulk_create(
        self, test_set_id: uuid.UUID, cases: list[TestCaseCreate]
    ) -> list[TestCaseResponse]:
        await self._assert_test_set_exists(test_set_id)
        tcs = [
            TestCase(
                test_set_id=test_set_id,
                query=c.query,
                expected_output=c.expected_output,
                ground_truth=c.ground_truth,
                context=c.context,
                failure_rules=[r.model_dump(exclude_none=True) for r in c.failure_rules]
                if c.failure_rules
                else [],
                tags=c.tags or [],
            )
            for c in cases
        ]
        self.db.add_all(tcs)
        await self.db.flush()
        for tc in tcs:
            await self.db.refresh(tc)
        await self._bump_version(test_set_id)
        return [TestCaseResponse.model_validate(tc) for tc in tcs]

    async def list(
        self,
        test_set_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
        tag: str | None = None,
    ) -> list[TestCaseResponse]:
        query = select(TestCase).where(TestCase.test_set_id == test_set_id)
        if tag:
            query = query.where(TestCase.tags.contains([tag]))
        query = query.order_by(TestCase.created_at.asc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return [TestCaseResponse.model_validate(tc) for tc in result.scalars().all()]

    async def get(self, test_set_id: uuid.UUID, case_id: uuid.UUID) -> TestCaseResponse:
        tc = await self._get_or_404(test_set_id, case_id)
        return TestCaseResponse.model_validate(tc)

    async def update(
        self, test_set_id: uuid.UUID, case_id: uuid.UUID, payload: TestCaseUpdate
    ) -> TestCaseResponse:
        tc = await self._get_or_404(test_set_id, case_id)
        if payload.query is not None:
            tc.query = payload.query
        if payload.expected_output is not None:
            tc.expected_output = payload.expected_output
        if payload.ground_truth is not None:
            tc.ground_truth = payload.ground_truth
        if payload.context is not None:
            tc.context = payload.context
        if payload.failure_rules is not None:
            tc.failure_rules = [r.model_dump(exclude_none=True) for r in payload.failure_rules]
        if payload.tags is not None:
            tc.tags = payload.tags
        await self.db.flush()
        await self.db.refresh(tc)
        await self._bump_version(test_set_id)
        return TestCaseResponse.model_validate(tc)

    async def delete(self, test_set_id: uuid.UUID, case_id: uuid.UUID) -> None:
        tc = await self._get_or_404(test_set_id, case_id)
        await self.db.delete(tc)
        await self._bump_version(test_set_id)

    async def _get_or_404(self, test_set_id: uuid.UUID, case_id: uuid.UUID) -> TestCase:
        result = await self.db.execute(
            select(TestCase).where(
                TestCase.id == case_id, TestCase.test_set_id == test_set_id
            )
        )
        tc = result.scalar_one_or_none()
        if tc is None:
            raise NotFoundError("TestCase", str(case_id))
        return tc

    async def _assert_test_set_exists(self, test_set_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(TestSet.id).where(TestSet.id == test_set_id)
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError("TestSet", str(test_set_id))

    async def _bump_version(self, test_set_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(TestSet).where(TestSet.id == test_set_id)
        )
        ts = result.scalar_one_or_none()
        if ts:
            major, minor = ts.version.split(".")
            ts.version = f"{major}.{int(minor) + 1}"
            await self.db.flush()
