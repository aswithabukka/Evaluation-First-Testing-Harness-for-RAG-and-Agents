"""
Celery task for LLM-powered test case generation.

Generates test cases via OpenAI and inserts them into a test set.
"""
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.test_case import TestCase
from app.db.models.test_set import TestSet
from app.services.generation_service import GenerationService
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, name="app.workers.tasks.generation_tasks.generate_test_cases", max_retries=1)
def generate_test_cases(self, test_set_id: str, topic: str, count: int = 10) -> dict:
    """Generate test cases for a test set using an LLM."""
    engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)

    with Session(engine) as db:
        ts = db.execute(
            select(TestSet).where(TestSet.id == uuid.UUID(test_set_id))
        ).scalar_one_or_none()

        if ts is None:
            return {"error": f"Test set {test_set_id} not found"}

        system_type = ts.system_type or "rag"

        try:
            cases = GenerationService.generate_test_cases(
                topic=topic,
                count=count,
                system_type=system_type,
            )
        except Exception as exc:
            return {"error": str(exc), "generated": 0}

        inserted = 0
        for case_data in cases:
            tc = TestCase(
                id=uuid.uuid4(),
                test_set_id=ts.id,
                query=case_data.get("query", ""),
                expected_output=case_data.get("expected_output"),
                ground_truth=case_data.get("ground_truth"),
                context=case_data.get("context"),
                failure_rules=case_data.get("failure_rules"),
                tags=case_data.get("tags", ["generated"]),
                expected_labels=case_data.get("expected_labels"),
                expected_ranking=case_data.get("expected_ranking"),
                conversation_turns=case_data.get("conversation_turns"),
            )
            db.add(tc)
            inserted += 1

        # Bump test set version (version is a string like "1.0")
        try:
            major = int(float(ts.version or "1.0"))
            ts.version = f"{major + 1}.0"
        except (ValueError, TypeError):
            ts.version = "2.0"
        db.commit()

    return {
        "test_set_id": test_set_id,
        "generated": inserted,
        "topic": topic,
    }
