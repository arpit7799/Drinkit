# Database architecture

## Scope

Phase 1 provides the persistence boundary for the modular monolith. PostgreSQL is the source of truth for transactional state. Redis is deliberately not part of the database session or commit path; later phases may use it for cache, rate limiting, coordination, and pub/sub.

The only persisted infrastructure record in this phase is `outbox_events`. It gives future domains a safe path to record a domain event in the same PostgreSQL transaction as a state change. Publishing is intentionally not implemented yet.

## Driver and session strategy

The FastAPI request path uses SQLAlchemy 2.x async sessions through `asyncpg`. This avoids blocking the event loop during ordinary API database work and matches FastAPI's async execution model. Alembic and Celery-style synchronous workers use a separate `psycopg` engine against the same ORM metadata. Keeping both engines explicit avoids running an event loop inside a synchronous worker and keeps migrations simple.

The two engines are not two databases: they address the same PostgreSQL source of truth. They share model metadata, naming conventions, constraints, and transaction rules.

- `app.core.database.async_engine` is the pooled API engine.
- `app.core.database.get_sync_engine()` is lazy and used by migrations/workers.
- `app.core.database.get_db()` is request-scoped and rolls back on unhandled exceptions.
- `app.core.database.transaction(session)` is the service-owned transaction context.
- Repositories must not call `commit()`; application services own transaction boundaries.

## Identifiers and timestamps

Persistent aggregate identifiers are UUIDv4 values generated in application memory. UUIDs avoid exposing record counts and are safe to generate across future service boundaries. UUIDv7 is intentionally not used in Phase 1 because the supported Python baseline does not provide it consistently and introducing a dependency solely for ordering would need a measured access-pattern decision. If ordered UUIDs become valuable, the migration should be explicit and benchmarked.

`created_at`, `updated_at`, and event timestamps are PostgreSQL `TIMESTAMP WITH TIME ZONE` columns. PostgreSQL stores instants in UTC; application code uses timezone-aware Python `datetime` values. The universal base does not include soft deletion or audit actor columns: those are domain-specific policies and must be added only where their semantics are clear.

## Naming, constraints, and indexes

All tables use explicit plural snake_case names. Columns use snake_case. Constraint names are deterministic through `NAMING_CONVENTION`, which makes migration diffs reviewable and database errors actionable.

Use `NOT NULL`, foreign keys, unique constraints, and check constraints for invariants that must hold regardless of caller. The outbox `attempts >= 0` rule is enforced by PostgreSQL, not only Pydantic or Python code.

Indexes must correspond to a read path. The outbox has an aggregate lookup index and a partial index for unpublished records, matching the future publisher's polling query. Future high-volume domains should add indexes with the migration that introduces their access path, rather than pre-creating speculative indexes.

## Configuration

`DATABASE_URL` is the single deployment-specific input. The application derives `postgresql+asyncpg` and `postgresql+psycopg` forms from it. Pool settings are configurable with `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, and `DB_POOL_PRE_PING`.

Defaults are development-oriented and must be replaced for staging/production. Secrets belong in an untracked `.env`, a secret manager, or deployment environment. No production credential is stored in source control.

## Migration workflow

```bash
# from the repository root
cp .env.example .env
# edit DATABASE_URL for the target PostgreSQL instance
drinkit_env/bin/alembic upgrade head
drinkit_env/bin/alembic current
drinkit_env/bin/alembic downgrade -1
drinkit_env/bin/alembic upgrade head
```

Autogeneration is available after importing new ORM models from `app.models`, but generated migrations must be reviewed manually. A migration is code: check constraints, indexes, nullability, defaults, and downgrade behavior before applying it.

## Testing workflow

Unit tests cover configuration, metadata, naming conventions, model column contracts, and liveness without a database. Integration tests use a real PostgreSQL database through `TEST_DATABASE_URL` when `APP_ENV=test`; they exercise connectivity, PostgreSQL constraints, session transactions, and rollback. SQLite is not used as a PostgreSQL substitute.

The test fixture creates only the Phase 1 metadata in the configured test database and removes it after the module. For CI, provision an isolated PostgreSQL database per job and never point tests at a developer or production database.

## Docker

`docker-compose.yml` supplies PostgreSQL and Redis for local development. Redis is included as an infrastructure boundary for future phases, but Phase 1 does not read or write Redis. The API can be run from the host using `drinkit_env`.
