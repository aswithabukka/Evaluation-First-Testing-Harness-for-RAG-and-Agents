"""
Stratified sampling engine for production traffic.

Sampling strategy:
  - 100% of errors (is_error=True) and low-confidence responses
  - 100% of negative user feedback (thumbs_down)
  - N% of normal traffic (configurable via SAMPLING_RATE)

Sampled entries are converted to test cases and added to an
auto-managed test set per source (e.g., "Production: customer-support-bot").
"""
import random
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.production_log import IngestionStatus, ProductionLog
from app.db.models.test_case import TestCase
from app.db.models.test_set import TestSet


class SamplingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def should_sample(self, log: ProductionLog) -> bool:
        """Decide whether a production log entry should be sampled for evaluation."""
        # Always sample errors
        if log.is_error:
            return random.random() < settings.SAMPLING_ERROR_RATE

        # Always sample negative feedback
        if log.user_feedback == "thumbs_down":
            return True

        # Always sample low-confidence responses
        if log.confidence_score is not None and log.confidence_score < 0.5:
            return random.random() < settings.SAMPLING_ERROR_RATE

        # Random sample of normal traffic
        return random.random() < settings.SAMPLING_RATE

    async def _get_or_create_test_set(self, source: str) -> TestSet:
        """Get or create the auto-managed test set for a production source."""
        name = f"Production: {source}"
        result = await self.db.execute(
            select(TestSet).where(TestSet.name == name)
        )
        ts = result.scalar_one_or_none()
        if ts is not None:
            return ts

        ts = TestSet(
            id=uuid.uuid4(),
            name=name,
            description=(
                f"Auto-generated test set from production traffic for '{source}'. "
                "Entries are sampled from live Q&A pairs."
            ),
            version="auto",
        )
        self.db.add(ts)
        await self.db.flush()
        return ts

    async def sample_and_create_test_case(self, log: ProductionLog) -> bool:
        """
        Apply sampling logic to a production log entry.
        If sampled, create a test case. Returns True if sampled.
        """
        if not self.should_sample(log):
            log.status = IngestionStatus.SKIPPED
            return False

        ts = await self._get_or_create_test_set(log.source)

        # Build failure rules based on the production context
        failure_rules = []
        if log.is_error:
            failure_rules.append({"type": "must_refuse"})
        if log.user_feedback == "thumbs_down":
            failure_rules.append({
                "type": "max_hallucination_risk",
                "threshold": 0.5,
            })

        # Build tags
        tags = list(log.tags or [])
        tags.append(f"source:{log.source}")
        if log.is_error:
            tags.append("error")
        if log.user_feedback:
            tags.append(f"feedback:{log.user_feedback}")

        tc = TestCase(
            id=uuid.uuid4(),
            test_set_id=ts.id,
            query=log.query,
            ground_truth=log.answer,  # Production answer becomes ground truth reference
            context=log.contexts,
            failure_rules=failure_rules if failure_rules else None,
            tags=tags,
        )
        self.db.add(tc)
        await self.db.flush()

        log.status = IngestionStatus.SAMPLED
        log.sampled_into_test_set_id = ts.id
        log.sampled_into_test_case_id = tc.id
        log.sampled_at = datetime.now(timezone.utc)

        return True

    async def get_stats(self, source: str | None = None) -> list[dict]:
        """Get sampling statistics, optionally filtered by source."""
        query = select(
            ProductionLog.source,
            ProductionLog.status,
            func.count().label("count"),
        ).group_by(ProductionLog.source, ProductionLog.status)

        if source:
            query = query.where(ProductionLog.source == source)

        result = await self.db.execute(query)
        rows = result.all()

        # Aggregate by source
        stats_by_source: dict[str, dict] = {}
        for row in rows:
            src = row.source
            if src not in stats_by_source:
                stats_by_source[src] = {
                    "source": src,
                    "total_received": 0,
                    "total_sampled": 0,
                    "total_skipped": 0,
                    "total_evaluated": 0,
                }
            status_val = row.status
            count = row.count
            if status_val == IngestionStatus.RECEIVED:
                stats_by_source[src]["total_received"] += count
            elif status_val == IngestionStatus.SAMPLED:
                stats_by_source[src]["total_sampled"] += count
            elif status_val == IngestionStatus.SKIPPED:
                stats_by_source[src]["total_skipped"] += count
            elif status_val == IngestionStatus.EVALUATED:
                stats_by_source[src]["total_evaluated"] += count

        result_list = []
        for src, data in stats_by_source.items():
            total = sum(data[k] for k in ["total_received", "total_sampled", "total_skipped", "total_evaluated"])
            sampled = data["total_sampled"] + data["total_evaluated"]
            result_list.append({
                **data,
                "sampling_rate": settings.SAMPLING_RATE,
                "error_sampling_rate": settings.SAMPLING_ERROR_RATE,
            })

        return result_list
