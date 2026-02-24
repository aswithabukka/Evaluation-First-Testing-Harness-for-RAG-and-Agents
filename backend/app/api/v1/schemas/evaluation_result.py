import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EvaluationResultResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    test_case_id: uuid.UUID
    faithfulness: float | None
    answer_relevancy: float | None
    context_precision: float | None
    context_recall: float | None
    rules_passed: bool | None
    rules_detail: list[Any] | None
    llm_judge_score: float | None
    llm_judge_reasoning: str | None
    passed: bool
    failure_reason: str | None
    raw_output: str | None
    raw_contexts: list[Any] | None
    tool_calls: list[Any] | None
    extended_metrics: dict[str, Any] | None
    duration_ms: int | None
    evaluated_at: datetime

    model_config = {"from_attributes": True}


class ResultSummary(BaseModel):
    run_id: uuid.UUID
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    avg_faithfulness: float | None
    avg_answer_relevancy: float | None
    avg_context_precision: float | None
    avg_context_recall: float | None


class RegressionItem(BaseModel):
    test_case_id: uuid.UUID
    query: str
    failure_reason: str | None
    current_scores: dict[str, float | None]
    baseline_scores: dict[str, float | None]


class RegressionDiff(BaseModel):
    run_id: uuid.UUID
    baseline_run_id: uuid.UUID | None
    regressions: list[RegressionItem]
    improvements: list[RegressionItem]
    metric_deltas: dict[str, float | None]
    gate_blocked: bool
