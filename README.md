# Drinkit

Drinkit is being built as a modular monolith for premium quick-commerce delivery of beverages, snacks, ice, party supplies, and recovery products.

## Phase 4 status

Phase 1 established the PostgreSQL and SQLAlchemy foundation. Phase 2 adds
email/password authentication, Argon2id password hashing, persisted devices,
rotating opaque refresh-token sessions, JWT access tokens, logout, and the
authenticated user profile endpoint. Phase 3 adds a read-only catalog
foundation with hierarchical categories, products, category membership, and
sellable variants/SKUs. Inventory, pricing, carts, orders, payments, delivery,
and catalog administration remain future phases. Phase 4 adds fulfillment
locations, PostgreSQL inventory balances, idempotent stock adjustments, and
concurrency-safe expiring reservations. Pricing, carts, orders, payments,
delivery, and operator administration remain future phases.

## Local setup

Requirements:

- Python 3.12 or newer
- PostgreSQL 15 or newer for local development
- Docker Compose is optional for running PostgreSQL and Redis

Create and install the project virtual environment:

```bash
python3 -m venv drinkit_env
drinkit_env/bin/python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `DATABASE_URL` for the local PostgreSQL instance. `.env` is ignored and must never contain committed production credentials.

Start infrastructure with Docker when desired:

```bash
docker compose up -d postgres redis
```

Run migrations:

```bash
drinkit_env/bin/alembic upgrade head
```

Run the API:

```bash
drinkit_env/bin/uvicorn app.main:app --reload
```

The OpenAPI documents are available at `/api/v1/openapi.json`, `/docs`, and
`/redoc`. Liveness is `/api/v1/health/live`; readiness performs a real
PostgreSQL query at `/api/v1/health/ready`.

Authentication endpoints are under `/api/v1/auth/`: `register`, `login`,
`refresh`, `logout`, and `me`. See
[`docs/authentication.md`](docs/authentication.md) for token and session
security details.

Catalog endpoints are under `/api/v1/catalog/`: `categories`, `products`, and
`products/{slug}`. See [`docs/catalog.md`](docs/catalog.md) for the product /
variant boundary and publication rules.

Inventory mutation is currently an internal service boundary, not a public
HTTP endpoint. See [`docs/inventory.md`](docs/inventory.md) for locking,
idempotency, reservation, and expiry behavior.

## Verification

Unit tests do not require PostgreSQL. Integration tests use a real PostgreSQL database configured through `TEST_DATABASE_URL` when `APP_ENV=test`:

```bash
APP_ENV=test \
TEST_DATABASE_URL=postgresql://drinkit:drinkit_dev_password@localhost:5432/drinkit_test \
drinkit_env/bin/python -m pytest -q
```

If the configured PostgreSQL test database cannot be reached, integration tests skip rather than falsely claiming PostgreSQL coverage.

Quality checks:

```bash
drinkit_env/bin/ruff check .
drinkit_env/bin/black --check .
drinkit_env/bin/mypy app
drinkit_env/bin/python -m pytest -q
```

## Repository conventions

- PostgreSQL is authoritative for transactional state.
- Redis is reserved for caching, coordination, rate limiting, and pub/sub; it is not a source of truth.
- API requests use async SQLAlchemy sessions. Alembic and synchronous workers use the psycopg driver against the same metadata.
- Services own transactions with `async with transaction(session)`; repositories must not commit independently.
- Models use explicit table names, UUIDv4 primary keys, timezone-aware UTC timestamps, named constraints, and indexes justified by access paths.
- Domain models should be imported from `app.models` so Alembic autogeneration sees their metadata.
- Soft deletion is opt-in per domain; it is not part of the universal base model.
- Authentication services own token/session transactions; refresh rotation uses
  row locking and refresh-token digests are the only persisted token form.
- Catalog products describe customer-facing identity; variants describe
  sellable SKU/package identity. Pricing and inventory are separate domains.
- Inventory balances are authoritative per fulfillment-location/variant pair;
  reservations and adjustments update them under PostgreSQL row locks.

See [`docs/database.md`](docs/database.md),
[`docs/authentication.md`](docs/authentication.md),
[`docs/catalog.md`](docs/catalog.md),
[`docs/inventory.md`](docs/inventory.md),
[`docs/adr/0001-database-access-strategy.md`](docs/adr/0001-database-access-strategy.md),
[`docs/adr/0002-authentication-session-strategy.md`](docs/adr/0002-authentication-session-strategy.md),
[`docs/adr/0003-catalog-product-variant-boundary.md`](docs/adr/0003-catalog-product-variant-boundary.md),
and [`docs/adr/0004-inventory-authority-and-locking.md`](docs/adr/0004-inventory-authority-and-locking.md)
for the Phase 1 through Phase 4 decisions.
