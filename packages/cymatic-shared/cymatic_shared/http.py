"""Shared outbound HTTP helpers. Single source for pool/timeout shapes."""
import httpx


def build_async_client(
    timeout_s: float = 30.0,
    connect_s: float = 5.0,
    max_keepalive: int = 20,
    max_connections: int = 50,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s, connect=connect_s),
        limits=httpx.Limits(
            max_keepalive_connections=max_keepalive,
            max_connections=max_connections,
        ),
    )


def admin_headers(admin_key: str) -> dict[str, str]:
    """Auth headers for service-to-service calls (empty when key unset)."""
    if admin_key:
        return {"X-Api-Key": admin_key}
    return {}
