import redis.asyncio as redis
import time
from app.config import get_settings
from fastapi import HTTPException
import structlog

logger = structlog.get_logger()
settings = get_settings()


class RateLimiter:
    def __init__(self):
        self.redis_client: redis.Redis = None
        self.enabled = True

    async def connect(self):
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("rate_limiter_connected")

    async def close(self):
        if self.redis_client:
            await self.redis_client.close()

    async def check_rate_limit(self, key: str, limit: int, window: int = 1) -> bool:
        if not self.enabled or not self.redis_client:
            return True

        try:
            now = time.time()
            window_start = now - window

            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window)
            results = await pipe.execute()

            current_count = results[2]
            if current_count > limit:
                await self.redis_client.zrem(key, str(now))
                return False
            return True
        except Exception as e:
            logger.error("rate_limit_check_failed", error=str(e))
            return True

    async def check_global_rate_limit(self) -> bool:
        return await self.check_rate_limit(
            "global_rate_limit",
            settings.RATE_LIMIT_PER_SECOND * 10,
            window=10
        )

    async def check_provider_rate_limit(self, provider_name: str) -> bool:
        return await self.check_rate_limit(
            f"provider_rate:{provider_name}",
            settings.RATE_LIMIT_PER_SECOND,
            window=1
        )

    async def get_usage(self, key: str, window: int = 1) -> int:
        if not self.redis_client:
            return 0
        try:
            now = time.time()
            window_start = now - window
            count = await self.redis_client.zcount(key, window_start, now)
            return count
        except Exception:
            return 0


rate_limiter = RateLimiter()
