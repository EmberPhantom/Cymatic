from datetime import timedelta

import pytest

from app.core.security import create_access_token, create_refresh_token, decode_token


def test_access_and_refresh_tokens_have_distinct_types():
    access = decode_token(create_access_token({"sub": "1"}))
    refresh = decode_token(create_refresh_token({"sub": "1"}))

    assert access["type"] == "access"
    assert refresh["type"] == "refresh"


def test_expired_token_is_rejected():
    token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))

    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(token)
