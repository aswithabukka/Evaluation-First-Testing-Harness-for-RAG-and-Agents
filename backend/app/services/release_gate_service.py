import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.evaluation_result import RegressionDiff, RegressionItem
from app.core.exceptions import NotFoundError
from app.db.models.evaluation_result import EvaluationResult
from app.db.models.evaluation_run import EvaluationRun, RunStatus
from app.db.models.test_case import TestCase
from app.services._gate_stats import significance_gate


# Per-case column on EvaluationResult that corresponds to each summary key.
# Drives the significance gate: we pull the raw per-case values here and feed
# them to bootstrap/Mann-Whitney instead of comparing the summary mean alone.
_METRIC_COLUMNS: dict[str, str] = {
    "faithfulness": "faithfulness",
    "answer_relevancy": "answer_relevancy",
    "context_precision": "context_precision",
    "context_recall": "context_recall",
    # pass_rate has no per-case column; handled via a boolean->float fallback below.
}


@dataclass
class GateFailure:
    metric: str
    actual: float
    threshold: float
    delta: float
    # New: CI bounds + significance context. ``None`` on the pass_rate path
    # (no per-case samples) so the JSON shape stays backwards-compatible.
    ci_lower: float | None = None
    ci_upper: float | None = None
    p_value: float | None = None
    sample_size: int = 0
    baseline_size: int = 0
    reason: str = ""


@dataclass
class GateDecision:
    passed: bool
    run_id: uuid.UUID
    metric_failures: list[GateFailure] = field(default_factory=list)
    rule_failures: list[dict] = field(default_factory=list)
    regression_diff: RegressionDiff | None = None


class ReleaseGateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate_gate(self, run_id: uuid.UUID) -> dict:
        run = await self._get_run_or_404(run_id)

        if run.status not in (RunStatus.COMPLETED, RunStatus.GATE_BLOCKED):
            return {
                "passed": None,
                "status": run.status.value,
                "message": "Run has not completed yet",
            }

        thresholds = run.gate_threshold_snapshot or {}
        summary = run.summary_metrics or {}

        # Significance-aware gate: for each metric with per-case scores, run
        # bootstrap CI + Mann-Whitney vs. the last passing baseline. Falls
        # back to the classic "mean < threshold" check for pass_rate (which
        # is already a derived scalar).
        current_results = await self._fetch_results_list(run_id)
        baseline_run = await self._find_last_passing_baseline(run)
        baseline_results = (
            await self._fetch_results_list(baseline_run.id) if baseline_run else []
        )

        metric_failures: list[GateFailure] = []

        for metric, column in _METRIC_COLUMNS.items():
            threshold = thresholds.get(metric)
            if threshold is None:
                continue
            current_vals = [getattr(r, column) for r in current_results]
            current_vals = [v for v in current_vals if v is not None]
            if not current_vals:
                continue
            baseline_vals = [getattr(r, column) for r in baseline_results]
            baseline_vals = [v for v in baseline_vals if v is not None]

            decision = significance_gate(
                current_vals,
                baseline=baseline_vals or None,
                threshold=threshold,
                higher_is_better=True,
            )
            if not decision.passed:
                metric_failures.append(
                    GateFailure(
                        metric=metric,
                        actual=decision.point_estimate,
                        threshold=threshold,
                        delta=decision.point_estimate - threshold,
                        ci_lower=decision.ci_lower,
                        ci_upper=decision.ci_upper,
                        p_value=decision.p_value,
                        sample_size=decision.sample_size,
                        baseline_size=decision.baseline_size,
                        reason=decision.reason,
                    )
                )

        # pass_rate: no per-case raw values — keep the classic check.
        pr_actual = summary.get("pass_rate")
        pr_threshold = thresholds.get("pass_rate")
        if pr_actual is not None and pr_threshold is not None and pr_actual < pr_threshold:
            metric_failures.append(
                GateFailure(
                    metric="pass_rate",
                    actual=pr_actual,
                    threshold=pr_threshold,
                    delta=pr_actual - pr_threshold,
                    reason=f"pass_rate {pr_actual:.3f} < threshold {pr_threshold:.3f}",
                )
            )

        # Check for zero-tolerance rule failures
        rule_failures_result = await self.db.execute(
            select(EvaluationResult).where(
                EvaluationResult.run_id == run_id,
                EvaluationResult.rules_passed == False,  # noqa: E712
            )
        )
        rule_failures = [
            {
                "result_id": str(r.id),
                "test_case_id": str(r.test_case_id),
                "rules_detail": r.rules_detail,
            }
            for r in rule_failures_result.scalars().all()
        ]

        gate_passed = len(metric_failures) == 0 and len(rule_failures) == 0

        return {
            "passed": gate_passed,
            "run_id": str(run_id),
            "metric_failures": [
                {
                    "metric": f.metric,
                    "actual": f.actual,
                    "threshold": f.threshold,
                    "delta": f.delta,
                    "ci_lower": f.ci_lower,
                    "ci_upper": f.ci_upper,
                    "p_value": f.p_value,
                    "sample_size": f.sample_size,
                    "baseline_size": f.baseline_size,
                    "reason": f.reason,
                }
                for f in metric_failures
            ],
            "rule_failures": rule_failures,
            "baseline_run_id": str(baseline_run.id) if baseline_run else None,
        }

    async def compute_regression_diff(self, run_id: uuid.UUID) -> RegressionDiff:
        run = await self._get_run_or_404(run_id)

        # Find the last completed passing run for the same test set
        baseline_result = await self.db.execute(
            select(EvaluationRun)
            .where(
                EvaluationRun.test_set_id == run.test_set_id,
                EvaluationRun.id != run_id,
                EvaluationRun.overall_passed == True,  # noqa: E712
                EvaluationRun.status == RunStatus.COMPLETED,
            )
            .order_by(EvaluationRun.completed_at.desc())
            .limit(1)
        )
        baseline = baseline_result.scalar_one_or_none()

        # Fetch current run results
        current_results = await self._fetch_results_map(run_id)

        if baseline is None:
            return RegressionDiff(
                run_id=run_id,
                baseline_run_id=None,
                regressions=[],
                improvements=[],
                metric_deltas={},
                gate_blocked=not (run.overall_passed or False),
            )

        baseline_results = await self._fetch_results_map(baseline.id)

        regressions = []
        improvements = []

        for case_id, current in current_results.items():
            baseline_r = baseline_results.get(case_id)
            if baseline_r is None:
                continue

            # Fetch query text
            tc_result = await self.db.execute(
                select(TestCase.query).where(TestCase.id == case_id)
            )
            query_text = tc_result.scalar_one_or_none() or ""

            current_scores = self._extract_scores(current)
            baseline_scores = self._extract_scores(baseline_r)

            item = RegressionItem(
                test_case_id=case_id,
                query=query_text,
                failure_reason=current.failure_reason,
                current_scores=current_scores,
                baseline_scores=baseline_scores,
            )

            if not current.passed and baseline_r.passed:
                regressions.append(item)
            elif current.passed and not baseline_r.passed:
                improvements.append(item)

        # Compute aggregate metric deltas
        current_summary = run.summary_metrics or {}
        baseline_summary = baseline.summary_metrics or {}

        metric_deltas = {}
        for metric in ("avg_faithfulness", "avg_answer_relevancy", "avg_context_precision", "avg_context_recall", "pass_rate"):
            c = current_summary.get(metric)
            b = baseline_summary.get(metric)
            metric_deltas[metric] = (c - b) if c is not None and b is not None else None

        return RegressionDiff(
            run_id=run_id,
            baseline_run_id=baseline.id,
            regressions=regressions,
            improvements=improvements,
            metric_deltas=metric_deltas,
            gate_blocked=len(regressions) > 0,
        )

    async def get_thresholds(self, test_set_id: uuid.UUID) -> dict:
        result = await self.db.execute(
            select(EvaluationRun.gate_threshold_snapshot)
            .where(EvaluationRun.test_set_id == test_set_id)
            .order_by(EvaluationRun.started_at.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()
        if snapshot:
            return snapshot
        from app.core.config import settings
        return {
            "faithfulness": settings.DEFAULT_FAITHFULNESS_THRESHOLD,
            "answer_relevancy": settings.DEFAULT_ANSWER_RELEVANCY_THRESHOLD,
            "context_precision": settings.DEFAULT_CONTEXT_PRECISION_THRESHOLD,
            "context_recall": settings.DEFAULT_CONTEXT_RECALL_THRESHOLD,
            "pass_rate": settings.DEFAULT_PASS_RATE_THRESHOLD,
        }

    async def update_thresholds(self, test_set_id: uuid.UUID, thresholds: dict) -> dict:
        # Thresholds are stored per-run; this updates a global default stored in app config
        # For now, return the thresholds — a production system would persist these in a config table
        return {"test_set_id": str(test_set_id), "thresholds": thresholds}

    async def _get_run_or_404(self, run_id: uuid.UUID) -> EvaluationRun:
        result = await self.db.execute(
            select(EvaluationRun).where(EvaluationRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise NotFoundError("EvaluationRun", str(run_id))
        return run

    async def _fetch_results_map(self, run_id: uuid.UUID) -> dict[uuid.UUID, EvaluationResult]:
        result = await self.db.execute(
            select(EvaluationResult).where(EvaluationResult.run_id == run_id)
        )
        return {r.test_case_id: r for r in result.scalars().all()}

    async def _fetch_results_list(self, run_id: uuid.UUID) -> list[EvaluationResult]:
        result = await self.db.execute(
            select(EvaluationResult).where(EvaluationResult.run_id == run_id)
        )
        return list(result.scalars().all())

    async def _find_last_passing_baseline(
        self, run: EvaluationRun
    ) -> EvaluationRun | None:
        """Most recent completed+passing run for the same test set, excluding
        the run under evaluation. Used as the comparison group for
        Mann-Whitney significance testing."""
        result = await self.db.execute(
            select(EvaluationRun)
            .where(
                EvaluationRun.test_set_id == run.test_set_id,
                EvaluationRun.id != run.id,
                EvaluationRun.overall_passed == True,  # noqa: E712
                EvaluationRun.status == RunStatus.COMPLETED,
            )
            .order_by(EvaluationRun.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _extract_scores(r: EvaluationResult) -> dict[str, float | None]:
        return {
            "faithfulness": r.faithfulness,
            "answer_relevancy": r.answer_relevancy,
            "context_precision": r.context_precision,
            "context_recall": r.context_recall,
        }
