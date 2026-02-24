"""
Service for ingesting production Q&A traffic.

Handles single and bulk ingestion, delegates sampling decisions
to the SamplingService, and returns ingestion statistics.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.ingestion import (
    IngestResponse,
    ProductionLogIngest,
    ProductionLogResponse,
)
from app.core.exceptions import NotFoundError
from app.db.models.production_log import IngestionStatus, ProductionLog
from app.services.sampling_service import SamplingService


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.sampler = SamplingService(db)

    async def ingest(self, items: list[ProductionLogIngest]) -> IngestResponse:
        """Ingest one or more production Q&A pairs and apply sampling."""
        sampled_count = 0
        skipped_count = 0

        for item in items:
            log = ProductionLog(
                id=uuid.uuid4(),
                source=item.source,
                pipeline_version=item.pipeline_version,
                query=item.query,
                answer=item.answer,
                contexts=item.contexts,
                tool_calls=item.tool_calls,
                latency_ms=item.latency_ms,
                user_feedback=item.user_feedback,
                confidence_score=item.confidence_score,
                is_error=item.is_error,
                error_message=item.error_message,
                tags=item.tags,
                extra_metadata=item.metadata,
                produced_at=item.produced_at,
                status=IngestionStatus.RECEIVED,
            )
            self.db.add(log)
            await self.db.flush()

            was_sampled = await self.sampler.sample_and_create_test_case(log)
            if was_sampled:
                sampled_count += 1
            else:
                skipped_count += 1

        return IngestResponse(
            ingested=len(items),
            sampled=sampled_count,
            skipped=skipped_count,
        )

    async def list_logs(
        self,
        source: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ProductionLogResponse]:
        query = select(ProductionLog).order_by(ProductionLog.ingested_at.desc())
        if source:
            query = query.where(ProductionLog.source == source)
        if status:
            query = query.where(ProductionLog.status == status)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return [ProductionLogResponse.model_validate(r) for r in result.scalars().all()]

    async def get_log(self, log_id: uuid.UUID) -> ProductionLogResponse:
        result = await self.db.execute(
            select(ProductionLog).where(ProductionLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        if log is None:
            raise NotFoundError("ProductionLog", str(log_id))
        return ProductionLogResponse.model_validate(log)
