import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.metrics_service import MetricsService
from app.services.release_gate_service import ReleaseGateService

router = APIRouter()


def get_metrics_service(db: AsyncSession = Depends(get_db)) -> MetricsService:
    return MetricsService(db)


def get_gate_service(db: AsyncSession = Depends(get_db)) -> ReleaseGateService:
    return ReleaseGateService(db)


@router.get("/trends")
async def get_metric_trends(
    service: Annotated[MetricsService, Depends(get_metrics_service)],
    test_set_id: uuid.UUID = Query(...),
    metric: str = Query(..., description="e.g. faithfulness, answer_relevancy"),
    days: int = Query(30, ge=1, le=365),
):
    return await service.get_trends(test_set_id=test_set_id, metric=metric, days=days)


@router.get("/thresholds/{test_set_id}")
async def get_thresholds(
    test_set_id: uuid.UUID,
    gate_service: Annotated[ReleaseGateService, Depends(get_gate_service)],
):
    return await gate_service.get_thresholds(test_set_id)


@router.put("/thresholds/{test_set_id}")
async def update_thresholds(
    test_set_id: uuid.UUID,
    thresholds: dict,
    gate_service: Annotated[ReleaseGateService, Depends(get_gate_service)],
):
    return await gate_service.update_thresholds(test_set_id, thresholds)


@router.get("/gate/{run_id}")
async def check_release_gate(
    run_id: uuid.UUID,
    gate_service: Annotated[ReleaseGateService, Depends(get_gate_service)],
):
    """Returns gate decision for a completed run."""
    return await gate_service.evaluate_gate(run_id)
