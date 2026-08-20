from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.middleware import TenantScopingMiddleware, AuditLoggingMiddleware, RequestContextMiddleware, CorrelationIdMiddleware
from app.db.session import init_db, close_db
from app.api.v1.router import api_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.DEBUG else "disabled",
    }