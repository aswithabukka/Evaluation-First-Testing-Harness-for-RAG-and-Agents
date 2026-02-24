from pydantic import BaseModel, Field


class PlaygroundRequest(BaseModel):
    system_type: str = Field(
        ...,
        description="One of: rag, agent, chatbot, search",
        pattern="^(rag|agent|chatbot|search)$",
    )
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(
        None,
        description="Session ID for multi-turn chatbot conversations. Omit to start new.",
    )


class ToolCallResponse(BaseModel):
    tool: str
    args: dict
    result: dict | None = None


class PlaygroundResponse(BaseModel):
    answer: str
    retrieved_contexts: list[str] = []
    tool_calls: list[ToolCallResponse] = []
    turn_history: list[dict] = []
    metadata: dict = {}
    session_id: str | None = None


class PlaygroundSystemInfo(BaseModel):
    system_type: str
    name: str
    description: str
    icon: str
    color: str
    sample_queries: list[str]


class DocumentUploadRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, description="List of document texts to add")


class DocumentListResponse(BaseModel):
    documents: list[str]
    count: int


class DocumentUploadResponse(BaseModel):
    added: int
    total: int
