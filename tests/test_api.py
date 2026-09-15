import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from app.models.schemas import ProviderStatus


@pytest.mark.asyncio
async def test_health_endpoint():
    from app.main import app
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.models.database.connect_db", new_callable=AsyncMock):
            with patch("app.models.postgres.connect_postgres", new_callable=AsyncMock):
                with patch("app.services.provider_manager.provider_manager.initialize", new_callable=AsyncMock):
                    with patch("app.utils.rate_limiter.rate_limiter.connect", new_callable=AsyncMock):
                        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_process_request_returns_response():
    from app.main import app
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.models.database.connect_db", new_callable=AsyncMock):
            with patch("app.models.postgres.connect_postgres", new_callable=AsyncMock):
                with patch("app.services.provider_manager.provider_manager.initialize", new_callable=AsyncMock):
                    with patch("app.utils.rate_limiter.rate_limiter.connect", new_callable=AsyncMock):
                        with patch("app.services.provider_manager.provider_manager.send_with_retry") as mock_retry:
                            mock_retry.return_value = {
                                "status": ProviderStatus.SUCCESS,
                                "error": None,
                                "provider": "provider_a",
                                "response": {"result": "ok"},
                                "status_code": 200,
                                "latency_ms": 150.0,
                                "retry_count": 0,
                            }
                            with patch("app.routers.api.log_request", new_callable=AsyncMock):
                                with patch("app.routers.api.update_request_log", new_callable=AsyncMock):
                                    with patch("app.routers.api.persist_audit_log") as mock_task:
                                        mock_task.delay = MagicMock()
                                        response = await client.post(
                                            "/v1/process",
                                            json={"action": "test"},
                                        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "provider_a"
    assert data["latency_ms"] == 150.0
