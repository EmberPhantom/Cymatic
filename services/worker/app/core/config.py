from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

_ENV_FILE = str(Path(__file__).resolve().parents[3] / ".env")


class Settings(BaseSettings):
    APP_NAME: str = "CYMATIC Worker"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql://cymatic:cymatic@localhost:5432/cymatic"
    REDIS_URL: str = "redis://localhost:6379/0"

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
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()