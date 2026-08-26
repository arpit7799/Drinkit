from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.database import AsyncSessionFactory, get_db
from app.main import app
from app.models.auth import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def auth_client(integration_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
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
        async with AsyncSessionFactory(bind=integration_engine) as session:
            await session.execute(delete(User))
            await session.commit()


async def test_register_login_me_and_refresh_rotation(auth_client: AsyncClient):
    registration = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "Alice@Example.COM",
            "password": "correct horse battery staple",
            "device": {"device_key": "alice-phone", "platform": "ios"},
        },
    )

    assert registration.status_code == 201
    tokens = registration.json()
    assert tokens["user"]["email"] == "alice@example.com"
    assert tokens["token_type"] == "bearer"

    me = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert UUID(me.json()["id"])

    refreshed = await auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    rotated = refreshed.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]

    old_access = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert old_access.status_code == 401

    reused = await auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reused.status_code == 401

    family_revoked = await auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated["refresh_token"]},
    )
    assert family_revoked.status_code == 401


async def test_duplicate_registration_and_invalid_login_are_safe(auth_client: AsyncClient):
    payload = {"email": "customer@example.com", "password": "safe password 123"}
    assert (await auth_client.post("/api/v1/auth/register", json=payload)).status_code == 201

    duplicate = await auth_client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_already_registered"

    invalid_login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "wrong password"},
    )
    assert invalid_login.status_code == 401
    assert invalid_login.json()["error"]["code"] == "invalid_credentials"


async def test_logout_revokes_refresh_token(auth_client: AsyncClient):
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": "logout@example.com", "password": "safe password 123"},
    )
    refresh_token = response.json()["refresh_token"]

    logout = await auth_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout.status_code == 204

    refreshed = await auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refreshed.status_code == 401


async def test_password_is_not_persisted_in_plaintext(
    auth_client: AsyncClient,
    integration_engine: AsyncEngine,
):
    password = "safe password 123"
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": "hash@example.com", "password": password},
    )
    user_id = UUID(response.json()["user"]["id"])

    async with AsyncSessionFactory(bind=integration_engine) as session:
        user = await session.scalar(select(User).where(User.id == user_id))

    assert user is not None
    assert user.password_hash != password
    assert user.password_hash.startswith("$argon2")
