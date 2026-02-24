import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.evaluation_result import EvaluationResultResponse, ResultSummary
from app.db.models.evaluation_result import EvaluationResult
from app.db.models.test_case import TestCase
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


@router.get("/export")
async def export_results(
    run_id: uuid.UUID = Query(...),
    format: str = Query("csv", regex="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
):
    """Export run results as CSV or JSON, including test case queries and extended metrics."""
    # Fetch results joined with test cases
    stmt = (
        select(EvaluationResult, TestCase)
        .outerjoin(TestCase, EvaluationResult.test_case_id == TestCase.id)
        .where(EvaluationResult.run_id == run_id)
        .order_by(EvaluationResult.created_at)
    )
    rows = (await db.execute(stmt)).all()

    # Collect all extended_metrics keys across results
    ext_keys: list[str] = []
    seen_keys: set[str] = set()
    for result, _ in rows:
        if result.extended_metrics:
            for k in result.extended_metrics:
                if k not in seen_keys:
                    ext_keys.append(k)
                    seen_keys.add(k)

    if format == "json":
        data = []
        for result, tc in rows:
            row = {
                "id": str(result.id),
                "test_case_id": str(result.test_case_id),
                "query": tc.query if tc else None,
                "expected_output": tc.expected_output if tc else None,
                "raw_output": result.raw_output,
                "passed": result.passed,
                "failure_reason": result.failure_reason,
                "faithfulness": result.faithfulness,
                "answer_relevancy": result.answer_relevancy,
                "context_precision": result.context_precision,
                "context_recall": result.context_recall,
                "rules_passed": result.rules_passed,
                "duration_ms": result.duration_ms,
            }
            if result.extended_metrics:
                for k in ext_keys:
                    row[k] = result.extended_metrics.get(k)
            data.append(row)
        return JSONResponse(content=data, headers={
            "Content-Disposition": f'attachment; filename="run_{str(run_id)[:8]}_results.json"',
        })

    # CSV export
    base_columns = [
        "id", "test_case_id", "query", "expected_output", "raw_output",
        "passed", "failure_reason", "faithfulness", "answer_relevancy",
        "context_precision", "context_recall", "rules_passed", "duration_ms",
    ]
    all_columns = base_columns + ext_keys

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=all_columns)
    writer.writeheader()

    for result, tc in rows:
        row = {
            "id": str(result.id),
            "test_case_id": str(result.test_case_id),
            "query": tc.query if tc else "",
            "expected_output": tc.expected_output if tc else "",
            "raw_output": result.raw_output or "",
            "passed": result.passed,
            "failure_reason": result.failure_reason or "",
            "faithfulness": result.faithfulness,
            "answer_relevancy": result.answer_relevancy,
            "context_precision": result.context_precision,
            "context_recall": result.context_recall,
            "rules_passed": result.rules_passed,
            "duration_ms": result.duration_ms,
        }
        if result.extended_metrics:
            for k in ext_keys:
                row[k] = result.extended_metrics.get(k)
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="run_{str(run_id)[:8]}_results.csv"',
        },
    )


@router.get("/{result_id}", response_model=EvaluationResultResponse)
async def get_result(
    result_id: uuid.UUID,
    service: Annotated[EvaluationService, Depends(get_service)],
):
    return await service.get_result(result_id)
