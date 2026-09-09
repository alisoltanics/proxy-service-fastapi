import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from app.utils.rate_limiter import RateLimiter


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_request_within_limit(self, mock_settings):
        limiter = RateLimiter()
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[None, None, 5, True])
        mock_redis.pipeline.return_value = mock_pipe
        limiter.redis_client = mock_redis

        result = await limiter.check_rate_limit("test_key", limit=10, window=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_request_over_limit(self, mock_settings):
        limiter = RateLimiter()
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[None, None, 15, True])
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.zrem = AsyncMock()
        limiter.redis_client = mock_redis

        result = await limiter.check_rate_limit("test_key", limit=10, window=1)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_disabled(self, mock_settings):
        limiter = RateLimiter()
        limiter.enabled = False
        result = await limiter.check_rate_limit("test_key", limit=10)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_on_redis_error(self, mock_settings):
        limiter = RateLimiter()
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=Exception("Redis error"))
        mock_redis.pipeline.return_value = mock_pipe
        limiter.redis_client = mock_redis

        result = await limiter.check_rate_limit("test_key", limit=10)
        assert result is True

    @pytest.mark.asyncio
    async def test_global_rate_limit(self, mock_settings):
        limiter = RateLimiter()
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[None, None, 500, True])
        mock_redis.pipeline.return_value = mock_pipe
        limiter.redis_client = mock_redis

        result = await limiter.check_global_rate_limit()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_usage(self, mock_settings):
        limiter = RateLimiter()
        mock_redis = AsyncMock()
        mock_redis.zcount = AsyncMock(return_value=42)
        limiter.redis_client = mock_redis

        usage = await limiter.get_usage("test_key", window=1)
        assert usage == 42
