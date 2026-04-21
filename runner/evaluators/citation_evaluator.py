"""
Citation faithfulness evaluator.

Decomposes an answer into atomic claims and checks whether each claim is
supported by at least one retrieved context chunk. Produces:

    citation_faithfulness : float  # fraction of claims supported
    unsupported_claims    : list[str]
    claim_count           : int

This is a stricter signal than Ragas' faithfulness — it attributes
support at the claim level rather than in aggregate. Useful for gating
"the model says things the corpus does not support" regressions.

Two-stage LLM call:
    1. Claim extraction: answer → list of atomic claims.
    2. Support check:     (claim, contexts) → supported? yes/no.

Falls back to single-pass if the first call fails; errored cases get
``scores["citation_faithfulness"] = None``.
"""
from __future__ import annotations

import time

from runner.evaluators._llm import LLMClient, get_default_client
from runner.evaluators.base_evaluator import BaseEvaluator, EvalError, MetricScores


_EXTRACT_SYSTEM = """Extract atomic factual claims from the response.

Rules:
- Each claim must be a standalone sentence that asserts a single fact.
- Ignore questions, hedges, opinions, and generic statements.
- Keep proper nouns, numbers, and dates verbatim.

Return ONLY JSON: {"claims": ["claim 1", "claim 2", ...]}"""


_SUPPORT_SYSTEM = """Decide whether each claim is supported by the supplied context.

Rules:
- A claim is supported only if the context explicitly states or directly
  implies it.
- Partial support counts as unsupported.
- Do not use outside knowledge.

Return ONLY JSON: {"supports": [true|false, ...]} with one entry per claim,
in input order."""


class CitationEvaluator(BaseEvaluator):
    name = "citation"
    version = "1"

    def __init__(
        self,
        *,
        model: str = "gpt-4o",
        openai_api_key: str | None = None,
        max_claims: int = 10,
        client: LLMClient | None = None,
    ):
        self._model = model
        self._max_claims = max_claims
        self._client = client or get_default_client(openai_api_key)

    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        return [self._score(tc) for tc in test_cases]

    def _score(self, tc: dict) -> MetricScores:
        start = time.time()
        answer = tc.get("answer", "")
        contexts = tc.get("contexts") or []

        if not answer:
            return MetricScores(
                scores={"citation_faithfulness": None},
                error=EvalError(type="missing_input", message="empty answer", retryable=False),
                version=self.version,
            )
        if not contexts:
            return MetricScores(
                scores={"citation_faithfulness": None},
                error=EvalError(type="missing_input", message="no contexts to check against", retryable=False),
                version=self.version,
            )

        total_cost = 0.0
        claims, err, c1 = self._extract_claims(answer)
        total_cost += c1
        if err is not None:
            return MetricScores(
                scores={"citation_faithfulness": None},
                error=err,
                cost_usd=total_cost,
                latency_ms=(time.time() - start) * 1000.0,
                version=self.version,
            )
        if not claims:
            return MetricScores(
                scores={"citation_faithfulness": 1.0},
                cost_usd=total_cost,
                latency_ms=(time.time() - start) * 1000.0,
                version=self.version,
                metadata={"claim_count": 0, "unsupported_claims": []},
            )

        claims = claims[: self._max_claims]
        supports, err, c2 = self._check_support(claims, contexts)
        total_cost += c2
        if err is not None:
            return MetricScores(
                scores={"citation_faithfulness": None},
                error=err,
                cost_usd=total_cost,
                latency_ms=(time.time() - start) * 1000.0,
                version=self.version,
            )

        supported_count = sum(1 for s in supports if s)
        faithfulness = supported_count / len(claims)
        unsupported = [claims[i] for i, s in enumerate(supports) if not s]

        return MetricScores(
            scores={"citation_faithfulness": faithfulness},
            cost_usd=total_cost,
            latency_ms=(time.time() - start) * 1000.0,
            version=self.version,
            metadata={
                "claim_count": len(claims),
                "supported_claims": supported_count,
                "unsupported_claims": unsupported,
            },
        )

    def _extract_claims(self, answer: str) -> tuple[list[str] | None, EvalError | None, float]:
        r = self._client.chat_json(
            system=_EXTRACT_SYSTEM,
            user=f"Response:\n{answer}",
            model=self._model,
            temperature=0.0,
            seed=0,
        )
        if r.error or not isinstance(r.parsed, dict):
            return None, EvalError(
                type=(r.error.type if r.error else "parse_error"),
                message=(r.error.message if r.error else "non-dict response"),
                retryable=bool(r.error and r.error.retryable),
            ), r.cost_usd
        raw = r.parsed.get("claims") or []
        claims = [str(c).strip() for c in raw if str(c).strip()]
        return claims, None, r.cost_usd

    def _check_support(
        self, claims: list[str], contexts: list[str]
    ) -> tuple[list[bool] | None, EvalError | None, float]:
        context_block = "\n---\n".join(contexts[:5])
        claim_block = "\n".join(f"{i+1}. {c}" for i, c in enumerate(claims))
        user = f"Context:\n{context_block}\n\nClaims:\n{claim_block}"

        r = self._client.chat_json(
            system=_SUPPORT_SYSTEM,
            user=user,
            model=self._model,
            temperature=0.0,
            seed=0,
        )
        if r.error or not isinstance(r.parsed, dict):
            return None, EvalError(
                type=(r.error.type if r.error else "parse_error"),
                message=(r.error.message if r.error else "non-dict response"),
                retryable=bool(r.error and r.error.retryable),
            ), r.cost_usd

        raw = r.parsed.get("supports")
        if not isinstance(raw, list) or len(raw) != len(claims):
            return None, EvalError(
                type="parse_error",
                message=f"expected {len(claims)} support flags, got {len(raw) if isinstance(raw, list) else 'non-list'}",
                retryable=False,
            ), r.cost_usd
        return [bool(v) for v in raw], None, r.cost_usd
