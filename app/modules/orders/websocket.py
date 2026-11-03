"""Real-time order tracking WebSocket endpoints backed by Redis Pub/Sub."""

import asyncio
import contextlib
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.exceptions import InvalidAccessToken
from app.core.redis import get_redis, order_channel
from app.core.security import decode_access_token
from app.models.auth import AuthSession, User
from app.models.delivery import Delivery
from app.models.orders import Order

logger = logging.getLogger(__name__)

router = APIRouter(tags=["order-tracking"])


async def _authenticate_ws(token: str, session: AsyncSession) -> User | None:
    """Validate bearer token from WebSocket handshake query param."""
    try:
        claims = decode_access_token(token)
    except InvalidAccessToken:
        return None

    user = await session.scalar(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            User.id == claims.subject,
            User.is_active.is_(True),
            AuthSession.id == claims.session_id,
            AuthSession.revoked_at.is_(None),
        )
    )
    return user


async def _get_order_snapshot(order_id: UUID, user_id: UUID, session: AsyncSession) -> dict | None:
    """Fetch the initial order and delivery state snapshot."""
    order = await session.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    if order is None:
        return None

    delivery = await session.scalar(
        select(Delivery)
        .where(Delivery.order_id == order_id)
        .options(selectinload(Delivery.courier))
    )

    delivery_data = None
    if delivery:
        delivery_data = {
            "id": str(delivery.id),
            "status": delivery.status,
            "tracking_number": delivery.tracking_number,
            "tracking_url": delivery.tracking_url,
            "estimated_delivery_at": (
                delivery.estimated_delivery_at.isoformat()
                if delivery.estimated_delivery_at
                else None
            ),
            "courier": (
                {
                    "name": delivery.courier.name,
                    "phone": delivery.courier.phone,
                    "vehicle_type": delivery.courier.vehicle_type,
                    "current_lat": delivery.courier.current_lat,
                    "current_lng": delivery.courier.current_lng,
                }
                if delivery.courier
                else None
            ),
        }

    return {
        "type": "order.snapshot",
        "data": {
            "order_id": str(order.id),
            "status": order.status,
            "payment_status": order.payment_status,
            "currency_code": order.currency_code,
            "total_minor": order.total_minor,
            "delivery": delivery_data,
        },
    }


@router.websocket("/orders/{order_id}/live")
async def order_live_tracking_ws(
    websocket: WebSocket,
    order_id: UUID,
    token: str = Query(..., description="Customer JWT access token"),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> None:
    """Live WebSocket stream for real-time order and delivery updates.

    Emits:
    - Initial `order.snapshot` upon connection.
    - Real-time Redis Pub/Sub events on `orders:{order_id}` as status changes.
    """
    user = await _authenticate_ws(token, session)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    snapshot = await _get_order_snapshot(order_id, user.id, session)
    if snapshot is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # Send initial snapshot
    await websocket.send_text(json.dumps(snapshot))

    pubsub = redis.pubsub()
    channel_name = order_channel(order_id)
    await pubsub.subscribe(channel_name)

    async def _redis_forwarder() -> None:
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    data = message.get("data")
                    if isinstance(data, (str, bytes)):
                        await websocket.send_text(
                            data if isinstance(data, str) else data.decode("utf-8")
                        )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("ws_redis_forwarder_error", extra={"error": str(exc)})

    forwarder_task = asyncio.create_task(_redis_forwarder())

    try:
        while True:
            # Keep receiving client heartbeats or messages
            client_msg = await websocket.receive_text()
            if client_msg.strip() == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except (WebSocketDisconnect, ConnectionResetError):
        pass
    finally:
        forwarder_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await forwarder_task
        await pubsub.unsubscribe(channel_name)
        await pubsub.aclose()
