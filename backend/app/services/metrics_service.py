import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.metrics_history import MetricsHistory


class MetricsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_trends(
        self, test_set_id: uuid.UUID, metric: str, days: int = 30
    ) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            select(MetricsHistory)
            .where(
                MetricsHistory.test_set_id == test_set_id,
                MetricsHistory.metric_name == metric,
                MetricsHistory.recorded_at >= since,
            )
            .order_by(MetricsHistory.recorded_at.asc())
        )
        return [
            {
                "recorded_at": r.recorded_at.isoformat(),
                "metric_value": r.metric_value,
                "metric_name": r.metric_name,
                "pipeline_version": r.pipeline_version,
                "git_commit_sha": r.git_commit_sha,
                "run_id": str(r.run_id),
            }
            for r in result.scalars().all()
        ]

    async def record_run_metrics(
        self,
        test_set_id: uuid.UUID,
        run_id: uuid.UUID,
        summary: dict,
        pipeline_version: str | None,
        git_commit_sha: str | None,
    ) -> None:
        metric_map = {
            "faithfulness": summary.get("avg_faithfulness"),
            "answer_relevancy": summary.get("avg_answer_relevancy"),
            "context_precision": summary.get("avg_context_precision"),
            "context_recall": summary.get("avg_context_recall"),
            "pass_rate": summary.get("pass_rate"),
        }
        entries = [
            MetricsHistory(
                test_set_id=test_set_id,
                run_id=run_id,
                metric_name=metric,
                metric_value=value,
                pipeline_version=pipeline_version,
                git_commit_sha=git_commit_sha,
            )
            for metric, value in metric_map.items()
            if value is not None
        ]
        if entries:
            self.db.add_all(entries)
            await self.db.flush()
