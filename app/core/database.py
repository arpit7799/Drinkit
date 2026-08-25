"""SQLAlchemy 2.x engines, models, and transaction boundaries."""

from collections.abc import AsyncGenerator, AsyncIterator, Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Engine, MetaData, Uuid, create_engine, func, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by all Drinkit ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """Reusable UUIDv4 primary key for externally exposed aggregates.

    UUIDv4 avoids sequential identifiers leaking volume or being enumerable.
    IDs are generated in application memory, which keeps inserts portable and
    avoids requiring a PostgreSQL extension. UUIDv7 can be introduced later as
    a deliberate migration when the runtime and access patterns justify it.
    """

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TimestampMixin:
    """UTC, timezone-aware timestamps for records that have lifecycle time."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BaseModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Default model base; opt out by inheriting from ``Base`` directly."""

    __abstract__ = True


settings = get_settings()

async_engine: AsyncEngine = create_async_engine(
    settings.database_url_async,
    echo=settings.sql_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=settings.db_pool_pre_ping,
)

AsyncSessionFactory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

sync_engine: Engine | None = None
SyncSessionFactory = sessionmaker(expire_on_commit=False, autoflush=False)


def get_sync_engine() -> Engine:
    """Lazily create the synchronous engine used by Alembic and Celery."""
    global sync_engine
    if sync_engine is None:
        sync_engine = create_engine(
            settings.database_url_sync,
            echo=settings.sql_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=settings.db_pool_pre_ping,
        )
    return sync_engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one request-scoped session without committing implicitly.

    Application services own transaction boundaries. This dependency only
    guarantees rollback on an exception and session closure after the request.
    """

    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Provide the standard service-owned transaction boundary."""

    async with session.begin():
        yield session


@contextmanager
def sync_session() -> Generator[Session, None, None]:
    """Yield a synchronous worker/migration session with rollback safety."""

    with SyncSessionFactory(bind=get_sync_engine()) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


async def check_database(engine: AsyncEngine | None = None) -> bool:
    """Return whether PostgreSQL accepts a trivial query."""

    active_engine = engine or async_engine
    try:
        async with active_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


async def dispose_engines() -> None:
    """Close pooled connections during application shutdown."""

    await async_engine.dispose()
    if sync_engine is not None:
        sync_engine.dispose()
