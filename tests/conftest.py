import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    with patch("app.config.get_settings") as mock:
        settings = MagicMock()
        settings.MONGO_URI = "mongodb://localhost:27017"
        settings.MONGO_DB = "test_db"
        settings.REDIS_URL = "redis://localhost:6379/0"
        settings.CELERY_BROKER_URL = "amqp://localhost:5672"
        settings.CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
        settings.RATE_LIMIT_PER_SECOND = 100
        settings.RATE_LIMIT_BURST = 200
        settings.CIRCUIT_BREAKER_THRESHOLD = 5
        settings.CIRCUIT_BREAKER_TIMEOUT = 30
        settings.REQUEST_TIMEOUT = 30.0
        settings.PROVIDER_A_URL = "http://localhost:8001/v1/process"
        settings.PROVIDER_B_URL = "http://localhost:8002/v1/process"
        settings.PROVIDER_C_URL = "http://localhost:8003/v1/process"
        mock.return_value = settings
        yield settings
