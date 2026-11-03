"""Transactional Outbox Relay Worker.

Polls unpublished events from `outbox_events` using PostgreSQL
`SELECT ... FOR UPDATE SKIP LOCKED` to allow safe, concurrent multi-worker
consumption without lock contention or duplicated messages. Broadcasts events
to Redis Pub/Sub channels for real-time WebSocket distribution.
"""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import transaction
from app.core.redis import get_redis, order_channel, user_orders_channel
from app.models.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)


async def publish_outbox_event(
    redis_client: Redis,
    event: OutboxEvent,
) -> int:
    """Publish a single outbox event to appropriate Redis Pub/Sub channels.

    Returns the number of subscribers that received the message.
    """
    message = json.dumps(
        {
            "event_id": str(event.id),
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
            "event_type": event.event_type,
            "payload": event.payload,
            "occurred_at": event.occurred_at.isoformat(),
        }
    )

    published_subscribers = 0

    # Order-specific channel
    if event.aggregate_type == "order":
        ch = order_channel(event.aggregate_id)
        subscribers = await redis_client.publish(ch, message)
        published_subscribers += subscribers

    # Delivery events associated with an order
    elif event.aggregate_type == "delivery" and "order_id" in event.payload:
        try:
            order_id = UUID(str(event.payload["order_id"]))
            ch = order_channel(order_id)
            subscribers = await redis_client.publish(ch, message)
            published_subscribers += subscribers
        except (ValueError, TypeError):
            pass

    # Customer user notifications channel
    if "user_id" in event.payload:
        try:
            user_id = UUID(str(event.payload["user_id"]))
            ch = user_orders_channel(user_id)
            subscribers = await redis_client.publish(ch, message)
            published_subscribers += subscribers
        except (ValueError, TypeError):
            pass

    return published_subscribers


async def process_outbox_batch(
    session: AsyncSession,
    redis_client: Redis | None = None,
    *,
    batch_size: int = 50,
) -> int:
    """Poll and publish a batch of unpublished outbox events atomically.

    Uses `FOR UPDATE SKIP LOCKED` so multiple relay worker processes or Celery
    tasks can process disjoint batches simultaneously without blocking.
    """
    client = redis_client or get_redis()
    processed_count = 0

    async with transaction(session):
        events = (
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.occurred_at.asc())
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()

        now = datetime.now(UTC)

        for event in events:
            try:
                await publish_outbox_event(client, event)
                event.published_at = now
                event.last_error = None
                processed_count += 1
            except Exception as exc:
                event.attempts += 1
                event.last_error = str(exc)
                logger.error(
                    "outbox_event_publish_failed",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "attempts": event.attempts,
                        "error": str(exc),
                    },
                )

        await session.flush()

    return processed_count
