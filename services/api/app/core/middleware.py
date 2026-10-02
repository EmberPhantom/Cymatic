import asyncio
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import structlog

logger = structlog.get_logger()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware to add correlation ID to all requests for distributed tracing."""

    def __init__(self, app, header_name: str = "X-Correlation-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time"] = str(process_time)
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time_ms=round(process_time * 1000, 2),
        )
        structlog.contextvars.clear_contextvars()
        return response


class TenantScopingMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce tenant scoping on all requests."""

    EXEMPT_PATHS = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/v1/auth/login",
        "/v1/auth/register",
        "/v1/auth/refresh",
    }

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS or request.url.path.startswith(
            "/static"
        ):
            return await call_next(request)
        request.state.request_id = str(uuid.uuid4())
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Process-Time"] = str(process_time)
        return response


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log important actions for audit trail.

    Uses background task to avoid holding DB connections per request and
    to not block response. Only schedules audit for successful mutating requests
    with authenticated user context.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Only audit successful mutating requests; schedule in background
        if (
            request.method in ("POST", "PATCH", "DELETE", "PUT")
            and response.status_code < 400
        ):
            # Don't await — fire and forget, handle errors inside
            # Capture needed request state to avoid race
            user_id = getattr(request.state, "user_id", None)
            org_id = getattr(request.state, "organization_id", None)
            if user_id and org_id:
                action = self._determine_action(request.method, request.url.path)
                if action:
                    # Schedule without blocking response
                    correlation_id = getattr(request.state, "correlation_id", None)
                    asyncio.create_task(
                        self._log_audit_bg(
                            user_id=user_id,
                            org_id=org_id,
                            method=request.method,
                            path=request.url.path,
                            status_code=response.status_code,
                            correlation_id=correlation_id,
                            action=action,
                        )
                    )
        return response

    async def _log_audit_bg(
        self,
        *,
        user_id: int | str,
        org_id: int | str,
        method: str,
        path: str,
        status_code: int,
        correlation_id: str | None,
        action: str,
    ):
        # Lazy import to avoid circular deps and to allow session to be mocked in tests
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.audit_log import AuditLog

            resource_type, resource_id = self._extract_resource(path)
            async with AsyncSessionLocal() as db:
                audit_log = AuditLog(
                    organization_id=org_id,
                    actor_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    metadata_json={
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "correlation_id": correlation_id,
                    },
                )
                db.add(audit_log)
                await db.commit()
        except (OSError, ValueError) as e:
            logger.warning("audit_log_failed", error=str(e))
        except Exception as e:
            logger.warning("audit_log_unexpected", error=str(e))

    def _determine_action(self, method: str, path: str) -> str | None:
        if method == "POST" and (
            path.startswith("/v1/projects/") or path == "/v1/projects"
        ):
            if "/generate-spec" in path:
                return "spec_generated"
            if "/generate-scene" in path:
                return "scene_generated"
            if "/publish" in path:
                return "scene_published"
            if path == "/v1/projects":
                return "project_created"
            return None
        if method == "PATCH" and path.startswith("/v1/projects/"):
            return "project_updated"
        if method == "DELETE" and path.startswith("/v1/projects/"):
            return "project_deleted"
        if method == "POST" and path == "/v1/stream/sessions":
            return "stream_session_started"
        if method == "POST" and path == "/v1/assets/upload":
            return "asset_uploaded"
        if method == "POST" and path == "/v1/auth/register":
            return "user_registered"
        if method == "POST" and path == "/v1/users/invite":
            return "user_invited"
        return None

    def _extract_resource(self, path: str) -> tuple[str | None, int | None]:
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "v1":
            resource_type = parts[1].rstrip("s")
            try:
                resource_id = int(parts[2])
                return resource_type, resource_id
            except (ValueError, IndexError):
                return resource_type, None
        return None, None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to add request context to state."""

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = getattr(
            request.state, "request_id", str(uuid.uuid4())
        )
        return await call_next(request)
