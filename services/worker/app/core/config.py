from functools import lru_cache
from pathlib import Path
from typing import List, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = str(Path(__file__).resolve().parents[3] / ".env")


class Settings(BaseSettings):
    APP_NAME: str = "CYMATIC Worker"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql://cymatic:cymatic@localhost:5432/cymatic"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Redis DB 0 = queue, 5 = pubsub
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PUBSUB_URL: str | None = None
    REDIS_PASSWORD: str = ""

    POSTGRES_PASSWORD: str = "cymatic"

    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "cymatic"
    S3_REGION: str = "us-east-1"

    LLM_ROUTER_URL: str = "http://localhost:8001"
    LLM_TIMEOUT: float = 5.0

    WORKER_CONCURRENCY: int = 4
    WORKER_QUEUES: str = "generation,spec,asset,analytics"

    ADMIN_API_KEY: str = ""
    RATE_LIMIT_API: str = "1000/minute"
    WORKER_JOB_TIMEOUT_SECONDS: int = 300
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v not in ("development", "staging", "production"):
            raise ValueError("ENVIRONMENT must be development, staging, or production")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str, info: Any) -> str:
        env = info.data.get("ENVIRONMENT") if hasattr(info, "data") else None
        if env == "production" and ("localhost" in v or "127.0.0.1" in v):
            raise ValueError("DATABASE_URL must not contain localhost in production")
        return v

    @field_validator("POSTGRES_PASSWORD")
    @classmethod
    def validate_postgres_password(cls, v: str, info: Any) -> str:
        env = info.data.get("ENVIRONMENT") if hasattr(info, "data") else None
        if env == "production" and v in ("cymatic", "", "postgres"):
            raise ValueError("POSTGRES_PASSWORD must be set in production")
        return v

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
