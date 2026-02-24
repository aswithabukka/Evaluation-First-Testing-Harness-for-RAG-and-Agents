import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SystemType(str, enum.Enum):
    RAG = "rag"
    AGENT = "agent"
    CHATBOT = "chatbot"
    CODE_GEN = "code_gen"
    SEARCH = "search"
    CLASSIFICATION = "classification"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    CUSTOM = "custom"


class TestSet(Base):
    __tablename__ = "test_sets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_type: Mapped[SystemType] = mapped_column(
        Enum(SystemType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SystemType.RAG,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    test_cases: Mapped[list["TestCase"]] = relationship(  # noqa: F821
        "TestCase", back_populates="test_set", cascade="all, delete-orphan"
    )
    evaluation_runs: Mapped[list["EvaluationRun"]] = relationship(  # noqa: F821
        "EvaluationRun", back_populates="test_set"
    )

    def __repr__(self) -> str:
        return f"<TestSet id={self.id} name={self.name!r}>"
