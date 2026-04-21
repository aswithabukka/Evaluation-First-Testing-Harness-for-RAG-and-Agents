"""
Pairwise preference evaluator.

Used for run-vs-run and model-vs-model comparison. Lower-variance than
absolute LLM-judge scoring because the judge only has to choose A or B
instead of pinning a number in [0, 1].

Position bias is a known issue — judges systematically prefer whichever
answer appears first. We mitigate with a position swap: every pair is
judged twice, once as (A, B) and once as (B, A), and the final preference
is the average. If swapping the order flips the judge's preference, that's a
tie.

Output format for each case in ``scores``:
    "pairwise_preference_a": 1.0  # A strictly preferred (confirmed under swap)
    "pairwise_preference_a": 0.5  # tie (judge flipped under swap)
    "pairwise_preference_a": 0.0  # B strictly preferred

Expected test_case keys: ``question``, ``answer_a``, ``answer_b``.
Optional: ``ground_truth``, ``contexts``.
"""
from __future__ import annotations

import time

from runner.evaluators._llm import LLMClient, get_default_client
from runner.evaluators.base_evaluator import BaseEvaluator, EvalError, MetricScores


_SYSTEM = """You are comparing two AI responses, A and B, for the same question.

Rules:
1. Pick the better response on correctness first, then helpfulness. Do not
   reward verbosity.
2. If an expected answer is supplied, prefer the response closer to it.
3. If they are effectively equivalent, return "tie".

Return ONLY JSON: {"winner": "A"|"B"|"tie", "reasoning": "<one sentence>"}"""


class PairwiseEvaluator(BaseEvaluator):
    name = "pairwise"
    version = "1"

    def __init__(
        self,
        *,
        model: str = "gpt-4o",
        openai_api_key: str | None = None,
        swap_for_bias: bool = True,
        client: LLMClient | None = None,
    ):
        self._model = model
        self._swap = swap_for_bias
        self._client = client or get_default_client(openai_api_key)

    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        return [self._score_pair(tc) for tc in test_cases]

    def _score_pair(self, tc: dict) -> MetricScores:
        start = time.time()
        a = tc.get("answer_a", "")
        b = tc.get("answer_b", "")

        if not a or not b:
            return MetricScores(
                scores={"pairwise_preference_a": None},
                error=EvalError(type="missing_input", message="answer_a or answer_b missing", retryable=False),
                version=self.version,
            )

        w1, r1, cost1 = self._judge(tc, a, b)
        if w1 is None:
            return MetricScores(
                scores={"pairwise_preference_a": None},
                error=EvalError(type="parse_error", message="judge did not return A/B/tie", retryable=False),
                cost_usd=cost1,
                latency_ms=(time.time() - start) * 1000.0,
                version=self.version,
            )

        if not self._swap:
            score = {"A": 1.0, "B": 0.0, "tie": 0.5}[w1]
            return MetricScores(
                scores={"pairwise_preference_a": score},
                cost_usd=cost1,
                latency_ms=(time.time() - start) * 1000.0,
                version=self.version,
                metadata={"winners": [w1], "reasonings": [r1], "swap": False},
            )

        # Position-swapped call.
        w2, r2, cost2 = self._judge(tc, b, a)
        total_cost = cost1 + cost2

        if w2 is None:
            score = {"A": 1.0, "B": 0.0, "tie": 0.5}[w1]
            return MetricScores(
                scores={"pairwise_preference_a": score},
                cost_usd=total_cost,
                latency_ms=(time.time() - start) * 1000.0,
                version=self.version,
                metadata={"winners": [w1, None], "swap": True, "swap_failed": True},
            )

        # Convert both judgements to "A strictly wins?" booleans.
        # Under the second call, A and B were swapped — so "A" there means our B.
        a_first = {"A": 1.0, "B": 0.0, "tie": 0.5}[w1]
        a_second = {"A": 0.0, "B": 1.0, "tie": 0.5}[w2]
        final = (a_first + a_second) / 2.0

        return MetricScores(
            scores={"pairwise_preference_a": final},
            cost_usd=total_cost,
            latency_ms=(time.time() - start) * 1000.0,
            version=self.version,
            metadata={
                "winners": [w1, w2],
                "reasonings": [r1, r2],
                "swap": True,
                "a_first": a_first,
                "a_second": a_second,
                "position_bias_detected": abs(a_first - a_second) > 0.5,
            },
        )

    def _judge(self, tc: dict, a: str, b: str) -> tuple[str | None, str, float]:
        parts = [f"Question:\n{tc.get('question', tc.get('query', ''))}"]
        if tc.get("contexts"):
            parts.append(f"Retrieved Context:\n{chr(10).join(tc['contexts'][:3])}")
        if tc.get("ground_truth"):
            parts.append(f"Expected Answer:\n{tc['ground_truth']}")
        parts.append(f"Response A:\n{a}")
        parts.append(f"Response B:\n{b}")
        user = "\n\n".join(parts)

        r = self._client.chat_json(
            system=_SYSTEM,
            user=user,
            model=self._model,
            temperature=0.0,
            seed=0,
        )
        if r.error or not isinstance(r.parsed, dict):
            return None, "", r.cost_usd
        winner = str(r.parsed.get("winner", "")).strip()
        if winner not in ("A", "B", "tie"):
            return None, str(r.parsed.get("reasoning", "")), r.cost_usd
        return winner, str(r.parsed.get("reasoning", "")), r.cost_usd
