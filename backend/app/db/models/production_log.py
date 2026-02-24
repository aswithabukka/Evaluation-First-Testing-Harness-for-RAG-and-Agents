"""
ProductionLog — stores ingested production Q&A pairs.

Production systems POST their Q&A interactions here via /api/v1/ingest.
The sampling engine decides which entries become test cases for evaluation.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestionStatus(str, enum.Enum):
    RECEIVED = "received"      # Just ingested, not yet sampled
    SAMPLED = "sampled"        # Selected for evaluation
    SKIPPED = "skipped"        # Not selected by sampling
    EVALUATED = "evaluated"    # Evaluation complete


class ProductionLog(Base):
    """
    Append-only log of production Q&A interactions.

    Each row represents one user query → system answer pair from a live
    production system. The sampling engine periodically selects entries
    for evaluation based on configured sampling rates.
    """
    __tablename__ = "production_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Which pipeline/system produced this
    source: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # The Q&A pair
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    contexts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Production metadata
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_feedback: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "thumbs_up" | "thumbs_down" | None
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # Model confidence if available
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Sampling & evaluation tracking
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=IngestionStatus.RECEIVED,
        index=True,
    )
    sampled_into_test_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_sets.id", ondelete="SET NULL"),
        nullable=True,
    )
    sampled_into_test_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    evaluation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    produced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # When the production system served this
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sampled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<ProductionLog id={self.id} source={self.source} status={self.status}>"
