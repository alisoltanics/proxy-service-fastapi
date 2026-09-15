from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Proxy Service"
    DEBUG: bool = False

    MONGO_URI: str = "mongodb://mongo:27017"
    MONGO_DB: str = "proxy_service"

    POSTGRES_URL: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/proxy_audit"

    REDIS_URL: str = "redis://redis:6379/0"

    CELERY_BROKER_URL: str = "amqp://rabbitmq:5672"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    RATE_LIMIT_PER_SECOND: int = 100
    RATE_LIMIT_BURST: int = 200

    METRICS_API_KEY: str = "proxy-metrics-secret"

    PROVIDER_A_URL: str = "http://92.114.51.251:8001/v1/process"
    PROVIDER_B_URL: str = "http://92.114.51.251:8002/v1/process"
    PROVIDER_C_URL: str = "http://92.114.51.251:8003/v1/process"

    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_TIMEOUT: int = 30

    REQUEST_TIMEOUT: float = 30.0

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
