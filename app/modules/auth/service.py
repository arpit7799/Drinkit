"""Authentication application workflows and session lifecycle."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import transaction
from app.core.exceptions import AuthConflict, InvalidCredentials, InvalidRefreshToken
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_password_rehash,
    verify_password,
    verify_unknown_user_password,
)
from app.models.auth import AuthSession, Device, User
from app.modules.auth.schemas import DeviceInput, LoginRequest, RegisterRequest


@dataclass(frozen=True)
class IssuedTokens:
    """Tokens returned after registration, login, or refresh rotation."""

    user: User
    access_token: str
    refresh_token: str
    expires_in: int


async def register_user(session: AsyncSession, request: RegisterRequest) -> IssuedTokens:
    """Create a user and its first session atomically."""

    password_hash = hash_password(request.password)
    try:
        async with transaction(session):
            existing = await session.scalar(select(User).where(User.email == request.email))
            if existing is not None:
                raise AuthConflict

            user = User(email=request.email, password_hash=password_hash)
            session.add(user)
            await session.flush()
            device = await _upsert_device(session, user.id, request.device)
            issued = await _issue_tokens(session, user, device)
    except IntegrityError as exc:
        raise AuthConflict from exc
    return issued


async def login_user(session: AsyncSession, request: LoginRequest) -> IssuedTokens:
    """Authenticate credentials and issue a new persisted refresh session."""

    async with transaction(session):
        user = await session.scalar(
            select(User).where(User.email == request.email).with_for_update()
        )
        if user is None:
            verify_unknown_user_password(request.password)
            raise InvalidCredentials
        if not user.is_active or not verify_password(request.password, user.password_hash):
            raise InvalidCredentials

        if needs_password_rehash(user.password_hash):
            user.password_hash = hash_password(request.password)
        user.last_login_at = datetime.now(UTC)
        device = await _upsert_device(session, user.id, request.device)
        issued = await _issue_tokens(session, user, device)
    return issued


async def refresh_session(session: AsyncSession, refresh_token: str) -> IssuedTokens:
    """Rotate a refresh token once and revoke a family on reuse detection."""

    token_hash = hash_refresh_token(refresh_token)
    now = datetime.now(UTC)
    issued: IssuedTokens | None = None
    invalid = False

    async with transaction(session):
        auth_session = await session.scalar(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == token_hash)
            .with_for_update()
        )
        if auth_session is None:
            invalid = True
        elif auth_session.revoked_at is not None:
            await session.execute(
                update(AuthSession)
                .where(
                    AuthSession.token_family_id == auth_session.token_family_id,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=now, updated_at=now)
            )
            invalid = True
        elif auth_session.expires_at <= now:
            auth_session.revoked_at = now
            invalid = True
        else:
            user = await session.scalar(select(User).where(User.id == auth_session.user_id))
            if user is None or not user.is_active:
                auth_session.revoked_at = now
                invalid = True
            else:
                auth_session.revoked_at = now
                auth_session.last_used_at = now
                new_session_id = uuid4()
                new_refresh_token = generate_refresh_token()
                replacement = AuthSession(
                    id=new_session_id,
                    user_id=auth_session.user_id,
                    device_id=auth_session.device_id,
                    refresh_token_hash=hash_refresh_token(new_refresh_token),
                    token_family_id=auth_session.token_family_id,
                    expires_at=now + timedelta(days=get_settings().refresh_token_expire_days),
                    last_used_at=now,
                )
                session.add(replacement)
                await session.flush()
                auth_session.replaced_by_session_id = new_session_id
                await session.flush()
                issued = IssuedTokens(
                    user=user,
                    access_token=create_access_token(user.id, new_session_id, now=now),
                    refresh_token=new_refresh_token,
                    expires_in=get_settings().access_token_expire_minutes * 60,
                )

    if invalid or issued is None:
        raise InvalidRefreshToken
    return issued


async def logout_session(session: AsyncSession, refresh_token: str) -> None:
    """Revoke a refresh session; logout is intentionally idempotent."""

    token_hash = hash_refresh_token(refresh_token)
    async with transaction(session):
        auth_session = await session.scalar(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == token_hash)
            .with_for_update()
        )
        if auth_session is not None and auth_session.revoked_at is None:
            auth_session.revoked_at = datetime.now(UTC)


async def _upsert_device(
    session: AsyncSession,
    user_id: UUID,
    device: DeviceInput | None,
) -> Device | None:
    if device is None:
        return None

    existing: Device | None = None
    if device.device_key is not None:
        existing = await session.scalar(
            select(Device)
            .where(Device.user_id == user_id, Device.device_key == device.device_key)
            .with_for_update()
        )
    if existing is not None:
        if device.device_name is not None:
            existing.device_name = device.device_name
        if device.platform is not None:
            existing.platform = device.platform
        existing.last_seen_at = datetime.now(UTC)
        existing.revoked_at = None
        return existing

    new_device = Device(
        user_id=user_id,
        device_key=device.device_key,
        device_name=device.device_name,
        platform=device.platform,
        last_seen_at=datetime.now(UTC),
    )
    session.add(new_device)
    await session.flush()
    return new_device


async def _issue_tokens(
    session: AsyncSession,
    user: User,
    device: Device | None,
) -> IssuedTokens:
    now = datetime.now(UTC)
    session_id = uuid4()
    refresh_token = generate_refresh_token()
    auth_session = AuthSession(
        id=session_id,
        user_id=user.id,
        device_id=device.id if device is not None else None,
        refresh_token_hash=hash_refresh_token(refresh_token),
        token_family_id=uuid4(),
        expires_at=now + timedelta(days=get_settings().refresh_token_expire_days),
        last_used_at=now,
    )
    session.add(auth_session)
    await session.flush()
    return IssuedTokens(
        user=user,
        access_token=create_access_token(user.id, session_id, now=now),
        refresh_token=refresh_token,
        expires_in=get_settings().access_token_expire_minutes * 60,
    )
