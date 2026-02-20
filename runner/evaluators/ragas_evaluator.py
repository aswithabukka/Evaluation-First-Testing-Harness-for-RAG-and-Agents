"""
Ragas-based batch evaluator.

Evaluates faithfulness, answer_relevancy, context_precision, context_recall
using the Ragas library against an LLM judge (OpenAI by default).
"""
from runner.evaluators.base_evaluator import BaseEvaluator, MetricScores


class RagasEvaluator(BaseEvaluator):
    SUPPORTED_METRICS = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    ]

    def __init__(self, metrics: list[str] | None = None, openai_api_key: str | None = None):
        self._active = [m for m in (metrics or self.SUPPORTED_METRICS) if m in self.SUPPORTED_METRICS]
        self._openai_api_key = openai_api_key

    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        """
        Each test_case dict must have:
          - question: str
          - answer: str         (actual pipeline output)
          - contexts: list[str] (retrieved context chunks)
          - ground_truth: str   (optional)
        """
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

        if not active_metric_objs or not test_cases:
            return [MetricScores() for _ in test_cases]

        data = {
            "question": [tc["question"] for tc in test_cases],
            "answer": [tc["answer"] for tc in test_cases],
            "contexts": [tc.get("contexts", [""]) for tc in test_cases],
            "ground_truth": [tc.get("ground_truth", "") for tc in test_cases],
        }

        dataset = Dataset.from_dict(data)
        result = ragas_evaluate(dataset=dataset, metrics=active_metric_objs)
        df = result.to_pandas()

        scores = []
        for _, row in df.iterrows():
            scores.append(
                MetricScores(
                    faithfulness=float(row["faithfulness"]) if "faithfulness" in row and row["faithfulness"] is not None else None,
                    answer_relevancy=float(row["answer_relevancy"]) if "answer_relevancy" in row and row["answer_relevancy"] is not None else None,
                    context_precision=float(row["context_precision"]) if "context_precision" in row and row["context_precision"] is not None else None,
                    context_recall=float(row["context_recall"]) if "context_recall" in row and row["context_recall"] is not None else None,
                )
            )
        return scores
