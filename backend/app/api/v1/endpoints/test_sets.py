import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.test_set import TestSetCreate, TestSetResponse, TestSetUpdate
from app.db.session import get_db
from app.services.test_set_service import TestSetService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> TestSetService:
    return TestSetService(db)


@router.post("/", response_model=TestSetResponse, status_code=201)
async def create_test_set(
    payload: TestSetCreate,
    service: Annotated[TestSetService, Depends(get_service)],
):
    return await service.create(payload)


@router.get("/", response_model=list[TestSetResponse])
async def list_test_sets(
    service: Annotated[TestSetService, Depends(get_service)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return await service.list(skip=skip, limit=limit)


@router.get("/{test_set_id}", response_model=TestSetResponse)
async def get_test_set(
    test_set_id: uuid.UUID,
    service: Annotated[TestSetService, Depends(get_service)],
):
    return await service.get(test_set_id)


@router.put("/{test_set_id}", response_model=TestSetResponse)
async def update_test_set(
    test_set_id: uuid.UUID,
    payload: TestSetUpdate,
    service: Annotated[TestSetService, Depends(get_service)],
):
    return await service.update(test_set_id, payload)


@router.delete("/{test_set_id}", status_code=204)
async def delete_test_set(
    test_set_id: uuid.UUID,
    service: Annotated[TestSetService, Depends(get_service)],
):
    await service.delete(test_set_id)


@router.get("/{test_set_id}/export")
async def export_test_set(
    test_set_id: uuid.UUID,
    service: Annotated[TestSetService, Depends(get_service)],
):
    return await service.export(test_set_id)
