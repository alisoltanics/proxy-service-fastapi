from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING
from app.config import get_settings
from app.models.schemas import RequestLog, ProviderHealth
from typing import Optional, List
from datetime import datetime
import structlog

logger = structlog.get_logger()

settings = get_settings()


class Database:
    client: Optional[AsyncIOMotorClient] = None
    db = None


db = Database()


async def connect_db():
    db.client = AsyncIOMotorClient(settings.MONGO_URI)
    db.db = db.client[settings.MONGO_DB]

    await db.db.request_logs.create_indexes([
        IndexModel([("request_id", ASCENDING)], unique=True),
        IndexModel([("trace_id", ASCENDING)]),
        IndexModel([("timestamp", ASCENDING)]),
        IndexModel([("provider_used", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
    ])

    await db.db.provider_health.create_indexes([
        IndexModel([("provider_name", ASCENDING)], unique=True),
    ])

    logger.info("database_connected", mongo_uri=settings.MONGO_URI)


async def close_db():
    if db.client:
        db.client.close()
        logger.info("database_closed")


async def log_request(request_log: RequestLog):
    try:
        await db.db.request_logs.insert_one(request_log.model_dump())
        logger.debug("request_logged", request_id=request_log.request_id)
    except Exception as e:
        logger.error("failed_to_log_request", error=str(e))


async def update_request_log(request_id: str, update_data: dict):
    try:
        await db.db.request_logs.update_one(
            {"request_id": request_id},
            {"$set": update_data}
        )
    except Exception as e:
        logger.error("failed_to_update_request", request_id=request_id, error=str(e))


async def get_request_log(request_id: str) -> Optional[dict]:
    return await db.db.request_logs.find_one(
        {"request_id": request_id},
        {"_id": 0}
    )


async def get_request_logs(limit: int = 100, skip: int = 0) -> List[dict]:
    cursor = db.db.request_logs.find({}, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def get_provider_health(provider_name: str) -> Optional[dict]:
    return await db.db.provider_health.find_one(
        {"provider_name": provider_name},
        {"_id": 0}
    )


async def update_provider_health(provider_name: str, health_data: dict):
    await db.db.provider_health.update_one(
        {"provider_name": provider_name},
        {"$set": health_data},
        upsert=True
    )


async def get_metrics() -> dict:
    pipeline = [
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]
    status_counts = {}
    async for doc in db.db.request_logs.aggregate(pipeline):
        status_counts[doc["_id"]] = doc["count"]

    pipeline = [
        {"$group": {
            "_id": "$provider_used",
            "count": {"$sum": 1},
            "avg_latency": {"$avg": "$response_time_ms"},
            "errors": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}}
        }}
    ]
    provider_stats = []
    async for doc in db.db.request_logs.aggregate(pipeline):
        provider_stats.append(doc)

    total = sum(status_counts.values())
    return {
        "total_requests": total,
        "status_counts": status_counts,
        "provider_stats": provider_stats,
    }
