from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 9010
    database_url: str = "sqlite+aiosqlite:///./data/stock_agent.db"
    cors_origins: list[str] = ["http://localhost:6173"]
    log_level: str = "INFO"
    app_encryption_key: str = "development-only-change-before-production"
    llm_timeout_seconds: float = 45
    llm_max_retries: int = 2
    llm_temperature: float = 0.1

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
