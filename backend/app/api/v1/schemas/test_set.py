import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TestSetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    system_type: str = Field(
        "rag",
        description="AI system type: rag, agent, chatbot, code_gen, search, classification, summarization, translation, custom",
    )


class TestSetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    system_type: str | None = None


class TestSetResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    system_type: str
    version: str
    created_at: datetime
    updated_at: datetime
    test_case_count: int = 0
    last_run_status: str | None = None

    model_config = {"from_attributes": True}
