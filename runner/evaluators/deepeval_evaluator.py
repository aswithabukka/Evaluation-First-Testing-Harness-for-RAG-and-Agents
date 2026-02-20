"""
DeepEval-based evaluator.

Provides an alternative to Ragas with pytest-style assertions and a rich set
of metrics including hallucination detection and contextual relevancy.
"""
from runner.evaluators.base_evaluator import BaseEvaluator, MetricScores


class DeepEvalEvaluator(BaseEvaluator):
    def __init__(
        self,
        threshold: float = 0.7,
        metrics: list[str] | None = None,
    ):
        self._threshold = threshold
        self._metrics = metrics or ["answer_relevancy", "faithfulness"]

    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        from deepeval import evaluate
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
        from deepeval.test_cases import LLMTestCase

        metric_map = {
            "answer_relevancy": AnswerRelevancyMetric(threshold=self._threshold),
            "faithfulness": FaithfulnessMetric(threshold=self._threshold),
        }
        active_metrics = [metric_map[m] for m in self._metrics if m in metric_map]

        de_cases = [
            LLMTestCase(
                input=tc["question"],
                actual_output=tc["answer"],
                expected_output=tc.get("ground_truth"),
                retrieval_context=tc.get("contexts", []),
            )
            for tc in test_cases
        ]

        results = evaluate(de_cases, active_metrics)

        scores = []
        for test_result in results.test_results:
            metrics_by_name = {m.name: m for m in test_result.metrics_data}
            scores.append(
                MetricScores(
                    faithfulness=self._extract(metrics_by_name, "FaithfulnessMetric"),
                    answer_relevancy=self._extract(metrics_by_name, "AnswerRelevancyMetric"),
                )
            )
        return scores

    @staticmethod
    def _extract(metrics_by_name: dict, name: str) -> float | None:
        m = metrics_by_name.get(name)
        return float(m.score) if m and m.score is not None else None
