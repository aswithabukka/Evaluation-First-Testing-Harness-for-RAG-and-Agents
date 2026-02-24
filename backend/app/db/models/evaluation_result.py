import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Ragas metrics (0.0–1.0, null if not evaluated)
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_recall: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Rule evaluation
    rules_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Per-rule breakdown: [{"rule": {...}, "passed": false, "reason": "..."}]
    rules_detail: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # LLM-as-judge (stretch goal)
    llm_judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_judge_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Aggregate
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Raw pipeline outputs stored for debugging
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_contexts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Cost tracking
    eval_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Extended metrics for non-RAG systems (stored as JSONB for flexibility)
    extended_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    run: Mapped["EvaluationRun"] = relationship(  # noqa: F821
        "EvaluationRun", back_populates="evaluation_results"
    )
    test_case: Mapped["TestCase"] = relationship(  # noqa: F821
        "TestCase", back_populates="evaluation_results"
    )

    def __repr__(self) -> str:
        return f"<EvaluationResult id={self.id} passed={self.passed}>"
