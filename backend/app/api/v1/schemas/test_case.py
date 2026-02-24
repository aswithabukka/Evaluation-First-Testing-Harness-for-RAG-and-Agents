import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FailureRule(BaseModel):
    type: str
    value: str | None = None
    tool: str | None = None
    threshold: float | None = None
    pattern: str | None = None
    plugin_class: str | None = None


class TestCaseCreate(BaseModel):
    query: str = Field(..., min_length=1)
    expected_output: str | None = None
    ground_truth: str | None = None
    context: list[str] | None = None
    failure_rules: list[FailureRule] | None = Field(default_factory=list)
    tags: list[str] | None = Field(default_factory=list)
    # Classification systems
    expected_labels: list[str] | None = None
    # Search/retrieval systems
    expected_ranking: list[str] | None = None
    # Chatbot multi-turn
    conversation_turns: list[dict[str, Any]] | None = None


class TestCaseBulkCreate(BaseModel):
    cases: list[TestCaseCreate]


class TestCaseUpdate(BaseModel):
    query: str | None = None
    expected_output: str | None = None
    ground_truth: str | None = None
    context: list[str] | None = None
    failure_rules: list[FailureRule] | None = None
    tags: list[str] | None = None
    expected_labels: list[str] | None = None
    expected_ranking: list[str] | None = None
    conversation_turns: list[dict[str, Any]] | None = None


class TestCaseResponse(BaseModel):
    id: uuid.UUID
    test_set_id: uuid.UUID
    query: str
    expected_output: str | None
    ground_truth: str | None
    context: list[Any] | None
    failure_rules: list[Any] | None
    tags: list[Any] | None
    expected_labels: list[Any] | None = None
    expected_ranking: list[Any] | None = None
    conversation_turns: list[Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
