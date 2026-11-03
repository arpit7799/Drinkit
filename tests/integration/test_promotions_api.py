"""Integration tests for promotions, coupon validation, and Liver Points APIs."""

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
from app.models.promotions_tax import LoyaltyAccount

pytestmark = pytest.mark.integration


@pytest.fixture
async def promo_client(integration_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
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
            email=f"promo-api-{user_id}@example.com",
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


async def test_promotions_coupon_lifecycle_endpoints(
    integration_engine: AsyncEngine,
    promo_client: AsyncClient,
):
    user, token = await _create_test_user_and_token(integration_engine)
    headers = {"Authorization": f"Bearer {token}"}

    api_code = f"API20_{uuid4().hex[:6].upper()}"
    now = datetime.now(UTC)
    payload = {
        "code": api_code,
        "name": "API 20% Off",
        "description": "20% discount on order",
        "discount_type": "percentage",
        "discount_value": "20.00",
        "currency_code": "INR",
        "min_order_amount_minor": 1500,
        "max_discount_minor": 1000,
        "max_uses": 50,
        "max_uses_per_customer": 2,
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=7)).isoformat(),
    }

    # 1. Create coupon
    create_res = await promo_client.post(
        "/api/v1/promotions/coupons",
        json=payload,
        headers=headers,
    )
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["code"] == api_code
    assert created_data["status"] == "active"

    # 2. Get coupon by code
    get_res = await promo_client.get(
        f"/api/v1/promotions/coupons/{api_code}",
        headers=headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["code"] == api_code

    # 3. Validate coupon with valid subtotal: ₹50.00 (5000 minor units)
    # 20% of 5000 is 1000, capped at 1000 max_discount_minor
    val_res = await promo_client.post(
        "/api/v1/promotions/coupons/validate",
        json={"code": api_code, "cart_subtotal_minor": 5000},
        headers=headers,
    )
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["valid"] is True
    assert val_data["discount_applied_minor"] == 1000
    assert val_data["discounted_subtotal_minor"] == 4000

    # 4. Validate coupon below min order requirement: ₹10.00 (1000 minor < 1500 min)
    min_fail_res = await promo_client.post(
        "/api/v1/promotions/coupons/validate",
        json={"code": api_code, "cart_subtotal_minor": 1000},
        headers=headers,
    )
    assert min_fail_res.status_code == 400
    assert min_fail_res.json()["error"]["code"] == "coupon_min_order_not_met"


async def test_promotions_loyalty_endpoints(
    integration_engine: AsyncEngine,
    promo_client: AsyncClient,
):
    user, token = await _create_test_user_and_token(integration_engine)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed initial loyalty account with 150 points
    async with AsyncSessionFactory(bind=integration_engine) as session:
        account = LoyaltyAccount(
            customer_id=user.id,
            points_balance=150,
            lifetime_earned=150,
            tier="bronze",
        )
        session.add(account)
        await session.commit()

    # 1. Fetch loyalty balance
    res = await promo_client.get("/api/v1/promotions/loyalty", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["customer_id"] == str(user.id)
    assert data["points_balance"] == 150
    assert data["tier"] == "bronze"
    assert data["point_value_minor"] == 100

    # 2. Estimate discount value: 50 points -> ₹50.00 (5000 minor units)
    est_res = await promo_client.post(
        "/api/v1/promotions/loyalty/estimate",
        json={"points": 50},
        headers=headers,
    )
    assert est_res.status_code == 200
    est_data = est_res.json()
    assert est_data["points"] == 50
    assert est_data["discount_value_minor"] == 5000
    assert est_data["available_balance"] == 150

    # 3. View loyalty transactions history
    tx_res = await promo_client.get(
        "/api/v1/promotions/loyalty/transactions",
        headers=headers,
    )
    assert tx_res.status_code == 200
    assert isinstance(tx_res.json(), list)
