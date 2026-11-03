"""Redis client connection pool, lifecycle, and pub/sub channels."""

import asyncio
import contextlib
import logging
from uuid import UUID

from redis.asyncio import ConnectionPool, Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_loop_id: int | None = None
_pool: ConnectionPool | None = None
_client: Redis | None = None


def get_redis_pool() -> ConnectionPool:
    """Lazily construct the global Redis connection pool."""
    global _pool, _loop_id
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    current_loop_id = id(current_loop) if current_loop is not None else None
    if _pool is None or _loop_id != current_loop_id:
        _loop_id = current_loop_id
        settings = get_settings()
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
    return _pool


def get_redis() -> Redis:
    """Return the shared asynchronous Redis client for the current loop."""
    global _client, _pool, _loop_id
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    current_loop_id = id(current_loop) if current_loop is not None else None
    if _client is None or _loop_id != current_loop_id:
        pool = get_redis_pool()
        _client = Redis(connection_pool=pool)
    return _client


async def close_redis() -> None:
    """Close the global Redis client and connection pool."""
    global _client, _pool, _loop_id
    if _client is not None:
        with contextlib.suppress(Exception):
            await _client.aclose()
        _client = None
    if _pool is not None:
        with contextlib.suppress(Exception):
            await _pool.disconnect()
        _pool = None
    _loop_id = None


async def check_redis(client: Redis | None = None) -> bool:
    """Return whether Redis accepts a ping command within a short timeout."""
    active_client = client or get_redis()
    try:
        return bool(await active_client.ping())
    except Exception as exc:
        logger.warning("redis_health_check_failed", extra={"error": str(exc)})
        return False


def order_channel(order_id: UUID) -> str:
    """Channel name for order-specific real-time tracking events."""
    return f"orders:{order_id}"


def user_orders_channel(user_id: UUID) -> str:
    """Channel name for user-level order notifications."""
    return f"users:{user_id}:orders"
