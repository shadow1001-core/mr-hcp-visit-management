from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MR-HCP Academic Visit Management API"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = "development"
    business_timezone: str = "Asia/Shanghai"
    database_url: str = "postgresql+psycopg://mr_hcp@localhost:5432/mr_hcp"

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            msg = "DATABASE_URL must use PostgreSQL"
            raise ValueError(msg)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
