"""
Production traffic ingestion endpoints.

POST /ingest        — Ingest a single Q&A pair
POST /ingest/bulk   — Ingest multiple Q&A pairs at once
GET  /ingest/logs   — List ingested production logs
GET  /ingest/logs/{id} — Get a specific production log
GET  /ingest/stats  — Sampling statistics per source
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.ingestion import (
    IngestResponse,
    ProductionLogBulkIngest,
    ProductionLogIngest,
    ProductionLogResponse,
    SamplingStats,
)
from app.core.auth import require_api_key
from app.db.session import get_db
from app.services.ingestion_service import IngestionService
from app.services.sampling_service import SamplingService

router = APIRouter()


def get_ingestion_service(db: AsyncSession = Depends(get_db)) -> IngestionService:
    return IngestionService(db)


def get_sampling_service(db: AsyncSession = Depends(get_db)) -> SamplingService:
    return SamplingService(db)


@router.post("/", response_model=IngestResponse, status_code=202)
async def ingest_single(
    payload: ProductionLogIngest,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
    _api_key: str | None = Depends(require_api_key),
):
    """
    Ingest a single production Q&A pair.

    The system automatically applies stratified sampling to decide whether
    this entry will be evaluated:
    - 100% of errors and negative feedback are sampled
    - ~20% of normal traffic is sampled (configurable via SAMPLING_RATE)
    """
    return await service.ingest([payload])


@router.post("/bulk", response_model=IngestResponse, status_code=202)
async def ingest_bulk(
    payload: ProductionLogBulkIngest,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
    _api_key: str | None = Depends(require_api_key),
):
    """
    Ingest multiple production Q&A pairs at once (up to 500).

    Same sampling logic applies to each entry individually.
    """
    return await service.ingest(payload.items)


@router.get("/logs", response_model=list[ProductionLogResponse])
async def list_production_logs(
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
    source: str | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _api_key: str | None = Depends(require_api_key),
):
    """List ingested production logs with optional filters."""
    return await service.list_logs(source=source, status=status, skip=skip, limit=limit)


@router.get("/logs/{log_id}", response_model=ProductionLogResponse)
async def get_production_log(
    log_id: uuid.UUID,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
    _api_key: str | None = Depends(require_api_key),
):
    """Get a specific production log entry."""
    return await service.get_log(log_id)


@router.get("/stats", response_model=list[SamplingStats])
async def get_sampling_stats(
    sampling_service: Annotated[SamplingService, Depends(get_sampling_service)],
    source: str | None = Query(None),
    _api_key: str | None = Depends(require_api_key),
):
    """Get sampling statistics per source."""
    return await sampling_service.get_stats(source=source)
