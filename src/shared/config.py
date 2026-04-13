"""Shared configuration loaded from env vars or .env."""
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    database_url: str = Field(
        default="",
        description="PostgreSQL async connection URL (postgresql+asyncpg://...)",
    )
    credential_encryption_key: str = Field(
        default="",
        description="Symmetric key used with pgcrypto to decrypt stored credentials",
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def validate_required(self) -> None:
        missing = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.credential_encryption_key:
            missing.append("CREDENTIAL_ENCRYPTION_KEY")
        if missing:
            raise ValueError(f"Configuration incomplete. Missing: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
