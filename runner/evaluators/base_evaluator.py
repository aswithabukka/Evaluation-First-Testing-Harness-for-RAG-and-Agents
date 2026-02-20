from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MetricScores:
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    custom: dict = field(default_factory=dict)


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate_batch(self, test_cases: list[dict]) -> list[MetricScores]:
        """Evaluate a batch of test cases. Returns one MetricScores per case."""
        ...
