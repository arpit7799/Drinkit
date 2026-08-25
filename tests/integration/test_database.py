from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database import AsyncSessionFactory, Base, check_database
from app.models.outbox_event import OutboxEvent

pytestmark = pytest.mark.integration


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
        table_exists = await connection.scalar(text("SELECT to_regclass('public.outbox_events')"))
        if table_exists is None:
            await connection.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as connection:
        await connection.execute(delete(OutboxEvent))
    await engine.dispose()


@pytest_asyncio.fixture
async def session(integration_engine: AsyncEngine) -> AsyncSession:
    async with AsyncSessionFactory(bind=integration_engine) as db_session:
        yield db_session
        await db_session.rollback()
        await db_session.execute(delete(OutboxEvent))
        await db_session.commit()


async def test_database_health_check_uses_postgresql(integration_engine: AsyncEngine):
    assert await check_database(integration_engine) is True


async def test_session_transaction_rolls_back_on_failure(session: AsyncSession):
    event_id = uuid4()

    with pytest.raises(RuntimeError, match="force rollback"):
        async with session.begin():
            session.add(
                OutboxEvent(
                    id=event_id,
                    aggregate_type="test",
                    aggregate_id=uuid4(),
                    event_type="TestEvent",
                    payload={"value": 1},
                )
            )
            await session.flush()
            raise RuntimeError("force rollback")

    result = await session.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id))
    assert result is None


async def test_outbox_event_constraints_are_enforced_by_postgresql(session: AsyncSession):
    event = OutboxEvent(
        aggregate_type="test",
        aggregate_id=uuid4(),
        event_type="TestEvent",
        payload={"value": 1},
        attempts=-1,
    )
    session.add(event)

    with pytest.raises(SQLAlchemyError):
        await session.commit()

    await session.rollback()
