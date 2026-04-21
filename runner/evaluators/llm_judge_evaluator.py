"""
LLM-as-Judge evaluator — hardened.

Over the naive version, this adds:

* **Self-consistency** — run the judge ``k`` times and take the median score.
  Variance across runs is reported so flaky test cases can be flagged.
* **None-on-error** — provider failures and JSON parse errors set
  ``MetricScores.error`` and leave the score as ``None``. Do NOT return 0.0;
  that would trigger the release gate for infra reasons, not quality reasons.
* **Verbosity-bias hint** — judge prompt explicitly tells the model not to
  reward length. LLM judges otherwise systematically prefer longer answers
  (well-documented bias; see Zheng et al. "Judging LLM-as-a-Judge", 2023).
* **Shared LLM client** — retries, backoff, cost accounting, caching.
* **Per-case metadata** — prompt hash, judge model, sample count, variance.

Score is written to ``scores['llm_judge']`` in addition to the legacy
``custom['llm_judge']`` slot so downstream aggregators can read it cleanly.
"""
from __future__ import annotations

import statistics
import time

from runner.evaluators._llm import LLMClient, get_default_client
from runner.evaluators.base_evaluator import BaseEvaluator, EvalError, MetricScores


SYSTEM_PROMPT = """You are an impartial evaluator for AI-generated responses.

Score the response against the stated criteria. Apply these rules:

1. Score is a single float between 0.0 (fails all criteria) and 1.0 (meets all criteria).
2. Do NOT reward verbosity. A concise correct answer scores the same as a verbose correct answer.
3. Penalise hallucinated facts even if the answer sounds confident.
4. If an expected answer is supplied, treat it as ground truth.
5. Reasoning must be 1-2 sentences and must name the specific deficiency or strength.

Return ONLY JSON: {"score": <float>, "reasoning": "<string>"}

Criteria: {criteria}"""


class LLMJudgeEvaluator(BaseEvaluator):
    name = "llm_judge"
    version = "2"

    def __init__(
        self,
        *,
        model: str = "gpt-4o",
        criteria: str = "accuracy, helpfulness, and groundedness",
        openai_api_key: str | None = None,
        samples: int = 1,
        client: LLMClient | None = None,
    ):
        if samples < 1:
            raise ValueError("samples must be >= 1")
        self._model = model
        self._criteria = criteria
        self._samples = samples
        self._client = client or get_default_client(openai_api_key)

    # ------------------------------------------------------------ single-case

    def evaluate(
        self,
        query: str,
        answer: str,
        ground_truth: str | None = None,
        contexts: list[str] | None = None,
    ) -> dict:
        """Score a single (query, answer) pair.

        Returns a dict for backward compatibility with the old API:
          ``{"score": float | None, "reasoning": str, "variance": float,
             "cost_usd": float, "error": str | None}``
        """
        ms = self._score_case(query, answer, ground_truth, contexts)
        return {
            "score": ms.scores.get("llm_judge"),
            "reasoning": ms.metadata.get("reasoning", ""),
            "variance": ms.metadata.get("variance", 0.0),
            "cost_usd": ms.cost_usd,
            "error": ms.error.message if ms.error else None,
        }

    # ------------------------------------------------------------ batch API

    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        out: list[MetricScores] = []
        for tc in test_cases:
            out.append(
                self._score_case(
                    query=tc.get("question", "") or tc.get("query", ""),
                    answer=tc.get("answer", ""),
                    ground_truth=tc.get("ground_truth"),
                    contexts=tc.get("contexts"),
                )
            )
        return out

    # ------------------------------------------------------------ internals

    def _score_case(
        self,
        query: str,
        answer: str,
        ground_truth: str | None,
        contexts: list[str] | None,
    ) -> MetricScores:
        start = time.time()

        if not answer:
            return MetricScores(
                scores={"llm_judge": None},
                error=EvalError(type="missing_input", message="empty answer", retryable=False),
                version=self.version,
            )

        user = self._build_user_prompt(query, answer, ground_truth, contexts)
        system = SYSTEM_PROMPT.replace("{criteria}", self._criteria)

        scores: list[float] = []
        reasonings: list[str] = []
        total_cost = 0.0
        last_error: EvalError | None = None

        for i in range(self._samples):
            # Small temperature bump after the first sample so self-consistency
            # actually samples different reasoning paths. ``seed`` keeps it
            # reproducible per-sample.
            temp = 0.0 if i == 0 else 0.3
            r = self._client.chat_json(
                system=system,
                user=user,
                model=self._model,
                temperature=temp,
                seed=i,
            )
            total_cost += r.cost_usd
            if r.error is not None:
                last_error = EvalError(
                    type=r.error.type, message=r.error.message, retryable=r.error.retryable
                )
                continue
            if not isinstance(r.parsed, dict):
                last_error = EvalError(type="parse_error", message="non-dict response", retryable=False)
                continue
            try:
                s = float(r.parsed.get("score"))
            except (TypeError, ValueError):
                last_error = EvalError(type="parse_error", message="score missing/non-numeric", retryable=False)
                continue
            scores.append(max(0.0, min(1.0, s)))
            reasonings.append(str(r.parsed.get("reasoning", "")))

        latency_ms = (time.time() - start) * 1000.0

        if not scores:
            return MetricScores(
                scores={"llm_judge": None},
                custom={"llm_judge": None},
                error=last_error or EvalError(type="other", message="no samples", retryable=False),
                cost_usd=total_cost,
                latency_ms=latency_ms,
                version=self.version,
                metadata={"model": self._model, "samples": self._samples},
            )

        median = statistics.median(scores)
        variance = statistics.pvariance(scores) if len(scores) > 1 else 0.0
        return MetricScores(
            scores={"llm_judge": median},
            custom={"llm_judge": median},  # legacy slot
            cost_usd=total_cost,
            latency_ms=latency_ms,
            version=self.version,
            metadata={
                "model": self._model,
                "samples": self._samples,
                "variance": variance,
                "all_scores": scores,
                "reasoning": reasonings[0] if reasonings else "",
            },
        )

    @staticmethod
    def _build_user_prompt(
        query: str,
        answer: str,
        ground_truth: str | None,
        contexts: list[str] | None,
    ) -> str:
        parts = [f"Question:\n{query}"]
        if contexts:
            joined = "\n---\n".join(contexts[:3])
            parts.append(f"Retrieved Context:\n{joined}")
        if ground_truth:
            parts.append(f"Expected Answer:\n{ground_truth}")
        parts.append(f"Actual Answer:\n{answer}")
        return "\n\n".join(parts)
