import httpx
import time
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from app.config import get_settings
from app.models.schemas import ProviderStatus
import structlog

logger = structlog.get_logger()
settings = get_settings()


class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class Provider:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.circuit_open_until: Optional[datetime] = None
        self.total_requests = 0
        self.total_failures = 0
        self.latencies: list = []

    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return sum(self.latencies[-100:]) / len(self.latencies[-100:])

    def record_success(self, latency_ms: float):
        self.failure_count = 0
        self.success_count += 1
        self.total_requests += 1
        self.latencies.append(latency_ms)
        if len(self.latencies) > 1000:
            self.latencies = self.latencies[-500:]

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.circuit_open_until = None
            logger.info("circuit_closed", provider=self.name)

    def record_failure(self):
        self.failure_count += 1
        self.total_failures += 1
        self.total_requests += 1
        self.last_failure_time = datetime.utcnow()

        if self.failure_count >= settings.CIRCUIT_BREAKER_THRESHOLD:
            self.state = CircuitState.OPEN
            self.circuit_open_until = datetime.utcnow() + timedelta(
                seconds=settings.CIRCUIT_BREAKER_TIMEOUT
            )
            logger.warning(
                "circuit_opened",
                provider=self.name,
                failure_count=self.failure_count
            )

    def is_available(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if datetime.utcnow() >= self.circuit_open_until:
                self.state = CircuitState.HALF_OPEN
                logger.info("circuit_half_open", provider=self.name)
                return True
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "provider_name": self.name,
            "url": self.url,
            "is_healthy": self.state != CircuitState.OPEN,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "circuit_open_until": self.circuit_open_until,
            "total_requests": self.total_requests,
            "successful_requests": self.total_requests - self.total_failures,
            "failed_requests": self.total_failures,
            "avg_latency_ms": self.avg_latency_ms,
            "circuit_state": self.state,
        }


class ProviderManager:
    def __init__(self):
        self.providers: Dict[str, Provider] = {
            "provider_a": Provider("provider_a", settings.PROVIDER_A_URL),
            "provider_b": Provider("provider_b", settings.PROVIDER_B_URL),
            "provider_c": Provider("provider_c", settings.PROVIDER_C_URL),
        }
        self.client: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.REQUEST_TIMEOUT),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30,
            ),
        )
        logger.info("provider_manager_initialized", providers=list(self.providers.keys()))

    async def close(self):
        if self.client:
            await self.client.aclose()

    def _select_provider(self) -> Optional[Provider]:
        available = [
            p for p in self.providers.values()
            if p.is_available()
        ]

        if not available:
            return None

        available.sort(key=lambda p: p.avg_latency_ms)
        return available[0]

    async def send_request(
        self,
        method: str,
        body: Any = None,
        headers: dict = None,
    ) -> Dict[str, Any]:
        provider = self._select_provider()
        if not provider:
            return {
                "status": ProviderStatus.CIRCUIT_OPEN,
                "error": "All providers are unavailable",
                "provider": None,
                "response": None,
                "status_code": 503,
                "latency_ms": 0,
            }

        start_time = time.time()
        try:
            response = await self.client.request(
                method=method,
                url=provider.url,
                json=body,
                headers=headers or {},
            )
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 429:
                provider.record_failure()
                return {
                    "status": ProviderStatus.RATE_LIMITED,
                    "error": "Rate limited by provider",
                    "provider": provider.name,
                    "response": None,
                    "status_code": 429,
                    "latency_ms": latency_ms,
                }

            if 500 <= response.status_code < 600:
                provider.record_failure()
                return {
                    "status": ProviderStatus.FAILED,
                    "error": f"Provider returned {response.status_code}",
                    "provider": provider.name,
                    "response": None,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                }

            provider.record_success(latency_ms)
            return {
                "status": ProviderStatus.SUCCESS,
                "error": None,
                "provider": provider.name,
                "response": response.json() if response.content else None,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            }

        except httpx.TimeoutException:
            latency_ms = (time.time() - start_time) * 1000
            provider.record_failure()
            return {
                "status": ProviderStatus.TIMEOUT,
                "error": "Request timed out",
                "provider": provider.name,
                "response": None,
                "status_code": 408,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            provider.record_failure()
            return {
                "status": ProviderStatus.FAILED,
                "error": str(e),
                "provider": provider.name,
                "response": None,
                "status_code": 500,
                "latency_ms": latency_ms,
            }

    async def send_with_retry(
        self,
        method: str,
        body: Any = None,
        headers: dict = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        last_result = None

        for attempt in range(max_retries):
            result = await self.send_request(method, body, headers)
            last_result = result
            last_result["retry_count"] = attempt

            if result["status"] in (ProviderStatus.SUCCESS,):
                return result

            if result["status"] in (ProviderStatus.CIRCUIT_OPEN,):
                break

            if attempt < max_retries - 1:
                await asyncio.sleep(0.1 * (attempt + 1))

        return last_result

    def get_all_health(self) -> Dict[str, dict]:
        return {name: p.to_dict() for name, p in self.providers.items()}


provider_manager = ProviderManager()
