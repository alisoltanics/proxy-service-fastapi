import pytest
from app.models.schemas import RequestLog, ProviderStatus, ProviderHealth
from datetime import datetime


class TestSchemas:
    def test_request_log_creation(self):
        log = RequestLog(
            request_id="test-123",
            trace_id="trace456",
            method="POST",
            path="/v1/process",
            body={"action": "test"},
            timestamp=datetime.utcnow(),
            status="processing",
        )
        assert log.request_id == "test-123"
        assert log.method == "POST"
        assert log.status == "processing"

    def test_request_log_defaults(self):
        log = RequestLog(
            request_id="test-123",
            trace_id="trace456",
            method="POST",
            path="/v1/process",
        )
        assert log.headers == {}
        assert log.query_params == {}
        assert log.retry_count == 0

    def test_provider_status_enum(self):
        assert ProviderStatus.SUCCESS == "success"
        assert ProviderStatus.FAILED == "failed"
        assert ProviderStatus.TIMEOUT == "timeout"
        assert ProviderStatus.RATE_LIMITED == "rate_limited"
        assert ProviderStatus.CIRCUIT_OPEN == "circuit_open"

    def test_provider_health_creation(self):
        health = ProviderHealth(
            provider_name="provider_a",
            url="http://localhost:8001/v1/process",
            is_healthy=True,
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            avg_latency_ms=150.0,
        )
        assert health.provider_name == "provider_a"
        assert health.avg_latency_ms == 150.0
