"""Typed, redacted application configuration (environment prefix ``FIELDLENS_``)."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_NAMES = frozenset({"localhost"})
DEFAULT_API_PORT = 8101
DEFAULT_VITE_PORT = 5174


def is_loopback_host(host: str) -> bool:
    """True only for literal loopback addresses or ``localhost``."""
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _default_hosts() -> list[str]:
    ports = (DEFAULT_API_PORT, DEFAULT_VITE_PORT)
    return [f"{h}:{p}" for p in ports for h in ("127.0.0.1", "localhost")]


def _default_origins() -> list[str]:
    return [f"http://{h}" for h in _default_hosts()]


class Settings(BaseSettings):
    """Process configuration. Secret fields are never rendered by ``redacted()``."""

    model_config = SettingsConfigDict(
        env_prefix="FIELDLENS_", extra="ignore", env_file=None, frozen=True
    )

    host: str = "127.0.0.1"
    port: int = Field(DEFAULT_API_PORT, ge=1, le=65535)
    database_url: SecretStr | None = None
    storage_root: Path = Path(".local/fieldlens/storage")
    frontend_dist: Path = Path("frontend/dist")
    allowed_hosts: list[str] = Field(default_factory=_default_hosts)
    allowed_origins: list[str] = Field(default_factory=_default_origins)
    db_connect_timeout_s: int = Field(3, ge=1, le=30)

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if not is_loopback_host(value):
            raise ValueError(
                "FIELDLENS_HOST must be a loopback address (127.0.0.1, ::1, localhost)"
            )
        return value

    @field_validator("database_url")
    @classmethod
    def _psycopg_postgres_only(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("FIELDLENS_DATABASE_URL must use postgresql+psycopg://")
        return value

    def redacted(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["database_url"] = "***" if self.database_url is not None else None
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()
