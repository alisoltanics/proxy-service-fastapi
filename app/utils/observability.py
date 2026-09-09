import uuid
import time
import structlog
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

logger = structlog.get_logger()

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

ACTIVE_REQUESTS = Gauge(
    "http_active_requests",
    "Number of active HTTP requests"
)

PROVIDER_REQUESTS = Counter(
    "provider_requests_total",
    "Total provider requests",
    ["provider", "status"]
)

PROVIDER_LATENCY = Histogram(
    "provider_request_duration_seconds",
    "Provider request latency in seconds",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)


def generate_request_id() -> str:
    return str(uuid.uuid4())


def generate_trace_id() -> str:
    return str(uuid.uuid4()).replace("-", "")[:16]


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        request_id = generate_request_id()
        trace_id = generate_trace_id()

        request.state.request_id = request_id
        request.state.trace_id = trace_id

        start_time = time.time()
        ACTIVE_REQUESTS.inc()

        logger.info(
            "request_started",
            request_id=request_id,
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)
        except Exception as e:
            ACTIVE_REQUESTS.dec()
            logger.error(
                "request_failed",
                request_id=request_id,
                trace_id=trace_id,
                error=str(e),
            )
            raise

        ACTIVE_REQUESTS.dec()
        latency = time.time() - start_time

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code
        ).inc()

        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(latency)

        logger.info(
            "request_completed",
            request_id=request_id,
            trace_id=trace_id,
            status_code=response.status_code,
            latency_ms=round(latency * 1000, 2),
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id

        return response


def get_metrics() -> bytes:
    return generate_latest()
