"""Health check endpoints for readiness/liveness probes and monitoring."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(settings: Settings = Depends(get_settings)) -> dict:
    """Liveness probe: confirms the API process is up and responsive."""
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }


@router.get("/health/db", status_code=status.HTTP_200_OK)
async def health_check_db(db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness probe: confirms the API can actually reach the database."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}