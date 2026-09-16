from app.core.config import Settings


def test_default_database_uses_postgresql_without_embedded_password() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "@" in settings.database_url
    assert "://mr_hcp:" not in settings.database_url
