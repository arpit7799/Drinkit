"""
Alembic migration environment.

Loads the synchronous database URL from application settings (rather
than duplicating it in alembic.ini) so there is a single source of
truth for connection configuration. Imports `Base` and all ORM models
so `--autogenerate` can diff against the full metadata.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app` importable when alembic is invoked from the backend/ directory.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.session import Base  # noqa: E402

# Import all models here so they register on Base.metadata for autogenerate.
# Populated as models are added in Phase 1.
# from app.models import user, report, department  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()