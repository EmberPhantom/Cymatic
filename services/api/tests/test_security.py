from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    is_token_revoked,
)


def test_access_and_refresh_tokens_have_distinct_types():
    access = decode_token(create_access_token({"sub": "1"}))
    refresh = decode_token(create_refresh_token({"sub": "1"}))

    assert access["type"] == "access"
    assert refresh["type"] == "refresh"


def test_expired_token_is_rejected():
    token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))

    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(token)


@pytest.mark.asyncio
async def test_revocation_transport_error_fails_closed():
    """Redis down must deny rather than admit (stolen tokens stay dead)."""
    token = create_access_token({"sub": "1"})
    broken = AsyncMock()
    broken.exists.side_effect = RedisError("down")
    with patch("app.core.security._get_redis", return_value=broken):
        assert await is_token_revoked(token) is True


@pytest.mark.asyncio
async def test_revocation_unexpected_error_fails_closed():
    """Unknown revocation-check state denies rather than admits."""
    token = create_access_token({"sub": "1"})
    broken = AsyncMock()
    broken.exists.side_effect = RuntimeError("weird")
    with patch("app.core.security._get_redis", return_value=broken):
        assert await is_token_revoked(token) is True


@pytest.mark.asyncio
async def test_revoked_token_detected():
    from app.core.security import revoke_token

    token = create_access_token({"sub": "1"})
    await revoke_token(token)
    assert await is_token_revoked(token) is True
