"""Evaluator exports. New evaluators should also be added to EVALUATOR_REGISTRY
so the config loader can look them up by string name."""

from runner.evaluators.base_evaluator import BaseEvaluator, EvalError, MetricScores
from runner.evaluators.calibration_evaluator import CalibrationEvaluator
from runner.evaluators.citation_evaluator import CitationEvaluator
from runner.evaluators.geval_evaluator import GEvalEvaluator
from runner.evaluators.llm_judge_evaluator import LLMJudgeEvaluator
from runner.evaluators.pairwise_evaluator import PairwiseEvaluator
from runner.evaluators.ragas_evaluator import RagasEvaluator
from runner.evaluators.robustness_evaluator import RobustnessEvaluator
from runner.evaluators.safety_evaluator import SafetyEvaluator
from runner.evaluators.trajectory_evaluator import TrajectoryEvaluator

EVALUATOR_REGISTRY: dict[str, type] = {
    "ragas": RagasEvaluator,
    "llm_judge": LLMJudgeEvaluator,
    "g_eval": GEvalEvaluator,
    "pairwise": PairwiseEvaluator,
    "citation": CitationEvaluator,
    "trajectory": TrajectoryEvaluator,
    "robustness": RobustnessEvaluator,
    "calibration": CalibrationEvaluator,
    "safety": SafetyEvaluator,
}

__all__ = [
    "BaseEvaluator",
    "EvalError",
    "MetricScores",
    "EVALUATOR_REGISTRY",
    "RagasEvaluator",
    "LLMJudgeEvaluator",
    "GEvalEvaluator",
    "PairwiseEvaluator",
    "CitationEvaluator",
    "TrajectoryEvaluator",
    "RobustnessEvaluator",
    "CalibrationEvaluator",
    "SafetyEvaluator",
]
