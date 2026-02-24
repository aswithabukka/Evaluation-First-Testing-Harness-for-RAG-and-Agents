"""
Playground endpoint — interactive demo of the 4 AI systems.

Adapter lifecycle:
- Stateless adapters (RAG, Agent, Search) are cached as singletons.
  setup() is called once on first use.
- Chatbot adapters are cached per session_id (separate conversation histories).
  Sessions are evicted after 30 minutes of inactivity.
"""
import asyncio
import importlib
import logging
import time
import uuid
from threading import Lock

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File

from app.api.v1.schemas.ingestion import ProductionLogIngest
from app.api.v1.schemas.playground import (
    DocumentListResponse,
    DocumentUploadRequest,
    DocumentUploadResponse,
    PlaygroundRequest,
    PlaygroundResponse,
    PlaygroundSystemInfo,
    ToolCallResponse,
)
from app.db.session import AsyncSessionLocal
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

router = APIRouter()

# ── System registry ────────────────────────────────────────────────────

SYSTEM_CONFIGS = {
    "rag": {
        "module": "runner.adapters.demo_rag",
        "class": "DemoRAGAdapter",
        "name": "RAG Pipeline",
        "description": "Embedding-based retrieval + GPT-4o-mini generation. Ask factual questions and see which context chunks are retrieved.",
        "icon": "\U0001f50d",
        "color": "blue",
        "sample_queries": [
            "What is the capital of France?",
            "Explain photosynthesis",
            "What are the symptoms of diabetes?",
            "What is the difference between RAM and ROM?",
            "Who wrote Pride and Prejudice?",
        ],
    },
    "agent": {
        "module": "runner.adapters.demo_tool_agent",
        "class": "DemoToolAgentAdapter",
        "name": "Tool Agent",
        "description": "Function-calling agent with calculator, weather, unit converter, and web search tools. Ask questions that require tool use.",
        "icon": "\U0001f916",
        "color": "purple",
        "sample_queries": [
            "What is 247 * 389?",
            "What's the weather in Tokyo?",
            "Convert 100 km to miles",
            "Who won the Super Bowl this year?",
            "What is the current price of Bitcoin?",
        ],
    },
    "chatbot": {
        "module": "runner.adapters.demo_chatbot",
        "class": "DemoChatbotAdapter",
        "name": "Support Chatbot",
        "description": "Multi-turn TechStore customer support agent. Have a conversation about products, orders, returns, and warranties.",
        "icon": "\U0001f4ac",
        "color": "pink",
        "sample_queries": [
            "Hi, I need help with a recent order",
            "What laptops do you have under $1000?",
            "What is your return policy?",
            "I want to track order TS-12345",
            "Do you offer extended warranties?",
        ],
    },
    "search": {
        "module": "runner.adapters.demo_search",
        "class": "DemoSearchAdapter",
        "name": "Search Engine",
        "description": "Semantic search over a 25-document developer knowledge base with Google search fallback for off-topic queries.",
        "icon": "\U0001f50e",
        "color": "teal",
        "sample_queries": [
            "How do I sort a list in Python?",
            "Docker container basics",
            "REST API design best practices",
            "What are React hooks?",
            "Redis caching patterns",
        ],
    },
}

# ── Adapter cache ──────────────────────────────────────────────────────

_adapter_cache: dict[str, object] = {}
_adapter_lock = Lock()

_chatbot_sessions: dict[str, tuple[object, float]] = {}
_chatbot_lock = Lock()
_SESSION_TTL = 1800  # 30 minutes


def _get_adapter(system_type: str, session_id: str | None = None):
    config = SYSTEM_CONFIGS[system_type]

    if system_type == "chatbot":
        with _chatbot_lock:
            now = time.time()
            # Evict stale sessions
            stale = [sid for sid, (_, ts) in _chatbot_sessions.items() if now - ts > _SESSION_TTL]
            for sid in stale:
                a, _ = _chatbot_sessions.pop(sid)
                try:
                    a.teardown()
                except Exception:
                    pass

            if session_id and session_id in _chatbot_sessions:
                adapter, _ = _chatbot_sessions[session_id]
                _chatbot_sessions[session_id] = (adapter, now)
                return adapter, session_id

            new_id = session_id or str(uuid.uuid4())
            mod = importlib.import_module(config["module"])
            cls = getattr(mod, config["class"])
            adapter = cls()
            adapter.setup()
            _chatbot_sessions[new_id] = (adapter, now)
            return adapter, new_id
    else:
        with _adapter_lock:
            if system_type not in _adapter_cache:
                mod = importlib.import_module(config["module"])
                cls = getattr(mod, config["class"])
                adapter = cls()
                adapter.setup()
                _adapter_cache[system_type] = adapter
            return _adapter_cache[system_type], None


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get("/systems", response_model=list[PlaygroundSystemInfo])
async def list_systems():
    return [
        PlaygroundSystemInfo(
            system_type=st,
            name=cfg["name"],
            description=cfg["description"],
            icon=cfg["icon"],
            color=cfg["color"],
            sample_queries=cfg["sample_queries"],
        )
        for st, cfg in SYSTEM_CONFIGS.items()
    ]


async def _ingest_playground_interaction(
    system_type: str,
    query: str,
    answer: str,
    contexts: list[str] | None,
    tool_calls_data: list[dict] | None,
    latency_ms: int,
    metadata: dict | None,
) -> None:
    """Background task: ingest a playground interaction as production traffic."""
    try:
        async with AsyncSessionLocal() as db:
            service = IngestionService(db)
            item = ProductionLogIngest(
                source=f"playground-{system_type}",
                query=query,
                answer=answer,
                contexts=contexts if contexts else None,
                tool_calls=tool_calls_data if tool_calls_data else None,
                latency_ms=latency_ms,
                metadata=metadata,
                tags=["playground", system_type],
            )
            await service.ingest([item])
            await db.commit()
    except Exception as exc:
        logger.warning("Playground ingestion failed (non-fatal): %s", exc)


@router.post("/interact", response_model=PlaygroundResponse)
async def interact(req: PlaygroundRequest, background_tasks: BackgroundTasks):
    if req.system_type not in SYSTEM_CONFIGS:
        raise HTTPException(400, f"Unknown system type: {req.system_type}")

    try:
        adapter, session_id = _get_adapter(req.system_type, req.session_id)
        loop = asyncio.get_event_loop()

        start = time.time()
        output = await loop.run_in_executor(None, lambda: adapter.run(req.query, {}))
        latency_ms = int((time.time() - start) * 1000)

        # Ingest into production traffic in the background (non-blocking)
        tool_calls_data = [
            {"tool": tc.tool, "args": tc.args, "result": tc.result}
            for tc in output.tool_calls
        ] if output.tool_calls else None

        background_tasks.add_task(
            _ingest_playground_interaction,
            system_type=req.system_type,
            query=req.query,
            answer=output.answer,
            contexts=output.retrieved_contexts,
            tool_calls_data=tool_calls_data,
            latency_ms=latency_ms,
            metadata=output.metadata,
        )

        return PlaygroundResponse(
            answer=output.answer,
            retrieved_contexts=output.retrieved_contexts,
            tool_calls=[
                ToolCallResponse(tool=tc.tool, args=tc.args, result=tc.result)
                for tc in output.tool_calls
            ],
            turn_history=output.turn_history,
            metadata=output.metadata,
            session_id=session_id,
        )
    except Exception as exc:
        raise HTTPException(500, f"Adapter error: {type(exc).__name__}: {exc}")


@router.post("/reset-session")
async def reset_session(session_id: str):
    with _chatbot_lock:
        if session_id in _chatbot_sessions:
            adapter, _ = _chatbot_sessions.pop(session_id)
            try:
                adapter.teardown()
            except Exception:
                pass
            return {"message": "Session reset", "session_id": session_id}
    return {"message": "Session not found", "session_id": session_id}


# ── RAG Document Upload ──────────────────────────────────────────────

@router.post("/rag/documents", response_model=DocumentUploadResponse)
async def upload_documents(req: DocumentUploadRequest):
    """Add user documents to the RAG adapter's search corpus."""
    try:
        adapter, _ = _get_adapter("rag")
        loop = asyncio.get_event_loop()
        added = await loop.run_in_executor(None, lambda: adapter.add_documents(req.texts))
        total = len(adapter.get_user_documents())
        return DocumentUploadResponse(added=added, total=total)
    except Exception as exc:
        raise HTTPException(500, f"Upload error: {type(exc).__name__}: {exc}")


@router.get("/rag/documents", response_model=DocumentListResponse)
async def list_documents():
    """List all user-uploaded documents in the RAG adapter."""
    try:
        adapter, _ = _get_adapter("rag")
        docs = adapter.get_user_documents()
        return DocumentListResponse(documents=docs, count=len(docs))
    except Exception as exc:
        raise HTTPException(500, f"Error: {type(exc).__name__}: {exc}")


@router.delete("/rag/documents")
async def clear_documents():
    """Remove all user-uploaded documents from the RAG adapter."""
    try:
        adapter, _ = _get_adapter("rag")
        removed = adapter.clear_user_documents()
        return {"removed": removed, "message": f"Cleared {removed} document(s)"}
    except Exception as exc:
        raise HTTPException(500, f"Error: {type(exc).__name__}: {exc}")


def _extract_text_from_pdf(content: bytes) -> str:
    """Extract text from a PDF file using pypdf."""
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    return "\n\n".join(pages)


@router.post("/rag/upload-files", response_model=DocumentUploadResponse)
async def upload_files(files: list[UploadFile] = File(...)):
    """Upload files (PDF, TXT, MD, etc.) to the RAG adapter's corpus.

    PDFs are parsed server-side; text files are read directly.
    """
    texts: list[str] = []
    errors: list[str] = []

    for f in files:
        try:
            content = await f.read()
            name = f.filename or "unknown"
            lower = name.lower()

            if lower.endswith(".pdf"):
                text = _extract_text_from_pdf(content)
            else:
                # Try reading as UTF-8 text
                text = content.decode("utf-8", errors="ignore")

            text = text.strip()
            if text:
                texts.append(text)
            else:
                errors.append(f"{name}: no text content extracted")
        except Exception as exc:
            errors.append(f"{f.filename}: {type(exc).__name__}: {exc}")

    if not texts:
        detail = "No text could be extracted"
        if errors:
            detail += f". Errors: {'; '.join(errors)}"
        raise HTTPException(400, detail)

    try:
        adapter, _ = _get_adapter("rag")
        loop = asyncio.get_event_loop()
        added = await loop.run_in_executor(None, lambda: adapter.add_documents(texts))
        total = len(adapter.get_user_documents())
        return DocumentUploadResponse(added=added, total=total)
    except Exception as exc:
        raise HTTPException(500, f"Upload error: {type(exc).__name__}: {exc}")
