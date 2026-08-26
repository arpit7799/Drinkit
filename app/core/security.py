"""Authentication and identity security primitives."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings
from app.core.exceptions import InvalidAccessToken

_password_hasher = PasswordHasher()
_dummy_password_hash = _password_hasher.hash("drinkit-dummy-password")


@dataclass(frozen=True)
class AccessTokenClaims:
    """Validated claims carried by a Drinkit access token."""

    subject: UUID
    session_id: UUID
    token_type: str


def hash_password(password: str) -> str:
    """Hash a password using Argon2id with the library's safe defaults."""

    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password without exposing malformed-hash details."""

    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def needs_password_rehash(password_hash: str) -> bool:
    """Report whether a successful login should upgrade the Argon2 parameters."""

    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, VerificationError):
        return False


def verify_unknown_user_password(password: str) -> None:
    """Perform equivalent password work for an unknown email address."""

    verify_password(password, _dummy_password_hash)


def create_access_token(
    user_id: UUID,
    session_id: UUID,
    now: datetime | None = None,
) -> str:
    """Create a short-lived signed JWT bound to one persisted auth session."""

    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "typ": "access",
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> AccessTokenClaims:
    """Validate an access JWT and return only its typed identity claims."""

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "sid", "typ", "iat", "exp", "jti"]},
        )
        if payload.get("typ") != "access":
            raise InvalidAccessToken
        return AccessTokenClaims(
            subject=UUID(str(payload["sub"])),
            session_id=UUID(str(payload["sid"])),
            token_type="access",
        )
    except (InvalidAccessToken, ValueError, TypeError, jwt.InvalidTokenError) as exc:
        raise InvalidAccessToken from exc


def generate_refresh_token() -> str:
    """Generate a high-entropy opaque refresh token."""

    return secrets.token_urlsafe(48)


def hash_refresh_token(refresh_token: str) -> str:
    """Return the only representation of a refresh token stored in PostgreSQL."""

    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
