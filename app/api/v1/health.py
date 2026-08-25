"""Health endpoints distinguishing liveness from database readiness."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness() -> dict[str, str]:
    """Process liveness; intentionally does not require dependencies."""

    return {"status": "ok", "service": get_settings().app_name}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness(session: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Readiness requires a successful PostgreSQL connectivity check."""

    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "checks": {"postgres": "down"}},
        ) from exc

    return {"status": "ready", "checks": {"postgres": "up"}}
