"""Unit tests for Redis connection pool and pub/sub channels."""

from uuid import uuid4

from app.core.redis import get_redis, get_redis_pool, order_channel, user_orders_channel


def test_redis_channel_naming_conventions():
    order_id = uuid4()
    user_id = uuid4()

    assert order_channel(order_id) == f"orders:{order_id}"
    assert user_orders_channel(user_id) == f"users:{user_id}:orders"


def test_redis_pool_initialization():
    pool = get_redis_pool()
    assert pool is not None

    client = get_redis()
    assert client is not None
