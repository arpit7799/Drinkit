"""Integration tests for live order tracking via WebSocket and Redis Pub/Sub."""

import asyncio
import json
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import redis
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.database import AsyncSessionFactory, get_db
from app.core.redis import order_channel
from app.core.security import create_access_token, hash_refresh_token
from app.main import app
from app.models.address import CustomerAddress
from app.models.auth import AuthSession, User
from app.models.orders import Order

pytestmark = pytest.mark.integration


@pytest.fixture
def ws_client(integration_engine) -> Generator[TestClient, None, None]:
    async def override_get_db() -> AsyncIterator:
        async with AsyncSessionFactory(bind=integration_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_test_order(
    integration_engine,
) -> tuple[User, AuthSession, Order, str]:
    user_id = uuid4()
    session_id = uuid4()
    address_id = uuid4()
    order_id = uuid4()

    now = datetime.now(UTC)
    async with AsyncSessionFactory(bind=integration_engine) as db_session:
        user = User(
            id=user_id,
            email=f"ws-track-{user_id}@example.com",
            password_hash="$argon2id$v=19$m=1,t=1,p=1$test$test",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        auth_session = AuthSession(
            id=session_id,
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(uuid4().hex),
            token_family_id=uuid4(),
            expires_at=now + timedelta(days=30),
            last_used_at=now,
        )
        db_session.add(auth_session)

        address = CustomerAddress(
            id=address_id,
            user_id=user_id,
            label="home",
            recipient_name="WS Tester",
            line1="100 Marine Drive",
            city="Mumbai",
            state="Maharashtra",
            postal_code="400020",
            country_code="IN",
            is_default=True,
            is_active=True,
        )
        db_session.add(address)

        order = Order(
            id=order_id,
            user_id=user_id,
            address_id=address_id,
            status="confirmed",
            currency_code="INR",
            subtotal_minor=2000,
            tax_minor=360,
            delivery_fee_minor=2900,
            total_minor=5260,
            payment_status="captured",
        )
        db_session.add(order)
        await db_session.commit()

    token = create_access_token(user_id=user_id, session_id=session_id)
    return user, auth_session, order, token


def test_websocket_tracking_snapshot_and_live_updates(integration_engine, ws_client):
    settings = get_settings()
    sync_redis = redis.Redis.from_url(settings.redis_url)
    try:
        sync_redis.ping()
    except Exception:
        pytest.skip("Redis server is not available")

    user, auth_session, order, token = asyncio.run(_seed_test_order(integration_engine))

    # 1. Test successful connection and snapshot reception
    with ws_client.websocket_connect(f"/api/v1/orders/{order.id}/live?token={token}") as ws:
        snapshot_raw = ws.receive_text()
        snapshot = json.loads(snapshot_raw)

        assert snapshot["type"] == "order.snapshot"
        assert snapshot["data"]["order_id"] == str(order.id)
        assert snapshot["data"]["status"] == "confirmed"
        assert snapshot["data"]["total_minor"] == 5260

        # Test heartbeat
        ws.send_text("ping")
        pong = json.loads(ws.receive_text())
        assert pong["type"] == "pong"

        # 2. Test publishing real-time live event through Redis
        live_event = {
            "event_type": "delivery.status_updated",
            "order_id": str(order.id),
            "status": "in_transit",
            "courier": {
                "name": "Ramesh",
                "phone": "+919876543210",
                "vehicle_type": "bike",
                "current_lat": 18.922,
                "current_lng": 72.834,
            },
        }
        sync_redis.publish(order_channel(order.id), json.dumps(live_event))

        # Client receives real-time broadcast
        received_raw = ws.receive_text()
        received = json.loads(received_raw)
        assert received["event_type"] == "delivery.status_updated"
        assert received["status"] == "in_transit"
        assert received["courier"]["name"] == "Ramesh"

    sync_redis.close()


def test_websocket_tracking_rejects_unauthorized_token(integration_engine, ws_client):
    settings = get_settings()
    sync_redis = redis.Redis.from_url(settings.redis_url)
    try:
        sync_redis.ping()
    except Exception:
        pytest.skip("Redis server is not available")
    finally:
        sync_redis.close()

    _, _, order, _ = asyncio.run(_seed_test_order(integration_engine))

    with (
        pytest.raises(WebSocketDisconnect) as exc,
        ws_client.websocket_connect(f"/api/v1/orders/{order.id}/live?token=invalid.jwt.token"),
    ):
        pass
    assert exc.value.code == 1008


def test_websocket_tracking_rejects_unowned_order(integration_engine, ws_client):
    settings = get_settings()
    sync_redis = redis.Redis.from_url(settings.redis_url)
    try:
        sync_redis.ping()
    except Exception:
        pytest.skip("Redis server is not available")
    finally:
        sync_redis.close()

    # Seed order for User A
    _, _, order, _ = asyncio.run(_seed_test_order(integration_engine))
    # Seed User B with their own token
    _, _, _, token_b = asyncio.run(_seed_test_order(integration_engine))

    # User B tries to listen to User A's order live stream
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        ws_client.websocket_connect(f"/api/v1/orders/{order.id}/live?token={token_b}"),
    ):
        pass
    assert exc.value.code == 1008
