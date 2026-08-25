# Drinkit

Drinkit is being built as a modular monolith for premium quick-commerce delivery of beverages, snacks, ice, party supplies, and recovery products.

## Phase 1 status

Phase 1 establishes the PostgreSQL and SQLAlchemy foundation only. It does not implement authentication, catalog, inventory workflows, carts, orders, payments, or delivery.

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

The OpenAPI documents are available at `/api/v1/openapi.json`, `/docs`, and `/redoc`. Liveness is `/api/v1/health/live`; readiness performs a real PostgreSQL query at `/api/v1/health/ready`.

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

See [`docs/database.md`](docs/database.md) and [`docs/adr/0001-database-access-strategy.md`](docs/adr/0001-database-access-strategy.md) for the Phase 1 decisions.
