from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "proxy_service",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_soft_time_limit=30,
    task_time_limit=60,
)

celery_app.autodiscover_tasks(["app.tasks"])
