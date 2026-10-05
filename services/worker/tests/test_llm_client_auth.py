"""Worker -> router auth: every LLM call must carry X-Api-Key.

Regression test: with ADMIN_API_KEY configured on the router, an unauthenticated
worker call gets 401 and generation can never succeed (found during SLM tuning).
"""

import httpx
import pytest

from cymatic_shared.agents.llm_client import LLMRouterClient


def _client_with_captured_headers(api_key: str):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.headers))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}}]},
        )

    client = LLMRouterClient(base_url="http://test-router:8001", api_key=api_key)
    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), timeout=5.0
    )
    return client, captured


def test_explicit_api_key_sent():
    client, captured = _client_with_captured_headers("secret-key")
    assert client._headers == {"X-Api-Key": "secret-key"}
    assert captured == {}  # nothing sent yet


def test_empty_api_key_sends_no_header():
    client, _ = _client_with_captured_headers("")
    assert client._headers == {}


@pytest.mark.asyncio
async def test_chat_completion_carries_api_key():
    client, captured = _client_with_captured_headers("secret-key")
    await client.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
    )
    assert captured.get("x-api-key") == "secret-key"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_without_key_still_calls():
    # Router without a configured key must still be reachable (503 path is
    # the router's decision, not the client's).
    client, captured = _client_with_captured_headers("")
    await client.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
    )
    assert "x-api-key" not in captured
    await client.close()
