"""
G-Eval evaluator.

Implements the G-Eval pattern from Liu et al., "G-Eval: NLG Evaluation using
GPT-4 with Better Human Alignment" (EMNLP 2023):

1. Given an ``aspect`` (e.g. "coherence") and a short description, the judge
   first emits an *evaluation rubric* — the concrete steps it will use to
   score.
2. Given a test case, the judge is forced to run that rubric step-by-step
   (chain-of-thought) and emit an integer 1-5 score.
3. The integer is normalised to 0-1.

The cached rubric is reused across all cases in a run so the judge is
scoring against a consistent rubric rather than a fresh one per call.
Score is written to ``scores["g_eval:<aspect>"]``.
"""
from __future__ import annotations

import time

from runner.evaluators._llm import LLMClient, get_default_client
from runner.evaluators.base_evaluator import BaseEvaluator, EvalError, MetricScores


_RUBRIC_SYSTEM = """You are preparing an evaluation rubric.

Given a single quality aspect and a short description, return 3-5 concrete
evaluation steps a human annotator would follow to score a response from 1
(worst) to 5 (best). Steps must be specific, testable, and ordered.

Return ONLY JSON: {"steps": ["step 1", "step 2", ...]}"""


_SCORE_SYSTEM = """You are scoring an AI-generated response on a single aspect.

Rules:
1. Follow the evaluation steps in order. For each step, think briefly about
   how the response performs.
2. After running ALL steps, return a single integer from 1 (worst) to 5 (best).
3. Do not reward verbosity. A concise correct response scores the same as a
   verbose correct one.

Return ONLY JSON: {"step_notes": ["...", "..."], "score": <int 1-5>}"""


class GEvalEvaluator(BaseEvaluator):
    name = "g_eval"
    version = "1"

    def __init__(
        self,
        *,
        aspect: str,
        description: str,
        model: str = "gpt-4o",
        samples: int = 1,
        openai_api_key: str | None = None,
        client: LLMClient | None = None,
    ):
        self._aspect = aspect
        self._description = description
        self._model = model
        self._samples = max(1, samples)
        self._client = client or get_default_client(openai_api_key)
        self._cached_rubric: list[str] | None = None

    # ------------------------------------------------------------------ rubric

    def _get_rubric(self) -> tuple[list[str] | None, EvalError | None]:
        if self._cached_rubric is not None:
            return self._cached_rubric, None

        r = self._client.chat_json(
            system=_RUBRIC_SYSTEM,
            user=f"Aspect: {self._aspect}\nDescription: {self._description}",
            model=self._model,
            temperature=0.0,
            seed=0,
        )
        if r.error or not isinstance(r.parsed, dict) or not r.parsed.get("steps"):
            return None, EvalError(
                type=r.error.type if r.error else "parse_error",
                message=r.error.message if r.error else "no steps returned",
                retryable=bool(r.error and r.error.retryable),
            )
        self._cached_rubric = [str(s) for s in r.parsed["steps"]]
        return self._cached_rubric, None

    # ------------------------------------------------------------------ public

    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        rubric, err = self._get_rubric()
        metric_key = f"g_eval:{self._aspect}"

        if err is not None:
            return [
                MetricScores(scores={metric_key: None}, error=err, version=self.version)
                for _ in test_cases
            ]

        out: list[MetricScores] = []
        for tc in test_cases:
            out.append(self._score_case(tc, rubric, metric_key))
        return out

    # ------------------------------------------------------------------ internals

    def _score_case(self, tc: dict, rubric: list[str], metric_key: str) -> MetricScores:
        start = time.time()
        answer = tc.get("answer", "")
        if not answer:
            return MetricScores(
                scores={metric_key: None},
                error=EvalError(type="missing_input", message="empty answer", retryable=False),
                version=self.version,
            )

        user_prompt = self._build_user_prompt(tc, rubric)
        raw_scores: list[float] = []
        total_cost = 0.0
        last_error: EvalError | None = None

        for i in range(self._samples):
            r = self._client.chat_json(
                system=_SCORE_SYSTEM,
                user=user_prompt,
                model=self._model,
                temperature=0.0 if i == 0 else 0.3,
                seed=i,
            )
            total_cost += r.cost_usd
            if r.error or not isinstance(r.parsed, dict):
                last_error = EvalError(
                    type=(r.error.type if r.error else "parse_error"),
                    message=(r.error.message if r.error else "non-dict response"),
                    retryable=bool(r.error and r.error.retryable),
                )
                continue
            try:
                s = int(r.parsed.get("score"))
            except (TypeError, ValueError):
                last_error = EvalError(type="parse_error", message="score missing/non-int", retryable=False)
                continue
            s = max(1, min(5, s))
            raw_scores.append((s - 1) / 4.0)

        latency_ms = (time.time() - start) * 1000.0
        if not raw_scores:
            return MetricScores(
                scores={metric_key: None},
                error=last_error,
                cost_usd=total_cost,
                latency_ms=latency_ms,
                version=self.version,
            )

        import statistics
        median = statistics.median(raw_scores)
        variance = statistics.pvariance(raw_scores) if len(raw_scores) > 1 else 0.0
        return MetricScores(
            scores={metric_key: median},
            cost_usd=total_cost,
            latency_ms=latency_ms,
            version=self.version,
            metadata={
                "aspect": self._aspect,
                "rubric_steps": len(rubric),
                "samples": self._samples,
                "variance": variance,
                "all_scores": raw_scores,
            },
        )

    def _build_user_prompt(self, tc: dict, rubric: list[str]) -> str:
        parts = [
            f"Aspect: {self._aspect}",
            f"Description: {self._description}",
            "Evaluation Steps:",
            "\n".join(f"{i+1}. {s}" for i, s in enumerate(rubric)),
            f"\nQuestion:\n{tc.get('question', tc.get('query', ''))}",
        ]
        if tc.get("contexts"):
            parts.append(f"Retrieved Context:\n{chr(10).join(tc['contexts'][:3])}")
        if tc.get("ground_truth"):
            parts.append(f"Expected Answer:\n{tc['ground_truth']}")
        parts.append(f"Actual Answer:\n{tc.get('answer', '')}")
        return "\n\n".join(parts)
