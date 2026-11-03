"""Integration tests for compliance and KYC REST endpoints."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory, get_db
from app.core.security import create_access_token, hash_refresh_token
from app.main import app
from app.models.address import CustomerAddress
from app.models.auth import AuthSession, User
from app.models.compliance import StateAlcoholRegulation
from app.models.orders import Order
from app.modules.compliance.service import create_delivery_compliance_log

pytestmark = pytest.mark.integration


@pytest.fixture
async def comp_client(integration_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
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
            email=f"comp-api-{user_id}@example.com",
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


async def test_kyc_submission_and_retrieval_api(
    integration_engine: AsyncEngine,
    comp_client: AsyncClient,
):
    user, token = await _create_test_user_and_token(integration_engine)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Check initially empty KYC
    get_res = await comp_client.get("/api/v1/compliance/kyc", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json() is None

    # 2. Submit adult KYC (born in 2000 -> age > 21)
    payload = {
        "id_type": "aadhaar",
        "id_number": "987654321012",
        "date_of_birth": "2000-01-15",
    }
    submit_res = await comp_client.post("/api/v1/compliance/kyc", json=payload, headers=headers)
    assert submit_res.status_code == 200
    data = submit_res.json()
    assert data["customer_id"] == str(user.id)
    assert data["id_type"] == "aadhaar"
    assert data["id_number_last4"] == "1012"
    assert data["verified_age"] >= 21
    assert data["status"] == "verified"

    # 3. Retrieve confirmed KYC
    get_res2 = await comp_client.get("/api/v1/compliance/kyc", headers=headers)
    assert get_res2.status_code == 200
    assert get_res2.json()["status"] == "verified"


async def test_state_regulations_api(
    integration_engine: AsyncEngine,
    comp_client: AsyncClient,
):
    state_code = "GA"
    async with AsyncSessionFactory(bind=integration_engine) as session:
        await session.execute(
            delete(StateAlcoholRegulation).where(StateAlcoholRegulation.state_code == state_code)
        )
        reg = StateAlcoholRegulation(
            state_code=state_code,
            state_name="Goa",
            minimum_legal_drinking_age=18,
            operating_hours_start=time(9, 0),
            operating_hours_end=time(23, 0),
            max_spirits_litres_per_order=Decimal("12.00"),
            delivery_handover_otp_required=True,
        )
        session.add(reg)
        await session.commit()

    res = await comp_client.get(f"/api/v1/compliance/regulations/{state_code}")
    assert res.status_code == 200
    data = res.json()
    assert data["state_code"] == "GA"
    assert data["state_name"] == "Goa"
    assert data["minimum_legal_drinking_age"] == 18
    assert data["delivery_handover_otp_required"] is True


async def test_delivery_handover_verification_api(
    integration_engine: AsyncEngine,
    comp_client: AsyncClient,
):
    user, token = await _create_test_user_and_token(integration_engine)
    headers = {"Authorization": f"Bearer {token}"}

    order_id = uuid4()
    address_id = uuid4()

    async with AsyncSessionFactory(bind=integration_engine) as session:
        session.add(
            CustomerAddress(
                id=address_id,
                user_id=user.id,
                label="home",
                recipient_name="Tester",
                line1="Road 1",
                city="Mumbai",
                state="MH",
                postal_code="400001",
                country_code="IN",
                is_active=True,
            )
        )
        session.add(
            Order(
                id=order_id,
                user_id=user.id,
                address_id=address_id,
                status="confirmed",
                currency_code="INR",
                subtotal_minor=5000,
                tax_minor=1000,
                delivery_fee_minor=2900,
                total_minor=8900,
            )
        )
        await session.flush()
        log = await create_delivery_compliance_log(session, order_id=order_id, customer_id=user.id)
        await session.commit()
        otp = log.handover_otp

    # 1. Invalid OTP returns 400
    res_bad = await comp_client.post(
        f"/api/v1/compliance/orders/{order_id}/verify-handover",
        json={"order_id": str(order_id), "handover_otp": "000000", "recipient_age_confirmed": True},
        headers=headers,
    )
    assert res_bad.status_code == 400
    assert res_bad.json()["error"]["code"] == "invalid_handover_otp"

    # 2. Valid OTP returns 200 and confirms handover
    res_good = await comp_client.post(
        f"/api/v1/compliance/orders/{order_id}/verify-handover",
        json={"order_id": str(order_id), "handover_otp": otp, "recipient_age_confirmed": True},
        headers=headers,
    )
    assert res_good.status_code == 200
    data = res_good.json()
    assert data["order_id"] == str(order_id)
    assert data["handover_otp_verified"] is True
    assert data["recipient_age_verified"] is True
