from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, DateTime, JSON, Text, func
from app.config import get_settings
from typing import Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()
settings = get_settings()


class Base(DeclarativeBase):
    pass


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    trace_id: Mapped[str] = mapped_column(String(16), index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(256))
    client_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    provider_used: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    request_body: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    response_body: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class PostgresDB:
    engine = None
    session_factory = None


pg = PostgresDB()


async def connect_postgres():
    pg.engine = create_async_engine(
        settings.POSTGRES_URL,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    )
    pg.session_factory = async_sessionmaker(pg.engine, expire_on_commit=False)

    async with pg.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("postgres_connected", url=settings.POSTGRES_URL.split("@")[-1])


async def close_postgres():
    if pg.engine:
        await pg.engine.dispose()
        logger.info("postgres_closed")


async def get_session() -> AsyncSession:
    return pg.session_factory()


async def audit_log_request(
    request_id: str,
    trace_id: str,
    method: str,
    path: str,
    client_ip: Optional[str],
    provider_used: Optional[str],
    status: str,
    response_status_code: Optional[int],
    response_time_ms: Optional[float],
    error_message: Optional[str],
    retry_count: int,
    request_body: Optional[dict],
    response_body: Optional[dict],
    completed_at: Optional[datetime],
):
    try:
        async with pg.session_factory() as session:
            log = AuditLog(
                request_id=request_id,
                trace_id=trace_id,
                method=method,
                path=path,
                client_ip=client_ip,
                provider_used=provider_used,
                status=status,
                response_status_code=response_status_code,
                response_time_ms=response_time_ms,
                error_message=error_message,
                retry_count=retry_count,
                request_body=request_body,
                response_body=response_body,
                completed_at=completed_at,
            )
            session.add(log)
            await session.commit()
    except Exception as e:
        logger.error("audit_log_failed", error=str(e))
