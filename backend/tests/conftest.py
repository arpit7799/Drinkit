"""
Shared pytest fixtures.

Phase 0 only needs enough to prove the app boots and the health
endpoint responds. Database-backed fixtures (test DB, session
override) are added in Phase 1 once models exist.
"""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://civicai:civicai@localhost:5432/civicai_test"
)
os.environ.setdefault(
    "DATABASE_URL_SYNC", "postgresql+psycopg2://civicai:civicai@localhost:5432/civicai_test"
)


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client