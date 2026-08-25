"""Application configuration loaded from environment variables."""

from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API, workers, and migration tooling.

    ``DATABASE_URL`` is the only required deployment-specific database input.
    The application and migration/worker drivers are derived from it so URLs do
    not drift between runtime components.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Drinkit"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    database_url: str = "postgresql://drinkit:drinkit_dev_password@localhost:5432/drinkit"
    test_database_url: str | None = None
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1)
    db_pool_recycle: int = Field(default=1800, ge=0)
    db_pool_pre_ping: bool = True
    sql_echo: bool = False

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_postgresql(cls, value: str) -> str:
        scheme = urlsplit(value).scheme
        if scheme not in {
            "postgres",
            "postgresql",
            "postgresql+asyncpg",
            "postgresql+psycopg",
            "postgresql+psycopg2",
        }:
            raise ValueError("DATABASE_URL must use a PostgreSQL SQLAlchemy URL")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_url_async(self) -> str:
        """Return the URL used by FastAPI's async request path."""
        source = (
            self.test_database_url if self.testing and self.test_database_url else self.database_url
        )
        return _with_driver(source, "asyncpg")

    @property
    def database_url_sync(self) -> str:
        """Return the URL used by Alembic and synchronous workers."""
        source = (
            self.test_database_url if self.testing and self.test_database_url else self.database_url
        )
        return _with_driver(source, "psycopg")

    @property
    def testing(self) -> bool:
        return self.app_env.lower() in {"test", "testing"}


def _with_driver(database_url: str, driver: str) -> str:
    parsed = urlsplit(database_url)
    return urlunsplit(
        (
            f"postgresql+{driver}",
            parsed.netloc,
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-cached settings object."""
    return Settings()
