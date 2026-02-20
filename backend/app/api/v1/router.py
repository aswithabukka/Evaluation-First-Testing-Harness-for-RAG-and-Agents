from fastapi import APIRouter

from app.api.v1.endpoints import (
    evaluation_results,
    evaluation_runs,
    health,
    metrics,
    test_cases,
    test_sets,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(test_sets.router, prefix="/test-sets", tags=["Test Sets"])
api_router.include_router(test_cases.router, prefix="/test-sets", tags=["Test Cases"])
api_router.include_router(evaluation_runs.router, prefix="/runs", tags=["Evaluation Runs"])
api_router.include_router(evaluation_results.router, prefix="/results", tags=["Results"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["Metrics"])
