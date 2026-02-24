import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.evaluation_result import RegressionDiff
from app.api.v1.schemas.evaluation_run import (
    EvaluationRunCreate,
    EvaluationRunResponse,
    RunStatusResponse,
)
from app.db.session import get_db
from app.services.evaluation_service import EvaluationService
from app.services.release_gate_service import ReleaseGateService

router = APIRouter()


class MultiRunRequest(BaseModel):
    """Trigger multiple evaluation runs with different pipeline configs."""
    test_set_id: uuid.UUID
    configs: list[dict[str, Any]] = Field(..., min_length=2, max_length=6)


def get_eval_service(db: AsyncSession = Depends(get_db)) -> EvaluationService:
    return EvaluationService(db)


def get_gate_service(db: AsyncSession = Depends(get_db)) -> ReleaseGateService:
    return ReleaseGateService(db)


@router.post("/", response_model=EvaluationRunResponse, status_code=202)
async def trigger_evaluation_run(
    payload: EvaluationRunCreate,
    service: Annotated[EvaluationService, Depends(get_eval_service)],
):
    """Trigger a new async evaluation run. Returns immediately with run_id."""
    return await service.create_run(payload)


@router.post("/multi", status_code=202)
async def trigger_multi_run(
    payload: MultiRunRequest,
    service: Annotated[EvaluationService, Depends(get_eval_service)],
):
    """Trigger multiple evaluation runs with different pipeline configs for comparison."""
    run_ids = []
    for config in payload.configs:
        model_name = config.get("model", "unknown")
        run_data = EvaluationRunCreate(
            test_set_id=payload.test_set_id,
            pipeline_version=f"multi-compare/{model_name}",
            triggered_by="multi-model-compare",
            pipeline_config=config,
        )
        run = await service.create_run(run_data)
        run_ids.append(str(run.id))

    compare_url = f"/runs/compare?ids={','.join(run_ids)}"
    return {"run_ids": run_ids, "compare_url": compare_url}


@router.get("/", response_model=list[EvaluationRunResponse])
async def list_runs(
    service: Annotated[EvaluationService, Depends(get_eval_service)],
    test_set_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    git_branch: str | None = Query(None),
    git_commit_sha: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return await service.list_runs(
        test_set_id=test_set_id,
        status=status,
        git_branch=git_branch,
        git_commit_sha=git_commit_sha,
        skip=skip,
        limit=limit,
    )


@router.get("/{run_id}", response_model=EvaluationRunResponse)
async def get_run(
    run_id: uuid.UUID,
    service: Annotated[EvaluationService, Depends(get_eval_service)],
):
    return await service.get_run(run_id)


@router.get("/{run_id}/status", response_model=RunStatusResponse)
async def get_run_status(
    run_id: uuid.UUID,
    service: Annotated[EvaluationService, Depends(get_eval_service)],
):
    """Lightweight polling endpoint for CI pipelines."""
    return await service.get_run_status(run_id)


@router.get("/{run_id}/diff", response_model=RegressionDiff)
async def get_regression_diff(
    run_id: uuid.UUID,
    gate_service: Annotated[ReleaseGateService, Depends(get_gate_service)],
):
    """Diff this run against the last passing baseline run."""
    return await gate_service.compute_regression_diff(run_id)


@router.post("/{run_id}/cancel", status_code=202)
async def cancel_run(
    run_id: uuid.UUID,
    service: Annotated[EvaluationService, Depends(get_eval_service)],
):
    await service.cancel_run(run_id)
    return {"message": "Cancellation requested"}
