"""API router configuration."""

from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "Jira Analytics API",
        "docs": "/docs",
        "health": "/health",
    }


# Future: include sub-routers
# from app.api.endpoints import employees, projects, worklogs, sync, analytics, planning
# api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
# api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
# api_router.include_router(worklogs.router, prefix="/worklogs", tags=["worklogs"])
# api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
# api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
# api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
