# Authentication and identity

## Scope

Phase 2 adds the first customer identity boundary to the modular monolith:
email/password registration and login, persisted devices, refresh-token sessions,
JWT access tokens, logout, and the authenticated `/me` endpoint. OTP, OAuth,
email verification, RBAC, age verification, and operator administration are
intentionally deferred to later phases.

## Token model

Access tokens are short-lived JWTs signed with the configured HMAC secret. They
contain the user ID and the ID of a persisted authentication session. Every
protected request validates both the JWT and the session row, so logout,
refresh-token reuse detection, and administrative revocation can invalidate
access before the JWT's natural expiry.

Refresh tokens are opaque, generated with the operating system CSPRNG, and are
never stored in plaintext. PostgreSQL stores only a SHA-256 digest. A successful
refresh transaction row-locks the presented session, revokes it, inserts a
replacement in the same token family, and returns a new refresh token. Reuse of
a previously revoked token revokes all still-active sessions in that family.

## Persistence

- `users` stores normalized email addresses, Argon2id password hashes, account
  status, and lifecycle timestamps.
- `devices` stores optional client-installation metadata and belongs to a user.
- `auth_sessions` stores refresh-token digests, expiry, revocation, replacement,
  device, and token-family data.
- Foreign keys use cascading user deletion and nulling device/replacement links
  where appropriate.
- `uq_users_email_ci` is a PostgreSQL functional unique index on `lower(email)`;
  uniqueness does not depend only on request validation.

Passwords use `argon2-cffi`'s Argon2id `PasswordHasher` defaults. The login path
performs dummy hash verification for unknown emails to avoid a trivial timing
difference, and successful logins can transparently rehash when library
parameters change.

## API

- `POST /api/v1/auth/register` — create an account and issue tokens.
- `POST /api/v1/auth/login` — authenticate with email and password.
- `POST /api/v1/auth/refresh` — rotate a refresh token exactly once.
- `POST /api/v1/auth/logout` — idempotently revoke a refresh token.
- `GET /api/v1/auth/me` — return the authenticated non-sensitive user profile.

Expected auth failures use a stable envelope:

```json
{"error": {"code": "invalid_credentials", "message": "Email or password is incorrect."}}
```

Registration conflicts return `409`; invalid credentials, invalid refresh
credentials, revoked sessions, and expired sessions return `401`; malformed
request bodies remain FastAPI `422` validation responses.

## Configuration

Set these environment variables outside local development:

- `JWT_SECRET_KEY` — strong, random secret of at least 32 characters.
- `JWT_ALGORITHM` — currently constrained to `HS256`.
- `ACCESS_TOKEN_EXPIRE_MINUTES` — short access-token lifetime, default 15.
- `REFRESH_TOKEN_EXPIRE_DAYS` — refresh-session lifetime, default 30.

`APP_ENV=production` rejects the committed development placeholder secret.
Secrets belong in the deployment environment or a secret manager, never Git.

## Transaction and concurrency rules

Auth application services own transactions; repositories do not commit. Refresh
rotation uses `SELECT ... FOR UPDATE` on the presented session. PostgreSQL
constraints enforce case-insensitive email uniqueness, refresh-token digest
uniqueness, foreign-key integrity, and model nullability. Redis is not involved
in authentication correctness in this phase.

## Deferred security work

This phase does not claim regulatory compliance or complete account security.
Email verification, password reset, account lockout/rate limiting, MFA/OTP,
RBAC, audit events, age/jurisdiction verification, and provider-specific
credential policies require separate design and, where applicable, legal
validation.
