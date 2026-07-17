"""
Application entry point.

Uses the application-factory pattern (`create_app()`) rather than a
bare module-level `app = FastAPI()` so that tests can construct fresh,
isolated app instances with overridden settings/dependencies.

Run locally with:
    uvicorn app.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler: runs startup logic, then shutdown logic on exit."""
    settings = get_settings()
    logger.info(
        "app_startup",
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
        debug=settings.DEBUG,
    )
    yield
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "CivicAI — AI-powered civic issue reporting platform. "
            "Citizens report infrastructure problems via photo; the platform "
            "detects the issue, captures location, and helps generate and "
            "send a complaint to the correct municipal authority."
        ),
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()