from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "rageval",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.evaluation_tasks",
        "app.workers.tasks.ingestion_tasks",
        "app.workers.tasks.generation_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.evaluation_tasks.run_evaluation": {"queue": "evaluations"},
        "app.workers.tasks.ingestion_tasks.evaluate_sampled_traffic": {"queue": "evaluations"},
    },
    # Celery Beat — periodic tasks
    beat_schedule={
        "evaluate-sampled-traffic-hourly": {
            "task": "app.workers.tasks.ingestion_tasks.evaluate_sampled_traffic",
            "schedule": crontab(minute=0),  # Every hour at :00
            "options": {"queue": "evaluations"},
        },
    },
)
