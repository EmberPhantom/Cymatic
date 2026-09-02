from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

_ENV_FILE = str(Path(__file__).resolve().parents[3] / ".env")


class Settings(BaseSettings):
    APP_NAME: str = "CYMATIC LLM Router"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    LLM_ROUTER_HOST: str = "0.0.0.0"
    LLM_ROUTER_PORT: int = 8001

    REDIS_URL: str = "redis://localhost:6379/0"

    # Provider API Keys
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    NVIDIA_NIM_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    SARVAM_API_KEY: str = ""

    # Default Models
    DEFAULT_FAST_MODEL: str = "llama-3.1-8b-instant"
    DEFAULT_STRONG_MODEL: str = "gpt-4o-mini"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"
    DEFAULT_STT_PROVIDER: str = "sarvam"
    DEFAULT_TTS_PROVIDER: str = "sarvam"

    # Provider Config (can be loaded from YAML)
    PROVIDER_CONFIGS: dict = Field(default_factory=dict)

    # Admin API key for management endpoints
    ADMIN_API_KEY: str = ""

    # Rate Limiting
    RATE_LIMIT_LLM: str = "50/minute"

    # CORS
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