# ADR 0002: Persisted sessions with rotated opaque refresh tokens

- Status: Accepted
- Date: 2026-08-26
- Scope: Phase 2 authentication and identity

## Decision

Use short-lived HMAC-signed JWT access tokens plus cryptographically random,
opaque refresh tokens. Persist only SHA-256 refresh-token digests in PostgreSQL.
Represent each refresh session with a user, optional device, expiry, revocation
state, replacement pointer, and token-family identifier.

A refresh operation locks the presented session row, revokes it, inserts the
replacement session, and commits both changes atomically. Reuse of a revoked
token revokes the remaining active sessions in its family.

## Reason

The API needs stateless authorization claims for normal request throughput, but
quick-commerce operations also need immediate session revocation and reliable
refresh replay detection. A persisted session record provides that control
without putting security-critical state in Redis. Opaque refresh tokens avoid
exposing durable database identifiers or signed long-lived credentials to
clients, and storing digests limits the impact of a database read leak.

## Alternatives considered

### Long-lived JWT refresh tokens

Rejected. Revocation and replay detection are difficult without another durable
state store, and a stolen token remains usable until expiry.

### Server-side sessions only

Rejected for the API access path. It would add a database lookup to every
request and does not provide the useful bounded, verifiable access-token claims
needed by downstream services.

### Redis as the session authority

Rejected. Redis is appropriate for ephemeral coordination and acceleration,
but PostgreSQL is the authoritative store for identity and security state. A
Redis outage must not redefine whether a user session exists.

### JWT library defaults without persisted session checks

Rejected. Logout and operator revocation would not take effect until JWT
expiry, which is not an acceptable security contract.

## Trade-offs

- Protected requests perform a PostgreSQL session lookup in addition to JWT
  verification. This buys revocation correctness and can be optimized later
  with carefully bounded caching without changing the source of truth.
- Rotation creates one row per refresh operation. Expired/revoked-session
  retention and cleanup will require a later operational job.
- The initial password flow is email/password only. OTP, MFA, recovery,
  verification, RBAC, and compliance policies remain separate phases.
- HS256 requires secure secret distribution to every verifier. If independent
  services eventually need asymmetric verification, a deliberate migration to
  a key-pair/JWKS strategy should be benchmarked and documented.
