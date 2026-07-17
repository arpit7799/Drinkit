"""
Application configuration.

All runtime configuration is loaded from environment variables (see
`.env.example` for the full list) via Pydantic Settings. Importing
`get_settings()` anywhere in the codebase returns a cached singleton,
so environment variables are only parsed once per process.

Design decision: we use `lru_cache` rather than a module-level global
so that tests can override settings cleanly via dependency overrides
without mutating shared state.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings, populated from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App metadata ---
    APP_NAME: str = "CivicAI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Security ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173"

    # --- Database ---
    POSTGRES_USER: str = "civicai"
    POSTGRES_PASSWORD: str = "civicai_dev_password"
    POSTGRES_DB: str = "civicai_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # --- File storage ---
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "./storage/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # --- Email tokens ---
    EMAIL_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/email/oauth/callback"
    GOOGLE_OAUTH_SCOPES: str = "https://www.googleapis.com/auth/gmail.send"

    # --- Default city seed ---
    DEFAULT_CITY_NAME: str = "Gurugram"
    DEFAULT_CITY_STATE: str = "Haryana"
    DEFAULT_CITY_PINCODE: str = "122001"

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_not_be_placeholder(cls, v: str) -> str:
        if v in ("", "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"):
            raise ValueError(
                "SECRET_KEY must be set to a real secret. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS string into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Cached with lru_cache so environment parsing happens exactly once
    per process, while still being trivially overridable in tests via
    FastAPI's dependency_overrides on `get_settings`.
    """
    return Settings()