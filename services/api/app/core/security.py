from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
import redis.asyncio as aioredis
import asyncio
import uuid
import structlog
from redis.exceptions import RedisError
from app.core.config import get_settings

logger = structlog.get_logger()

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_revoked_tokens_key = "cymatic:revoked_tokens"

_redis_client: Optional[aioredis.Redis] = None
_redis_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_redis_url() -> str:
    # Use dedicated revoked DB (4) if configured, fallback to REDIS_URL (3)
    revoked = getattr(settings, "REDIS_REVOKED_URL", None)
    if isinstance(revoked, str) and revoked:
        return revoked
    return settings.REDIS_URL


async def _get_redis() -> aioredis.Redis:
    global _redis_client, _redis_loop
    current_loop = asyncio.get_running_loop()
    if _redis_client is None or _redis_loop is not current_loop:
        _redis_client = aioredis.from_url(_get_redis_url(), decode_responses=True)
        _redis_loop = current_loop
    return _redis_client


def _extract_jti(token: str) -> str | None:
    try:
        claims = jwt.get_unverified_claims(token)
        jti = claims.get("jti")
        if isinstance(jti, str) and jti:
            return jti
    except JWTError:
        pass
    except Exception:
        pass
    # Fallback: hash token to avoid storing full JWT (which may contain PII)
    # Use first 32 chars of token as fallback key fragment, but prefer jti
    try:
        # Deterministic fallback without leaking full token
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()[:32]
    except Exception:
        return None


async def revoke_token(token: str, ttl_seconds: int = 604800) -> None:
    """Mark a token as revoked by jti (not full JWT) with TTL."""
    jti = _extract_jti(token)
    if not jti:
        logger.warning("revoke_token_no_jti", token_prefix=token[:16])
        return
    r = await _get_redis()
    await r.setex(f"{_revoked_tokens_key}:{jti}", ttl_seconds, "1")


async def is_token_revoked(token: str) -> bool:
    """Check if a token's jti has been revoked."""
    jti = _extract_jti(token)
    if not jti:
        return False
    try:
        r = await _get_redis()
        return bool(await r.exists(f"{_revoked_tokens_key}:{jti}"))
    except RedisError as e:
        logger.warning("redis_revocation_check_failed", error=str(e))
        return False
    except Exception as e:
        logger.warning("revocation_check_failed", error=str(e))
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire, "type": "access", "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )
    to_encode.update({"exp": expire, "type": "refresh", "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        raise ValueError("Invalid token")
