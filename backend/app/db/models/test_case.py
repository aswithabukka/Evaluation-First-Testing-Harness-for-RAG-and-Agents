import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    test_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional — some tests only check non-hallucination without a strict expected answer
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    ground_truth: Mapped[str | None] = mapped_column(Text, nullable=True)
    # List of context strings that should be used as retrieval context
    context: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Structured failure rules, e.g.:
    # [{"type": "must_call_tool", "tool": "drug_lookup"},
    #  {"type": "must_not_contain", "value": "I don't know"}]
    failure_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    # Tags for filtering, e.g. ["safety", "dosage", "refusal"]
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    test_set: Mapped["TestSet"] = relationship("TestSet", back_populates="test_cases")  # noqa: F821
    evaluation_results: Mapped[list["EvaluationResult"]] = relationship(  # noqa: F821
        "EvaluationResult", back_populates="test_case"
    )

    def __repr__(self) -> str:
        return f"<TestCase id={self.id} query={self.query[:40]!r}>"
