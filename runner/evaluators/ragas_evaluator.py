"""
Ragas-based RAG evaluator — hardened.

Changes vs. the naive version:

* Optional imports probed at class init — fail fast if Ragas is missing.
* Missing/NaN scores produce ``MetricScores(error=...)`` instead of silently
  yielding 0.0 or None. The release gate can then skip errored rows instead of
  treating them as regressions.
* Per-row error isolation: if the batch call fails, we fall back to one call
  per row so a single bad row can't take down the whole batch.
* Latency is measured and stored on each MetricScores.
* Provider routing — when ``OPENROUTER_API_KEY`` / ``LLM_PROVIDER=openrouter``
  is set, we point Ragas at OpenRouter by wrapping its internal LLM in a
  LangChain ChatOpenAI configured with a custom ``openai_api_base``.

Ragas uses its own OpenAI client internally; the wiring below swaps that
client rather than piping every call through ``_llm.LLMClient`` (Ragas'
batched API is too coupled to ``datasets`` to intercept cleanly).
"""
from __future__ import annotations

import math
import time

import os

from runner.evaluators._llm import OPENROUTER_BASE_URL, is_openrouter_model
from runner.evaluators.base_evaluator import BaseEvaluator, EvalError, MetricScores


def _build_ragas_llm():
    """Return a LangChain ChatOpenAI configured for the active provider, or
    ``None`` to let Ragas pick its own default (bare OpenAI).

    Triggers on any of:
      * ``LLM_PROVIDER=openrouter``
      * ``OPENROUTER_API_KEY`` set with no ``OPENAI_API_KEY``
      * ``LLM_DEFAULT_MODEL`` is an OpenRouter slug (``provider/model``).
    """
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    model = os.getenv("LLM_DEFAULT_MODEL", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")

    use_openrouter = (
        provider == "openrouter"
        or (openrouter_key and not openai_key)
        or (model and is_openrouter_model(model))
    )
    if not use_openrouter:
        return None

    try:
        # Ragas ships with its own LangChain wrapper; we reuse it.
        from langchain_openai import ChatOpenAI
        from ragas.llms import LangchainLLMWrapper
    except ImportError:
        return None

    default_model = model or "deepseek/deepseek-chat"
    base_url = os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL)
    chat = ChatOpenAI(
        model=default_model,
        openai_api_key=openrouter_key or openai_key,
        openai_api_base=base_url,
        temperature=0.0,
        default_headers={
            "HTTP-Referer": "https://github.com/aswithabukka/Evaluation-First-Testing-Harness-for-RAG-and-Agents",
            "X-Title": "rag-eval-harness",
        },
    )
    return LangchainLLMWrapper(chat)


class RagasEvaluator(BaseEvaluator):
    name = "ragas"
    version = "2"

    SUPPORTED_METRICS = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    ]

    def __init__(
        self,
        metrics: list[str] | None = None,
        openai_api_key: str | None = None,
    ):
        self._active = [m for m in (metrics or self.SUPPORTED_METRICS) if m in self.SUPPORTED_METRICS]
        self._openai_api_key = openai_api_key
        self._ragas_available = self._probe_ragas()

    @staticmethod
    def _probe_ragas() -> bool:
        try:
            import ragas  # noqa: F401
            import datasets  # noqa: F401
            return True
        except ImportError:
            return False

    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        if not test_cases:
            return []

        if not self._active:
            return [MetricScores(version=self.version) for _ in test_cases]

        if not self._ragas_available:
            err = EvalError(type="missing_dep", message="ragas/datasets not installed", retryable=False)
            return [MetricScores(error=err, version=self.version) for _ in test_cases]

        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        metric_obj_map = {
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_precision": context_precision,
            "context_recall": context_recall,
        }
        active_metric_objs = [metric_obj_map[m] for m in self._active]

        # Route Ragas through OpenRouter when configured. ``None`` lets Ragas
        # use its bundled default (OpenAI via OPENAI_API_KEY).
        ragas_llm = _build_ragas_llm()
        evaluate_kwargs = {"dataset": None, "metrics": active_metric_objs}
        if ragas_llm is not None:
            evaluate_kwargs["llm"] = ragas_llm

        start = time.time()
        try:
            data = {
                "question": [tc.get("question", "") for tc in test_cases],
                "answer": [tc.get("answer", "") for tc in test_cases],
                "contexts": [tc.get("contexts") or [""] for tc in test_cases],
                "ground_truth": [tc.get("ground_truth", "") for tc in test_cases],
            }
            dataset = Dataset.from_dict(data)
            evaluate_kwargs["dataset"] = dataset
            result = ragas_evaluate(**evaluate_kwargs)
            df = result.to_pandas()
            batch_latency_ms = (time.time() - start) * 1000.0
            per_row_latency = batch_latency_ms / max(len(test_cases), 1)
            return [self._row_to_score(row, per_row_latency) for _, row in df.iterrows()]
        except Exception as e:
            return self._per_row_fallback(
                test_cases=test_cases,
                active_metric_objs=active_metric_objs,
                batch_error=str(e),
            )

    # ------------------------------------------------------------------ helpers

    def _row_to_score(self, row, latency_ms: float) -> MetricScores:
        def _pick(name: str) -> float | None:
            if name not in row:
                return None
            v = row[name]
            if v is None:
                return None
            try:
                f = float(v)
            except (TypeError, ValueError):
                return None
            if math.isnan(f):
                return None
            return f

        scores_map: dict[str, float | None] = {m: _pick(m) for m in self._active}
        errored = all(v is None for v in scores_map.values())
        err = EvalError(type="judge_null", message="all metrics None", retryable=True) if errored else None

        return MetricScores(
            faithfulness=scores_map.get("faithfulness"),
            answer_relevancy=scores_map.get("answer_relevancy"),
            context_precision=scores_map.get("context_precision"),
            context_recall=scores_map.get("context_recall"),
            scores={k: v for k, v in scores_map.items() if v is not None},
            error=err,
            latency_ms=latency_ms,
            version=self.version,
        )

    def _per_row_fallback(
        self,
        test_cases: list[dict],
        active_metric_objs,
        batch_error: str,
    ) -> list[MetricScores]:
        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate

        ragas_llm = _build_ragas_llm()

        out: list[MetricScores] = []
        for tc in test_cases:
            t0 = time.time()
            try:
                ds = Dataset.from_dict({
                    "question": [tc.get("question", "")],
                    "answer": [tc.get("answer", "")],
                    "contexts": [tc.get("contexts") or [""]],
                    "ground_truth": [tc.get("ground_truth", "")],
                })
                kwargs = {"dataset": ds, "metrics": active_metric_objs}
                if ragas_llm is not None:
                    kwargs["llm"] = ragas_llm
                r = ragas_evaluate(**kwargs)
                df = r.to_pandas()
                out.append(self._row_to_score(df.iloc[0], (time.time() - t0) * 1000.0))
            except Exception as e:
                out.append(MetricScores(
                    error=EvalError(
                        type="row_error",
                        message=f"batch_err={batch_error[:120]} row_err={str(e)[:120]}",
                        retryable=False,
                    ),
                    latency_ms=(time.time() - t0) * 1000.0,
                    version=self.version,
                ))
        return out
