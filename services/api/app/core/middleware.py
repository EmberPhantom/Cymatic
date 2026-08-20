import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert
from app.db.session import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User
import structlog

logger = structlog.get_logger()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware to add correlation ID to all requests for distributed tracing."""
    
    def __init__(self, app, header_name: str = "X-Correlation-ID"):
        super().__init__(app)
        self.header_name = header_name
    
    async def dispatch(self, request: Request, call_next):
        # Get or generate correlation ID
        correlation_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        # Bind correlation ID to logger context
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log request completion
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time_ms=round(process_time * 1000, 2),
        )
        
        # Clear context vars
        structlog.contextvars.clear_contextvars()
        
        return response


class TenantScopingMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce tenant scoping on all requests."""
    
    # Paths that don't require tenant scoping
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
        # Skip tenant scoping for exempt paths
        if request.url.path in self.EXEMPT_PATHS or request.url.path.startswith("/static"):
            return await call_next(request)
        
        # Tenant scoping is enforced at the dependency level (get_current_user)
        # This middleware adds request ID and timing
        request.state.request_id = str(uuid.uuid4())
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Process-Time"] = str(process_time)
        
        return response


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log important actions for audit trail."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Only audit successful mutating requests
        if request.method in ("POST", "PATCH", "DELETE", "PUT") and response.status_code < 400:
            await self._log_audit(request, response)
        
        return response
    
    async def _log_audit(self, request: Request, response: Response):
        try:
            # Get user from request state (set by auth dependency)
            user_id = getattr(request.state, "user_id", None)
            org_id = getattr(request.state, "organization_id", None)
            
            if not user_id or not org_id:
                return
            
            # Determine action
            action = self._determine_action(request.method, request.url.path)
            if not action:
                return
            
            # Extract resource info
            resource_type, resource_id = self._extract_resource(request.url.path)
            
            async with AsyncSessionLocal() as db:
                audit_log = AuditLog(
                    organization_id=org_id,
                    actor_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    metadata_json={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "correlation_id": getattr(request.state, "correlation_id", None),
                    }
                )
                db.add(audit_log)
                await db.commit()
                
        except Exception as e:
            logger.warning("audit_log_failed", error=str(e))
    
    def _determine_action(self, method: str, path: str) -> str | None:
        if method == "POST" and path.startswith("/v1/projects/"):
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
            resource_type = parts[1].rstrip("s")  # projects -> project
            try:
                resource_id = int(parts[2])
                return resource_type, resource_id
            except (ValueError, IndexError):
                return resource_type, None
        return None, None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to add request context to state."""
    
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return await call_next(request)