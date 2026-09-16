import pytest

from app.core.config import Settings
from app.db.seed import run_seed


def test_default_database_uses_postgresql_without_embedded_password() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "@" in settings.database_url
    assert "://mr_hcp:" not in settings.database_url


def test_seed_refuses_to_run_in_production_before_connecting() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+psycopg://invalid-host/unused",
    )

    with pytest.raises(RuntimeError, match="APP_ENV=production"):
        run_seed(settings)
