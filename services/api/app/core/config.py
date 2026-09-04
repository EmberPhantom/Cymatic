from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

_ENV_FILE = str(Path(__file__).resolve().parents[3] / ".env")


class Settings(BaseSettings):
    # App
    APP_NAME: str = "CYMATIC API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 4
    API_RELOAD: bool = False

    # Database
    DATABASE_URL: str = "postgresql://cymatic:cymatic@localhost:5432/cymatic"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO / S3
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "cymatic"
    S3_REGION: str = "us-east-1"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM Router
    LLM_ROUTER_URL: str = "http://localhost:8001"

    # Streaming
    RENDER_SERVER_URL: str = "http://localhost:8080"
    SIGNALING_URL: str = "ws://localhost:8000/v1/stream"
    STUN_URL: str = "stun:stun.l.google.com:19302"
    TURN_URL: str = ""
    TURN_USERNAME: str = ""
    TURN_PASSWORD: str = ""

    # Feature Flags
    ENABLE_HAND_TRACKING: bool = False
    ENABLE_UVC_CAMERA: bool = False
    ENABLE_VOICE: bool = True
    ENABLE_HERITAGE_TEMPLATES: bool = True
    ENABLE_ADAPTIVE_STREAMING: bool = True
    ENABLE_MANUAL_EDITING: bool = False
    ENABLE_MULTIPLAYER: bool = False

    # Rate Limiting (requests per minute)
    RATE_LIMIT_AUTH: str = "100/minute"
    RATE_LIMIT_API: str = "1000/minute"
    RATE_LIMIT_LLM: str = "50/minute"

    ADMIN_API_KEY: str = ""

    # CORS
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if v == "your-super-secret-jwt-key-change-in-production":
            raise ValueError("JWT_SECRET_KEY must be changed in production")
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v not in ("development", "staging", "production"):
            raise ValueError("ENVIRONMENT must be development, staging, or production")
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
