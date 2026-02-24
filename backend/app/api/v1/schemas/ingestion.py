"""Schemas for production traffic ingestion."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models.production_log import IngestionStatus


class ProductionLogIngest(BaseModel):
    """A single production Q&A pair to ingest."""
    source: str = Field(..., description="Pipeline/system identifier, e.g. 'customer-support-bot'")
    pipeline_version: str | None = None
    query: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    contexts: list[str] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    latency_ms: int | None = None
    user_feedback: str | None = Field(None, pattern=r"^(thumbs_up|thumbs_down)$")
    confidence_score: float | None = Field(None, ge=0.0, le=1.0)
    is_error: bool = False
    error_message: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None
    produced_at: datetime | None = None


class ProductionLogBulkIngest(BaseModel):
    """Bulk ingest multiple Q&A pairs at once."""
    items: list[ProductionLogIngest] = Field(..., min_length=1, max_length=500)


class ProductionLogResponse(BaseModel):
    id: uuid.UUID
    source: str
    query: str
    answer: str
    is_error: bool
    status: IngestionStatus
    confidence_score: float | None
    user_feedback: str | None
    ingested_at: datetime
    sampled_into_test_set_id: uuid.UUID | None
    evaluation_run_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class IngestResponse(BaseModel):
    ingested: int
    sampled: int
    skipped: int


class SamplingStats(BaseModel):
    source: str
    total_received: int
    total_sampled: int
    total_skipped: int
    total_evaluated: int
    sampling_rate: float
    error_sampling_rate: float


class FeedbackUpdate(BaseModel):
    """User feedback on a production log entry."""
    feedback: str = Field(..., pattern=r"^(thumbs_up|thumbs_down)$")


class FeedbackStats(BaseModel):
    """Aggregated feedback statistics."""
    source: str | None
    total: int
    thumbs_up: int
    thumbs_down: int
    no_feedback: int
    positive_rate: float | None
