import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.services.provider_manager import Provider, ProviderManager, CircuitState
from app.models.schemas import ProviderStatus


class TestCircuitBreaker:
    def test_provider_starts_closed(self, mock_settings):
        provider = Provider("test", "http://localhost:8001/v1/process")
        assert provider.state == CircuitState.CLOSED
        assert provider.is_available()

    def test_record_success_resets_failure_count(self, mock_settings):
        provider = Provider("test", "http://localhost:8001/v1/process")
        provider.failure_count = 4
        provider.record_success(100.0)
        assert provider.failure_count == 0
        assert provider.success_count == 1

    def test_circuit_opens_after_threshold(self, mock_settings):
        provider = Provider("test", "http://localhost:8001/v1/process")
        for _ in range(mock_settings.CIRCUIT_BREAKER_THRESHOLD):
            provider.record_failure()
        assert provider.state == CircuitState.OPEN
        assert not provider.is_available()

    def test_circuit_half_open_after_timeout(self, mock_settings):
        provider = Provider("test", "http://localhost:8001/v1/process")
        for _ in range(mock_settings.CIRCUIT_BREAKER_THRESHOLD):
            provider.record_failure()
        provider.circuit_open_until = datetime.utcnow() - timedelta(seconds=1)
        assert provider.is_available()
        assert provider.state == CircuitState.HALF_OPEN

    def test_circuit_closes_on_success_from_half_open(self, mock_settings):
        provider = Provider("test", "http://localhost:8001/v1/process")
        provider.state = CircuitState.HALF_OPEN
        provider.record_success(100.0)
        assert provider.state == CircuitState.CLOSED

    def test_avg_latency_rolling_window(self, mock_settings):
        provider = Provider("test", "http://localhost:8001/v1/process")
        for i in range(10):
            provider.record_success(float(i * 100))
        assert provider.avg_latency_ms == 450.0

    def test_to_dict(self, mock_settings):
        provider = Provider("test", "http://localhost:8001/v1/process")
        d = provider.to_dict()
        assert d["provider_name"] == "test"
        assert d["circuit_state"] == CircuitState.CLOSED


class TestProviderSelection:
    def test_selects_lowest_latency_provider(self, mock_settings):
        manager = ProviderManager()
        manager.providers["provider_a"].latencies = [100, 100, 100]
        manager.providers["provider_b"].latencies = [500, 500, 500]
        manager.providers["provider_c"].latencies = [300, 300, 300]

        selected = manager._select_provider()
        assert selected.name == "provider_a"

    def test_skips_unavailable_providers(self, mock_settings):
        manager = ProviderManager()
        manager.providers["provider_a"].state = CircuitState.OPEN
        manager.providers["provider_a"].circuit_open_until = datetime.utcnow() + timedelta(seconds=30)

        selected = manager._select_provider()
        assert selected.name in ("provider_b", "provider_c")

    def test_returns_none_when_all_open(self, mock_settings):
        manager = ProviderManager()
        for p in manager.providers.values():
            p.state = CircuitState.OPEN
            p.circuit_open_until = datetime.utcnow() + timedelta(seconds=30)

        selected = manager._select_provider()
        assert selected is None


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_returns_first_successful_result(self, mock_settings):
        manager = ProviderManager()
        with patch.object(manager, "send_request") as mock_send:
            mock_send.return_value = {
                "status": ProviderStatus.SUCCESS,
                "error": None,
                "provider": "provider_a",
                "response": {"result": "ok"},
                "status_code": 200,
                "latency_ms": 50.0,
            }
            result = await manager.send_with_retry("POST", body={"test": True})
            assert mock_send.call_count == 1
            assert result["status"].value == "success"

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, mock_settings):
        manager = ProviderManager()
        call_count = 0

        async def mock_send(method, body=None, headers=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {
                    "status": ProviderStatus.FAILED,
                    "error": "timeout",
                    "provider": "provider_a",
                    "response": None,
                    "status_code": 500,
                    "latency_ms": 100.0,
                }
            return {
                "status": ProviderStatus.SUCCESS,
                "error": None,
                "provider": "provider_a",
                "response": {"result": "ok"},
                "status_code": 200,
                "latency_ms": 50.0,
            }

        with patch.object(manager, "send_request", side_effect=mock_send):
            result = await manager.send_with_retry("POST", body={"test": True})
            assert call_count == 3
