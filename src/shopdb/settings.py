"""Settings (read from .env) and the size profiles (S and M)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Connection settings. Values come from environment variables or the project's .env file."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "shop"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    shop_owner_password: str = ""
    loader_password: str = ""
    mcp_reader_password: str = ""
    mcp_writer_password: str = ""
    mcp_proc_exec_password: str = ""
    shop_scale: str = "S"
    shop_seed: int = 42

    def password_for(self, role: str) -> str:
        if role == self.postgres_user:
            return self.postgres_password
        return getattr(self, f"{role}_password")


@lru_cache
def get_settings() -> Settings:
    return Settings()
