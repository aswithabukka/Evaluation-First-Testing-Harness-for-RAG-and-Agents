import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    GATE_BLOCKED = "gate_blocked"


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    git_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    git_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    git_pr_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=RunStatus.PENDING,
        index=True,
    )
    triggered_by: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )  # "ci" | "manual" | "api"
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    overall_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Snapshot of thresholds at run time — immutable audit trail
    gate_threshold_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Cached aggregate scores for fast dashboard reads
    summary_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Free-text changelog: what changed in this pipeline version
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured pipeline config captured at run time (model, top_k, embedding_model, etc.)
    pipeline_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    test_set: Mapped["TestSet"] = relationship(  # noqa: F821
        "TestSet", back_populates="evaluation_runs"
    )
    evaluation_results: Mapped[list["EvaluationResult"]] = relationship(  # noqa: F821
        "EvaluationResult", back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<EvaluationRun id={self.id} status={self.status}>"
