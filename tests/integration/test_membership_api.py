"""Integration tests for Drinkit VIP membership HTTP endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory, get_db
from app.core.security import create_access_token, hash_refresh_token
from app.main import app
from app.models.auth import AuthSession, User

pytestmark = pytest.mark.integration


@pytest.fixture
async def vip_client(integration_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with AsyncSessionFactory(bind=integration_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def _create_test_user_and_token(
    integration_engine: AsyncEngine,
) -> tuple[User, str]:
    user_id = uuid4()
    session_id = uuid4()
    now = datetime.now(UTC)

    async with AsyncSessionFactory(bind=integration_engine) as session:
        user = User(
            id=user_id,
            email=f"vip-api-{user_id}@example.com",
            password_hash="$argon2id$v=19$m=1,t=1,p=1$test$test",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        auth_session = AuthSession(
            id=session_id,
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(uuid4().hex),
            token_family_id=uuid4(),
            expires_at=now + timedelta(days=30),
            last_used_at=now,
        )
        session.add(auth_session)
        await session.commit()

    token = create_access_token(user_id=user_id, session_id=session_id)
    return user, token


@pytest.mark.asyncio
async def test_membership_api_lifecycle(
    integration_engine: AsyncEngine,
    vip_client: AsyncClient,
) -> None:
    user, token = await _create_test_user_and_token(integration_engine)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a new VIP membership plan via API
    plan_code = f"VIP_TIER_{uuid4().hex[:6].upper()}"
    create_payload = {
        "code": plan_code,
        "name": "Drinkit VIP Tier",
        "description": "Unlimited deliveries above ₹199 and 2x Liver points",
        "duration_days": 30,
        "price_minor": 19900,
        "currency_code": "INR",
        "free_delivery_min_order_minor": 19900,
        "points_multiplier": "2.0",
        "priority_fulfillment": True,
        "is_active": True,
    }
    resp_create = await vip_client.post(
        "/api/v1/memberships/plans",
        json=create_payload,
        headers=headers,
    )
    assert resp_create.status_code == 201, resp_create.text
    plan_data = resp_create.json()
    assert plan_data["code"] == plan_code
    plan_id = plan_data["id"]

    # 2. Browse public active membership plans
    resp_plans = await vip_client.get("/api/v1/memberships/plans")
    assert resp_plans.status_code == 200
    plans = resp_plans.json()
    assert any(p["id"] == plan_id for p in plans)

    # 3. Check current membership before subscribing
    resp_me_empty = await vip_client.get("/api/v1/memberships/me", headers=headers)
    assert resp_me_empty.status_code == 200
    assert resp_me_empty.json() is None

    # Check savings summary for non-VIP
    resp_savings_before = await vip_client.get("/api/v1/memberships/savings", headers=headers)
    assert resp_savings_before.status_code == 200
    assert resp_savings_before.json()["is_vip"] is False
    assert resp_savings_before.json()["total_delivery_fees_saved_minor"] == 0

    # 4. Subscribe to plan
    subscribe_payload = {
        "plan_id": plan_id,
        "auto_renew": True,
        "payment_reference": "mock_rzp_order_9988",
    }
    resp_sub = await vip_client.post(
        "/api/v1/memberships/subscribe",
        json=subscribe_payload,
        headers=headers,
    )
    assert resp_sub.status_code == 200, resp_sub.text
    sub_data = resp_sub.json()
    assert sub_data["status"] == "active"
    assert sub_data["plan_id"] == plan_id
    assert sub_data["auto_renew"] is True

    # 5. Check /api/v1/memberships/me
    resp_me = await vip_client.get("/api/v1/memberships/me", headers=headers)
    assert resp_me.status_code == 200
    me_data = resp_me.json()
    assert me_data is not None
    assert me_data["status"] == "active"
    assert me_data["plan"]["code"] == plan_code

    # 6. Check /api/v1/memberships/savings
    resp_savings = await vip_client.get("/api/v1/memberships/savings", headers=headers)
    assert resp_savings.status_code == 200
    savings_data = resp_savings.json()
    assert savings_data["is_vip"] is True
    assert savings_data["active_plan_code"] == plan_code

    # 7. Cancel membership
    resp_cancel = await vip_client.post(
        "/api/v1/memberships/cancel",
        json={"reason": "Customer opted out"},
        headers=headers,
    )
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["status"] == "cancelled"

    # 8. Check /api/v1/memberships/me after cancellation
    resp_me_after = await vip_client.get("/api/v1/memberships/me", headers=headers)
    assert resp_me_after.status_code == 200
    assert resp_me_after.json() is None
