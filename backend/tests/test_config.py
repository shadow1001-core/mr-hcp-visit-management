import pytest
from pydantic import ValidationError

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


def test_business_timezone_must_be_valid_iana_name() -> None:
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        Settings(_env_file=None, business_timezone="Mars/Olympus_Mons")
