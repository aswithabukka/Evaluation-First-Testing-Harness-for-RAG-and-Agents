"""
Demo Chatbot Adapter — a self-contained multi-turn customer-support chatbot.

Uses OpenAI GPT-4o-mini with a system prompt that plays a "TechStore" support agent.
Maintains conversation history across turns within a single test case.
Returns PipelineOutput with turn_history for conversation evaluators.
"""
import os
from openai import OpenAI

from runner.adapters.base import PipelineOutput, RAGAdapter, ToolCall

SYSTEM_PROMPT = """\
You are Alex, a friendly and knowledgeable customer support agent for TechStore, \
an online electronics retailer. Follow these rules strictly:

1. Always greet the customer warmly on the first message.
2. Be helpful, concise, and professional.
3. For product questions, reference our catalog: laptops ($499-$1999), \
   headphones ($29-$349), smartwatches ($199-$499), tablets ($299-$899), \
   phone chargers ($15-$45).
4. For order issues, ask for the order number (format: TS-XXXXX).
5. For returns, explain our 30-day return policy — items must be unused and in original packaging.
6. Never reveal internal pricing or discount codes.
7. If you don't know something, say "Let me connect you with a specialist" \
   rather than making things up.
8. Always end with "Is there anything else I can help you with?"
"""

# Knowledge base for grounding responses
KNOWLEDGE_BASE = [
    "TechStore offers free shipping on orders over $50. Standard shipping takes 3-5 business days.",
    "Our return policy allows returns within 30 days of purchase. Items must be unused and in original packaging. Refunds are processed within 5-7 business days.",
    "TechStore's laptop lineup: Budget Pro ($499), WorkStation X ($899), UltraBook Air ($1299), Gaming Beast ($1599), Creator Studio ($1999).",
    "Headphones catalog: BudgetBuds ($29), DailyDriver ($79), NoiseMaster Pro ($199), StudioElite ($349).",
    "Smartwatch models: FitTrack Basic ($199), FitTrack Pro ($299), LuxWatch ($499).",
    "Tablet lineup: TabLite ($299), TabPro ($599), TabMax ($899).",
    "Phone chargers: BasicCharge ($15), FastCharge 20W ($25), SuperCharge 65W ($35), MegaCharge 100W ($45).",
    "TechStore warranty: All products come with a 1-year manufacturer warranty. Extended 2-year warranty available for $49.",
    "Order tracking: Customers can track orders at techstore.com/track or by contacting support with order number (format: TS-XXXXX).",
    "Payment methods accepted: Visa, Mastercard, Amex, PayPal, Apple Pay, Google Pay. Financing available on orders over $500.",
]


class DemoChatbotAdapter(RAGAdapter):
    """Self-contained chatbot that uses OpenAI for conversation."""

    def __init__(self, model: str = "gpt-4o-mini", **kwargs):
        self.model = model
        self._client: OpenAI | None = None
        self._history: list[dict] = []

    def setup(self) -> None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        self._client = OpenAI(api_key=api_key)
        self._history = []

    def run(self, query: str, context: dict | None = None) -> PipelineOutput:
        context = context or {}

        # Check if this is a new conversation (reset history)
        if context.get("new_conversation", False) or not self._history:
            self._history = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add user message
        self._history.append({"role": "user", "content": query})

        # Find relevant knowledge chunks
        relevant_knowledge = self._retrieve_knowledge(query)

        # Inject knowledge as a system hint (not visible to user)
        messages = list(self._history)
        if relevant_knowledge:
            knowledge_text = "\n".join(f"- {k}" for k in relevant_knowledge)
            messages.insert(1, {
                "role": "system",
                "content": f"Relevant knowledge for answering:\n{knowledge_text}",
            })

        # Call OpenAI
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )

        answer = response.choices[0].message.content.strip()

        # Add assistant response to history
        self._history.append({"role": "assistant", "content": answer})

        return PipelineOutput(
            answer=answer,
            retrieved_contexts=relevant_knowledge,
            tool_calls=[],
            turn_history=[
                {"role": m["role"], "content": m["content"]}
                for m in self._history
                if m["role"] != "system"
            ],
            metadata={
                "model": self.model,
                "turn_count": len([m for m in self._history if m["role"] == "user"]),
                "knowledge_chunks_used": len(relevant_knowledge),
            },
        )

    def teardown(self) -> None:
        self._history = []
        self._client = None

    def _retrieve_knowledge(self, query: str) -> list[str]:
        """Simple keyword-based retrieval from the knowledge base."""
        query_lower = query.lower()
        scored = []
        for chunk in KNOWLEDGE_BASE:
            chunk_lower = chunk.lower()
            # Count keyword overlaps
            query_words = set(query_lower.split())
            chunk_words = set(chunk_lower.split())
            overlap = len(query_words & chunk_words)
            if overlap >= 2:
                scored.append((overlap, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:3]]
