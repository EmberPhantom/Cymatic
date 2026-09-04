from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from app.core.config import get_settings
from app.core.middleware import (
    TenantScopingMiddleware,
    AuditLoggingMiddleware,
    RequestContextMiddleware,
    CorrelationIdMiddleware,
)
from app.db.session import init_db, close_db
from app.api.v1.router import api_router
import structlog
import logging
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Histogram

settings = get_settings()

# Structured logging init
if settings.LOG_FORMAT == "json":
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper(), 20)
        ),
    )

REQUEST_COUNT = Counter(
    "http_requests_total", "Total requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "Request latency", ["method", "path"]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup validation for required env vars
    if not settings.JWT_SECRET_KEY or len(settings.JWT_SECRET_KEY) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be set and >=32 chars")
    if (
        not settings.DATABASE_URL
        or "localhost" in settings.DATABASE_URL
        and settings.ENVIRONMENT == "production"
    ):
        raise RuntimeError("DATABASE_URL must be configured for production")
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="CYMATIC - AI Simulation Builder Platform API",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Add middleware (order matters - first added is outermost)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(TenantScopingMiddleware)
app.add_middleware(AuditLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    import traceback

    corr = getattr(request.state, "correlation_id", None) or request.headers.get(
        "X-Correlation-ID", "-"
    )
    structlog.get_logger().error(
        "unhandled_exception",
        correlation_id=corr,
        path=str(request.url),
        error=str(exc),
        traceback=traceback.format_exc(),
    )
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "Unexpected error",
            "instance": str(request.url),
            "correlation_id": corr,
        },
    )


@app.get("/health")
async def health_check():
    checks = {"status": "healthy", "api": "healthy", "version": settings.APP_VERSION}
    # DB check
    try:
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["db"] = "healthy"
    except Exception as e:
        checks["db"] = f"unhealthy: {e}"
        checks["status"] = "degraded"
        checks["api"] = "degraded"
    # Redis check
    try:
        from app.core.rate_limit import _get_redis

        r = _get_redis()
        if r is not None:
            await r.ping()
            checks["redis"] = "healthy"
        else:
            checks["redis"] = "unknown"
    except Exception as e:
        checks["redis"] = f"unhealthy: {e}"
        checks["status"] = "degraded"
    return checks


@app.get("/metrics")
async def metrics(x_api_key: str = Header(None)):
    if settings.ADMIN_API_KEY and x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.DEBUG else "disabled",
    }
