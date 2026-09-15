from fastapi import APIRouter, Request, HTTPException
from app.services.provider_manager import provider_manager
from app.utils.rate_limiter import rate_limiter
from app.utils.observability import (
    generate_request_id,
    generate_trace_id,
    PROVIDER_REQUESTS,
    PROVIDER_LATENCY,
)
from app.models.schemas import RequestLog, ProviderStatus
from app.models.database import log_request, update_request_log, get_request_log, get_request_logs, get_metrics
from app.tasks.worker import persist_audit_log
from datetime import datetime
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.post("/process")
async def process_request(request: Request):
    request_id = getattr(request.state, "request_id", generate_request_id())
    trace_id = getattr(request.state, "trace_id", generate_trace_id())

    if not await rate_limiter.check_global_rate_limit():
        logger.warning("global_rate_limit_exceeded", request_id=request_id)
        raise HTTPException(status_code=429, detail="Global rate limit exceeded")

    body = await request.json() if request.headers.get("content-type") == "application/json" else None

    request_log = RequestLog(
        request_id=request_id,
        trace_id=trace_id,
        method=request.method,
        path=str(request.url.path),
        headers=dict(request.headers),
        body=body,
        query_params=dict(request.query_params),
        client_ip=request.client.host if request.client else None,
        timestamp=datetime.utcnow(),
        status="processing",
    )

    await log_request(request_log)

    result = await provider_manager.send_with_retry(
        method="POST",
        body=body,
        headers={"Content-Type": "application/json"},
    )

    status_value = result["status"].value if isinstance(result["status"], ProviderStatus) else str(result["status"])

    PROVIDER_REQUESTS.labels(
        provider=result.get("provider", "none"),
        status=status_value,
    ).inc()

    PROVIDER_LATENCY.labels(
        provider=result.get("provider", "none")
    ).observe(result["latency_ms"] / 1000)

    update_data = {
        "status": status_value,
        "response_status_code": result["status_code"],
        "response_body": result["response"],
        "response_time_ms": result["latency_ms"],
        "provider_used": result.get("provider"),
        "provider_status": status_value,
        "error_message": result.get("error"),
        "retry_count": result.get("retry_count", 0),
        "completed_at": datetime.utcnow(),
    }
    await update_request_log(request_id, update_data)

    # Postgres فقط یک رکورد فشرده‌ی حسابرسی نگه می‌دارد؛ payload در Mongo می‌ماند.
    persist_audit_log.delay({
        "request_id": request_id,
        "trace_id": trace_id,
        "method": request.method,
        "path": str(request.url.path),
        "client_ip": request.client.host if request.client else None,
        "provider_used": result.get("provider"),
        "status": status_value,
        "response_status_code": result["status_code"],
        "response_time_ms": result["latency_ms"],
        "error_message": result.get("error"),
        "retry_count": result.get("retry_count", 0),
        "completed_at": datetime.utcnow().isoformat(),
    })

    return {
        "request_id": request_id,
        "trace_id": trace_id,
        "status": status_value,
        "provider": result.get("provider"),
        "latency_ms": round(result["latency_ms"], 2),
        "response": result["response"],
        "error": result.get("error"),
    }


@router.get("/status/{request_id}")
async def get_status(request_id: str):
    log = await get_request_log(request_id)
    if not log:
        raise HTTPException(status_code=404, detail="Request not found")
    return log


@router.get("/history")
async def get_history(limit: int = 100, skip: int = 0):
    return await get_request_logs(limit=limit, skip=skip)


@router.get("/health")
async def health_check():
    health = provider_manager.get_all_health()
    return {
        "status": "healthy",
        "providers": health,
    }


@router.get("/metrics")
async def metrics():
    return await get_metrics()
