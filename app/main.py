from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from app.config import get_settings
from app.models.database import connect_db, close_db
from app.models.postgres import connect_postgres, close_postgres
from app.services.provider_manager import provider_manager
from app.utils.rate_limiter import rate_limiter
from app.utils.observability import ObservabilityMiddleware, get_metrics
from app.utils.auth import require_metrics_api_key
from app.routers.api import router
from prometheus_client import generate_latest
import structlog

settings = get_settings()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    await connect_postgres()
    await provider_manager.initialize()
    await rate_limiter.connect()
    yield
    await provider_manager.close()
    await rate_limiter.close()
    await close_postgres()
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    description="API Proxy Service with Fault Tolerance and Rate Limiting",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(ObservabilityMiddleware)
app.include_router(router, prefix="/v1")


@app.get("/health")
async def root_health():
    return {"status": "ok"}


@app.get("/metrics/prometheus", dependencies=[Depends(require_metrics_api_key)])
async def prometheus_metrics():
    from fastapi.responses import Response
    return Response(content=generate_latest(), media_type="text/plain")
