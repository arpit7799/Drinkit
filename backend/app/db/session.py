"""
Database engine and session management.

We use SQLAlchemy 2.0's async engine (via `asyncpg`) for the FastAPI
application at request-time, and a separate synchronous engine URL is
used only by Alembic for migrations (Alembic's autogenerate does not
yet fully support async engines in a way that's worth the complexity
here).

Usage in an endpoint:

    from app.db.session import get_db

    @router.get("/reports")
    async def list_reports(db: AsyncSession = Depends(get_db)):
        ...
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG and not settings.is_production,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session and guarantees
    it is closed after the request, rolling back on any unhandled
    exception so a failed request never leaves a dangling transaction.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()