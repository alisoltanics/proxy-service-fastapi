from fastapi import Header, HTTPException
from app.config import get_settings

settings = get_settings()


async def require_metrics_api_key(x_api_key: str = Header(default=None)):
    """Dependency that protects metrics endpoints with a shared API key."""
    if x_api_key != settings.METRICS_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
