import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.test_case import (
    TestCaseBulkCreate,
    TestCaseCreate,
    TestCaseResponse,
    TestCaseUpdate,
)
from app.db.session import get_db
from app.services.test_case_service import TestCaseService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> TestCaseService:
    return TestCaseService(db)


@router.post("/{test_set_id}/cases", response_model=TestCaseResponse, status_code=201)
async def create_test_case(
    test_set_id: uuid.UUID,
    payload: TestCaseCreate,
    service: Annotated[TestCaseService, Depends(get_service)],
):
    return await service.create(test_set_id, payload)


@router.post("/{test_set_id}/cases/bulk", response_model=list[TestCaseResponse], status_code=201)
async def bulk_create_test_cases(
    test_set_id: uuid.UUID,
    payload: TestCaseBulkCreate,
    service: Annotated[TestCaseService, Depends(get_service)],
):
    return await service.bulk_create(test_set_id, payload.cases)


@router.get("/{test_set_id}/cases", response_model=list[TestCaseResponse])
async def list_test_cases(
    test_set_id: uuid.UUID,
    service: Annotated[TestCaseService, Depends(get_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    tag: str | None = Query(None),
):
    return await service.list(test_set_id, skip=skip, limit=limit, tag=tag)


@router.get("/{test_set_id}/cases/{case_id}", response_model=TestCaseResponse)
async def get_test_case(
    test_set_id: uuid.UUID,
    case_id: uuid.UUID,
    service: Annotated[TestCaseService, Depends(get_service)],
):
    return await service.get(test_set_id, case_id)


@router.put("/{test_set_id}/cases/{case_id}", response_model=TestCaseResponse)
async def update_test_case(
    test_set_id: uuid.UUID,
    case_id: uuid.UUID,
    payload: TestCaseUpdate,
    service: Annotated[TestCaseService, Depends(get_service)],
):
    return await service.update(test_set_id, case_id, payload)


@router.delete("/{test_set_id}/cases/{case_id}", status_code=204)
async def delete_test_case(
    test_set_id: uuid.UUID,
    case_id: uuid.UUID,
    service: Annotated[TestCaseService, Depends(get_service)],
):
    await service.delete(test_set_id, case_id)
