"""Integration tests for transactional outbox relay worker."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import AsyncSessionFactory
from app.core.redis import check_redis, get_redis, order_channel
from app.models.outbox_event import OutboxEvent
from app.workers.outbox_relay import process_outbox_batch

pytestmark = pytest.mark.integration


async def test_process_outbox_batch_relays_events_to_redis(
    integration_engine: AsyncEngine,
):
    if not await check_redis():
        pytest.skip("Redis server is not available")

    redis_client = get_redis()
    order_id = uuid4()
    channel_name = order_channel(order_id)

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel_name)
    # Wait for the subscription confirmation message so Redis registers the subscriber
    confirm = await pubsub.get_message(timeout=1.0)
    assert confirm is not None and confirm.get("type") == "subscribe"

    async with AsyncSessionFactory(bind=integration_engine) as session:
        event = OutboxEvent(
            aggregate_type="order",
            aggregate_id=order_id,
            event_type="order.created",
            payload={"order_id": str(order_id), "status": "confirmed", "total_minor": 5000},
        )
        session.add(event)
        await session.commit()

        # Run relay processor
        processed = await process_outbox_batch(session, redis_client=redis_client, batch_size=10)
        assert processed >= 1

        # Verify event was marked published
        refreshed_event = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.id == event.id)
        )
        assert refreshed_event is not None
        assert refreshed_event.published_at is not None
        assert refreshed_event.last_error is None

    # Listen on Redis pubsub to verify broadcast
    # First message is subscription confirmation
    msg1 = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0)
    assert msg1 is not None
    assert msg1["type"] == "message"
    assert "order.created" in msg1["data"]

    await pubsub.unsubscribe(channel_name)
    await pubsub.aclose()
