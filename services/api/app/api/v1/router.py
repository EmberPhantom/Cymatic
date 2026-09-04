from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    organizations,
    users,
    projects,
    specs,
    assets,
    streaming,
    analytics,
    credits,
    editing,
    jobs,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    organizations.router, prefix="/organizations", tags=["organizations"]
)
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(specs.router, prefix="/projects", tags=["specs"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(streaming.router, prefix="/stream", tags=["streaming"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(credits.router, prefix="/credits", tags=["credits"])
api_router.include_router(editing.router, prefix="/projects", tags=["editing"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
