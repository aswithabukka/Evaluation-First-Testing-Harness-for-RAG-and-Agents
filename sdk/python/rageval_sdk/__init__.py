"""
RAG Eval SDK — lightweight client for logging production AI traffic.

Usage:
    from rageval_sdk import RagEvalClient

    client = RagEvalClient(
        api_url="https://your-eval-harness.com/api/v1",
        api_key="your-api-key",
    )

    # Log a single Q&A pair
    client.log(
        source="customer-support-bot",
        query="How do I reset my password?",
        answer="Go to Settings > Security > Reset Password...",
        contexts=["doc chunk 1", "doc chunk 2"],
        latency_ms=340,
    )

    # Or use as a decorator / context manager
    with client.trace(source="my-bot") as trace:
        trace.query = user_question
        answer = my_ai_system(user_question)
        trace.answer = answer
"""
from rageval_sdk.client import RagEvalClient
from rageval_sdk.middleware import FastAPIMiddleware

__all__ = ["RagEvalClient", "FastAPIMiddleware"]
__version__ = "0.1.0"
