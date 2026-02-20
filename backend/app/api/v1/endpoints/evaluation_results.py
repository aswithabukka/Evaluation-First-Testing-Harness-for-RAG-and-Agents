import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.evaluation_result import EvaluationResultResponse, ResultSummary
from app.db.session import get_db
from app.services.evaluation_service import EvaluationService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> EvaluationService:
    return EvaluationService(db)


@router.get("/", response_model=list[EvaluationResultResponse])
async def list_results(
    service: Annotated[EvaluationService, Depends(get_service)],
    run_id: uuid.UUID = Query(...),
    passed: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return await service.list_results(run_id=run_id, passed=passed, skip=skip, limit=limit)


@router.get("/summary", response_model=ResultSummary)
async def get_results_summary(
    run_id: uuid.UUID,
    service: Annotated[EvaluationService, Depends(get_service)],
):
    return await service.get_results_summary(run_id)


@router.get("/{result_id}", response_model=EvaluationResultResponse)
async def get_result(
    result_id: uuid.UUID,
    service: Annotated[EvaluationService, Depends(get_service)],
):
    return await service.get_result(result_id)
