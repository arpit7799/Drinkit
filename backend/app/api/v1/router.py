"""
Aggregates all v1 endpoint routers into a single APIRouter.

As new endpoint modules are added in later phases (auth, reports,
users, email, admin, municipal), import and `include_router` them
here. This keeps `app/main.py` free of per-feature routing details.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health

api_router = APIRouter()

api_router.include_router(health.router)

# Phase 2+: api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# Phase 3+: api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
# Phase 5+: api_router.include_router(email.router, prefix="/email", tags=["email"])