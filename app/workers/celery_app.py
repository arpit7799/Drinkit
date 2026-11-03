"""Celery application configuration and periodic background tasks."""

import asyncio

from celery import Celery

from app.core.config import get_settings
from app.core.database import AsyncSessionFactory
from app.core.redis import get_redis
from app.workers.outbox_relay import process_outbox_batch

settings = get_settings()

celery_app = Celery(
    "drinkit_workers",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="tasks.relay_outbox_events")
def relay_outbox_events_task(batch_size: int = 100) -> int:
    """Periodic Celery task to sweep and relay unpublished outbox events."""

    async def _run() -> int:
        async with AsyncSessionFactory() as session:
            count = await process_outbox_batch(session, get_redis(), batch_size=batch_size)
            return count

    return asyncio.run(_run())
