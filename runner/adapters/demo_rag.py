"""
DemoRAGAdapter — a self-contained RAG pipeline for demo and testing.

Architecture:
  - Knowledge base: hardcoded text corpus (~30 chunks across common topics)
  - Embeddings:     OpenAI text-embedding-3-small  (once at setup)
  - Retrieval:      Cosine similarity via numpy     (top-k chunks)
  - Generation:     GPT-4o-mini with retrieved context as system prompt

No external vector store required — everything is in-memory.
"""
from __future__ import annotations

import os
from typing import Optional

from runner.adapters.base import PipelineOutput, RAGAdapter

# ---------------------------------------------------------------------------
# Knowledge base corpus
# Each entry is an independent retrievable chunk.
# Topics match the demo test cases: geography, science, medical, tech,
# literature, physics, AI, and an ethics/refusal policy notice.
# ---------------------------------------------------------------------------
CORPUS: list[str] = [
    # ── Geography ──────────────────────────────────────────────────────────
    "Paris is the capital and largest city of France. It sits on the Seine River "
    "in northern France and has been the country's political center since the 12th century.",

    "France is a republic in Western Europe. Its capital is Paris, the seat of government "
    "and home to the Élysée Palace (presidential residence) and the National Assembly.",

    "Other major French cities include Lyon, Marseille, and Toulouse, but Paris remains "
    "the undisputed capital and accounts for roughly one-fifth of France's population.",

    # ── Photosynthesis ─────────────────────────────────────────────────────
    "Photosynthesis is the biological process by which green plants, algae, and some "
    "bacteria convert light energy into chemical energy stored as glucose (sugar). "
    "The overall reaction is: 6CO₂ + 6H₂O + light → C₆H₁₂O₆ + 6O₂.",

    "Photosynthesis occurs in two stages: the light-dependent reactions (in the thylakoid "
    "membranes) capture solar energy and produce ATP and NADPH; the Calvin cycle (in the "
    "stroma) uses that energy to fix CO₂ into glucose.",

    "Chlorophyll, the green pigment in plant chloroplasts, absorbs red and blue light most "
    "efficiently and drives the light-dependent reactions of photosynthesis.",

    # ── Diabetes symptoms ──────────────────────────────────────────────────
    "Common symptoms of type 2 diabetes include frequent urination (polyuria), excessive "
    "thirst (polydipsia), unexplained weight loss, fatigue, and blurred vision.",

    "Additional signs of diabetes are slow-healing wounds or sores, frequent infections, "
    "numbness or tingling in the hands or feet (peripheral neuropathy), and patches of "
    "darker skin (acanthosis nigricans) in body creases.",

    "Type 1 diabetes shares many symptoms with type 2 but often presents more suddenly, "
    "including nausea, vomiting, and abdominal pain. Both types require medical diagnosis — "
    "self-diagnosis is not reliable.",

    # ── RAM vs ROM ─────────────────────────────────────────────────────────
    "RAM (Random Access Memory) is volatile computer memory used to temporarily hold data "
    "and program instructions that the CPU is actively using. Its contents are lost when "
    "the computer is powered off.",

    "ROM (Read-Only Memory) is non-volatile memory that retains its data without power. "
    "It typically stores firmware — low-level software like the BIOS or bootloader — "
    "that runs when a device first powers on.",

    "The key difference: RAM is fast, temporary, and read/write; ROM is permanent, "
    "slower to write, and used for firmware. Modern computers use gigabytes of RAM "
    "but only a few megabytes of ROM.",

    # ── Speed of light ─────────────────────────────────────────────────────
    "The speed of light in a vacuum, denoted by the symbol c, is exactly "
    "299,792,458 metres per second (approximately 3 × 10⁸ m/s or 186,282 miles per second). "
    "It is a fundamental constant of physics.",

    "According to Einstein's special relativity, no object with mass can reach or exceed "
    "the speed of light. As an object's velocity approaches c, its relativistic mass "
    "increases without bound and the energy required to accelerate it becomes infinite.",

    "Light takes approximately 8 minutes and 20 seconds to travel from the Sun to Earth, "
    "and about 1.3 seconds to travel from the Moon to Earth.",

    # ── Pride and Prejudice ────────────────────────────────────────────────
    "Pride and Prejudice is a novel by the English author Jane Austen, first published "
    "in January 1813. It is a romantic story set in rural England at the turn of the "
    "19th century.",

    "The novel follows Elizabeth Bennet, the second of five sisters, as she navigates "
    "issues of marriage, morality, and social class. Her evolving relationship with the "
    "proud and wealthy Mr. Darcy is the central plot.",

    "Jane Austen began writing Pride and Prejudice in 1796 under the title 'First Impressions'. "
    "It was revised and sold to publisher Thomas Egerton for £110 in 1812, then published in 1813.",

    # ── Machine learning ───────────────────────────────────────────────────
    "Machine learning (ML) is a subfield of artificial intelligence in which algorithms "
    "learn patterns from data to make predictions or decisions without being explicitly "
    "programmed for each specific task.",

    "The three main paradigms of machine learning are: supervised learning (learning from "
    "labelled examples), unsupervised learning (finding structure in unlabelled data), "
    "and reinforcement learning (learning via rewards and penalties).",

    "Common machine learning techniques include linear regression, decision trees, random "
    "forests, support vector machines, and neural networks. Deep learning refers to neural "
    "networks with many layers (deep architectures).",

    # ── Ethics / refusal policy ────────────────────────────────────────────
    "This AI assistant is designed to be helpful, harmless, and honest. It will not "
    "assist with hacking, unauthorized computer access, cracking passwords, or any "
    "activity that violates the law or another person's privacy.",

    "Requests to access someone else's account without permission, bypass authentication "
    "systems, or exploit security vulnerabilities are declined. For legitimate security "
    "testing, consult a certified ethical hacker or penetration testing firm.",
]


class DemoRAGAdapter(RAGAdapter):
    """
    Self-contained RAG pipeline for demo / CI evaluation.

    setup() embeds the entire corpus once (≈ 1 OpenAI API call).
    run()   embeds the query, retrieves top-k chunks, then asks GPT-4o-mini
            to answer using only those chunks.
    """

    def __init__(self, top_k: int = 3, model: str = "gpt-4o-mini"):
        self.top_k = top_k
        self.model = model
        self._corpus_embeddings: Optional[list[list[float]]] = None
        self._client = None
        self._embed_model = "text-embedding-3-small"

    # ------------------------------------------------------------------
    def setup(self) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        # Embed the entire corpus in one batched API call
        response = self._client.embeddings.create(
            model=self._embed_model,
            input=CORPUS,
        )
        self._corpus_embeddings = [item.embedding for item in response.data]

    # ------------------------------------------------------------------
    def run(self, query: str, context: dict) -> PipelineOutput:
        if self._client is None or self._corpus_embeddings is None:
            raise RuntimeError("DemoRAGAdapter.setup() must be called before run()")

        # 1. Embed the query
        q_resp = self._client.embeddings.create(
            model=self._embed_model,
            input=[query],
        )
        q_vec = q_resp.data[0].embedding

        # 2. Cosine similarity against the corpus
        import math
        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x * x for x in a))
            mag_b = math.sqrt(sum(x * x for x in b))
            return dot / (mag_a * mag_b + 1e-9)

        scores = [
            (cosine(q_vec, emb), chunk)
            for emb, chunk in zip(self._corpus_embeddings, CORPUS)
        ]
        scores.sort(key=lambda t: t[0], reverse=True)
        top_chunks = [chunk for _, chunk in scores[: self.top_k]]

        # 3. Generate answer grounded in retrieved chunks
        context_block = "\n\n".join(
            f"[Source {i + 1}] {chunk}" for i, chunk in enumerate(top_chunks)
        )
        system_prompt = (
            "You are a helpful assistant. Answer the user's question using ONLY "
            "the information in the provided sources. If the sources do not contain "
            "enough information to answer, say so clearly. Do not add facts not "
            "present in the sources."
        )
        user_message = f"Sources:\n{context_block}\n\nQuestion: {query}"

        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            max_tokens=512,
        )
        answer = completion.choices[0].message.content or ""

        return PipelineOutput(
            answer=answer,
            retrieved_contexts=top_chunks,
            metadata={
                "model": self.model,
                "top_k": self.top_k,
                "scores": [round(s, 4) for s, _ in scores[: self.top_k]],
            },
        )

    # ------------------------------------------------------------------
    def teardown(self) -> None:
        self._client = None
        self._corpus_embeddings = None
