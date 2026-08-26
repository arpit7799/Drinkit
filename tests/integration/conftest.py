"""Shared PostgreSQL integration fixtures."""

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database import Base
from app.models.outbox_event import OutboxEvent


@pytest_asyncio.fixture(scope="module")
async def integration_engine() -> AsyncEngine:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url_async,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError) as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as connection:
        await connection.execute(delete(OutboxEvent))
    await engine.dispose()
