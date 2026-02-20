import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models.evaluation_run import RunStatus


class ThresholdConfig(BaseModel):
    faithfulness: float = Field(0.7, ge=0.0, le=1.0)
    answer_relevancy: float = Field(0.7, ge=0.0, le=1.0)
    context_precision: float = Field(0.6, ge=0.0, le=1.0)
    context_recall: float = Field(0.6, ge=0.0, le=1.0)
    pass_rate: float = Field(0.8, ge=0.0, le=1.0)


class EvaluationRunCreate(BaseModel):
    test_set_id: uuid.UUID
    pipeline_version: str | None = None
    git_commit_sha: str | None = None
    git_branch: str | None = None
    git_pr_number: str | None = None
    triggered_by: str = "manual"
    thresholds: ThresholdConfig | None = None
    metrics: list[str] = Field(
        default_factory=lambda: [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "rule_evaluation",
        ]
    )
    # Changelog: what changed in this pipeline version
    notes: str | None = None
    # Optional structured config override (normally auto-captured from the adapter)
    pipeline_config: dict | None = None


class EvaluationRunResponse(BaseModel):
    id: uuid.UUID
    test_set_id: uuid.UUID
    pipeline_version: str | None
    git_commit_sha: str | None
    git_branch: str | None
    git_pr_number: str | None
    status: RunStatus
    triggered_by: str
    started_at: datetime
    completed_at: datetime | None
    overall_passed: bool | None
    gate_threshold_snapshot: dict[str, Any] | None
    summary_metrics: dict[str, Any] | None
    notes: str | None
    pipeline_config: dict[str, Any] | None

    model_config = {"from_attributes": True}


class RunStatusResponse(BaseModel):
    run_id: uuid.UUID
    status: RunStatus
    overall_passed: bool | None
    completed_at: datetime | None
