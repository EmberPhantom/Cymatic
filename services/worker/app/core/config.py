from functools import lru_cache
from pathlib import Path
from typing import Annotated, List, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode

_CONFIG_PATH = Path(__file__).resolve()
# services/worker/app/core/config.py is 4 levels below repo root;
# container image is rooted at /app with fewer parents. Compose injects
# env directly, so a missing container-local .env is valid.
_ENV_FILE = (
    str(_CONFIG_PATH.parents[4] / ".env") if len(_CONFIG_PATH.parents) > 4 else ".env"
)


class Settings(BaseSettings):
    APP_NAME: str = "CYMATIC Worker"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql://cymatic:cymatic@localhost:5432/cymatic"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Redis DB 0 = queue, 3 = rate, 5 = pubsub
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_RATE_URL: str | None = None
    REDIS_PUBSUB_URL: str | None = None
    REDIS_PASSWORD: str = ""

    POSTGRES_PASSWORD: str = "cymatic"

    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "cymatic"
    S3_REGION: str = "us-east-1"

    LLM_ROUTER_URL: str = "http://localhost:8001"
    # Default router timeout (s) wired as LLMRouterClient's default.
    # Per-agent overrides take precedence: intake 120s, clarification 180s,
    # cloud architect path uses this default, local SLM uses LOCAL_LLM_TIMEOUT.
    LLM_TIMEOUT: float = 60.0

    # Offline <3B SLM for spec generation (feature-flagged, default off).
    # LAN compose with `--profile local` sets ENABLE_LOCAL_LLM=true.
    # SLM inference on CPU takes 60-180s for a full spec (phi-3-mini q4 at
    # ~10-15 tok/s); the per-request timeout must cover it. Measured 140s
    # on first load (model warmup included) during 2026-09-10 tuning.
    ENABLE_LOCAL_LLM: bool = False
    LOCAL_LLM_TIMEOUT: float = 300.0

    # RESERVED, currently unused — kept for env compat. worker_loop
    # (app/main.py) is intentionally SERIAL: one job at a time, one process
    # (uvicorn --workers is pinned to 1 in the Dockerfile). A value here
    # does NOT create in-process parallelism and must NOT be used to fan out
    # uvicorn processes (each would run its own competing loop over the same
    # Redis queues). Reserved for a future semaphore-bounded multi-queue loop.
    # Scale today by running more worker containers.
    WORKER_CONCURRENCY: int = 4
    WORKER_QUEUES: str = "generation,spec,asset,analytics"

    # Checkpoint retention/guardrails (mirrors app/pipelines/checkpoint.py
    # env reads; settings exist so the knobs are validated/discoverable).
    # Stale checkpoints older than this are ignored and pruned on load.
    CHECKPOINT_TTL_HOURS: float = 24.0
    # Per-stage cap on serialized stage_outputs; oversize stages are stored
    # as a pointer/summary instead of the full payload.
    CHECKPOINT_MAX_STAGE_BYTES: int = 1_000_000

    # Worker-side LLM-call budget (see app/core/llm_client.py +
    # cymatic_shared.agents.llm_budget): bounded retries with exponential
    # backoff around router calls, plus a consecutive-failure circuit
    # breaker that pauses the loop instead of hammering a downed router.
    LLM_BUDGET_MAX_RETRIES: int = 3
    LLM_BUDGET_BACKOFF_BASE_S: float = 1.0
    LLM_BUDGET_MAX_CONSECUTIVE_FAILURES: int = 5
    LLM_BUDGET_COOLDOWN_S: float = 30.0

    ADMIN_API_KEY: str = ""
    RATE_LIMIT_API: str = "1000/minute"
    WORKER_JOB_TIMEOUT_SECONDS: int = 300
    # NoDecode: pydantic-settings otherwise tries to JSON-parse list-typed env
    # vars before validators run, which rejects a plain comma-separated string.
    CORS_ORIGINS: Annotated[List[str], NoDecode] = Field(
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
