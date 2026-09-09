from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class ProviderStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CIRCUIT_OPEN = "circuit_open"


class RequestLog(BaseModel):
    request_id: str = Field(..., description="Unique request trace ID")
    trace_id: str = Field(..., description="Distributed trace ID")
    method: str
    path: str
    headers: dict = {}
    body: Optional[Any] = None
    query_params: dict = {}
    client_ip: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"
    response_status_code: Optional[int] = None
    response_body: Optional[Any] = None
    response_time_ms: Optional[float] = None
    provider_used: Optional[str] = None
    provider_status: Optional[ProviderStatus] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    completed_at: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ProviderHealth(BaseModel):
    provider_name: str
    url: str
    is_healthy: bool = True
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    circuit_open_until: Optional[datetime] = None
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
