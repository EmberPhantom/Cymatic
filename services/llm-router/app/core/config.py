from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode

_CONFIG_PATH = Path(__file__).resolve()
# The repository layout has four parents above this file; the container image
# is rooted at /app and has fewer parents. Compose injects environment values
# directly, so a missing container-local .env is valid.
_ENV_FILE = (
    str(_CONFIG_PATH.parents[4] / ".env") if len(_CONFIG_PATH.parents) > 4 else ".env"
)


class Settings(BaseSettings):
    APP_NAME: str = "CYMATIC LLM Router"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    LLM_ROUTER_HOST: str = "0.0.0.0"
    LLM_ROUTER_PORT: int = 8001

    # Redis DB split: 1 cache, 2 usage, 3 rate
    REDIS_URL: str = "redis://localhost:6379/1"
    REDIS_CACHE_URL: str | None = None
    REDIS_USAGE_URL: str | None = None
    REDIS_RATE_URL: str | None = None
    REDIS_PASSWORD: str = ""

    # Provider API Keys
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    NVIDIA_NIM_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    SARVAM_API_KEY: str = ""
    APINEX_API_KEY: str = ""
    APINEX_BASE_URL: str = "https://api.apinex.bond/v1"

    # Default Models
    DEFAULT_FAST_MODEL: str = "llama-3.1-8b-instant"
    DEFAULT_STRONG_MODEL: str = "gpt-4o-mini"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"
    DEFAULT_STT_PROVIDER: str = "sarvam"
    DEFAULT_TTS_PROVIDER: str = "sarvam"

    # Offline <3B SLM via Ollama sidecar (feature-flagged, default off for cloud CI).
    # LAN compose with `--profile local` sets ENABLE_LOCAL_LLM=true and starts ollama.
    ENABLE_LOCAL_LLM: bool = False
    OLLAMA_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "phi-3-mini-3.8b-q4"
    LOCAL_LLM_CONTEXT: int = 4096

    # Provider Config (can be loaded from YAML)
    PROVIDER_CONFIGS: dict[str, Any] = Field(default_factory=dict)

    # Admin API key for management endpoints
    ADMIN_API_KEY: str = ""

    # Rate Limiting
    RATE_LIMIT_LLM: str = "50/minute"

    # CORS
    # NoDecode: pydantic-settings otherwise tries to JSON-parse list-typed env
    # vars before validators run, which rejects a plain comma-separated string.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v not in ("development", "staging", "production"):
            raise ValueError("ENVIRONMENT must be development, staging, or production")
        return v

    @field_validator("DEBUG")
    @classmethod
    def validate_debug(cls, v: bool, info: Any) -> bool:
        env = info.data.get("ENVIRONMENT") if hasattr(info, "data") else None
        if env == "production" and v is True:
            raise ValueError("DEBUG must be False in production")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v.upper()

    @field_validator(
        "REDIS_URL", "REDIS_CACHE_URL", "REDIS_USAGE_URL", "REDIS_RATE_URL"
    )
    @classmethod
    def validate_redis_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v and not (
            v.startswith("redis://")
            or v.startswith("rediss://")
            or v.startswith("redis+")
        ):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")
        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("CORS_ORIGINS must not be empty")
        for origin in v:
            if origin == "*":
                raise ValueError(
                    "CORS_ORIGINS wildcard '*' not allowed with allow_credentials"
                )
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise ValueError(
                    f"CORS origin must start with http:// or https://: {origin}"
                )
        return v

    @field_validator("RATE_LIMIT_LLM")
    @classmethod
    def validate_rate_limit(cls, v: str) -> str:
        if "/" not in v:
            raise ValueError("RATE_LIMIT_LLM must be in format 'count/period'")
        count, period = v.split("/", 1)
        try:
            int(count)
        except ValueError as e:
            raise ValueError("RATE_LIMIT_LLM count must be integer") from e
        if period.strip() not in ("second", "minute", "hour", "day"):
            raise ValueError("RATE_LIMIT_LLM period must be second/minute/hour/day")
        return v

    @field_validator(
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "NVIDIA_NIM_API_KEY",
        "OPENAI_API_KEY",
        "SARVAM_API_KEY",
        "APINEX_API_KEY",
    )
    @classmethod
    def validate_provider_key(cls, v: str) -> str:
        if v and v.strip() != v:
            raise ValueError(
                "Provider API key must not have leading/trailing whitespace"
            )
        if v and len(v) < 8 and v != "":
            raise ValueError("Provider API key too short")
        return v

    @field_validator("REDIS_PASSWORD")
    @classmethod
    def validate_redis_password(cls, v: str, info: Any) -> str:
        env = info.data.get("ENVIRONMENT") if hasattr(info, "data") else None
        if env == "production" and (not v or v in ("cymatic_redis_pass", "password")):
            raise ValueError("REDIS_PASSWORD must be set in production")
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
