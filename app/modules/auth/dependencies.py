"""Authentication dependencies used by protected API routes."""

from datetime import UTC, datetime

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import InvalidAccessToken
from app.core.security import decode_access_token
from app.models.auth import AuthSession, User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Validate the JWT and its still-active persisted session."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidAccessToken

    claims = decode_access_token(credentials.credentials)
    user = await session.scalar(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            User.id == claims.subject,
            User.is_active.is_(True),
            AuthSession.id == claims.session_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    if user is None:
        raise InvalidAccessToken
    # Authentication is a read-only dependency. End its implicit transaction
    # so a protected mutation service can own the request transaction.
    await session.commit()
    return user
