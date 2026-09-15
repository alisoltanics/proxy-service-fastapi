from app.tasks.celery_app import celery_app
from motor.motor_asyncio import AsyncIOMotorClient
from app.models.postgres import insert_audit_log
from app.config import get_settings
from datetime import datetime, timedelta
import asyncio
import structlog

logger = structlog.get_logger()


@celery_app.task(bind=True, max_retries=3)
def persist_audit_log(self, audit_data: dict):
    try:
        asyncio.run(insert_audit_log(audit_data))
        logger.info("audit_log_persisted", request_id=audit_data.get("request_id"))
    except Exception as e:
        logger.error("audit_log_failed", error=str(e))
        raise self.retry(exc=e, countdown=5)


@celery_app.task
def cleanup_old_logs(days_old: int = 30):
    try:
        settings = get_settings()
        client = AsyncIOMotorClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]

        cutoff = datetime.utcnow() - timedelta(days=days_old)

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            db.request_logs.delete_many({"timestamp": {"$lt": cutoff}})
        )
        loop.close()
        client.close()

        logger.info("logs_cleaned", deleted_count=result.deleted_count)
    except Exception as e:
        logger.error("cleanup_failed", error=str(e))


celery_app.conf.beat_schedule = {
    "cleanup-old-logs": {
        "task": "app.tasks.worker.cleanup_old_logs",
        "schedule": 86400.0,
        "args": (30,),
    },
}
