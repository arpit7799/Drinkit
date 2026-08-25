from app.core.config import get_settings


def test_database_urls_are_normalized_to_the_selected_drivers(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/drinkit")
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url_async.startswith("postgresql+asyncpg://")
    assert settings.database_url_sync.startswith("postgresql+psycopg://")
    assert "user:pass@localhost:5432/drinkit" in settings.database_url_async
    assert "user:pass@localhost:5432/drinkit" in settings.database_url_sync

    get_settings.cache_clear()


def test_database_pool_settings_are_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "13")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "11")
    monkeypatch.setenv("DB_POOL_RECYCLE", "900")
    monkeypatch.setenv("DB_POOL_PRE_PING", "false")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.db_pool_size == 7
    assert settings.db_max_overflow == 13
    assert settings.db_pool_timeout == 11
    assert settings.db_pool_recycle == 900
    assert settings.db_pool_pre_ping is False

    get_settings.cache_clear()
