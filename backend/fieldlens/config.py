"""Typed, redacted application configuration (environment prefix ``FIELDLENS_``).

Values come from the process environment first, then the repository-root ``.env``.
Pass ``_env_file=None`` for an explicit, file-independent configuration.
"""

from __future__ import annotations

import ipaddress
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fieldlens.localenv import ENV_FILE, REPO_ROOT, load_local_env

LOOPBACK_NAMES = frozenset({"localhost"})
DEFAULT_API_PORT = 8101
DEFAULT_VITE_PORT = 5174
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_BATCH_BYTES = 512 * 1024 * 1024
MAX_FILES = 200
MAX_OVERHEAD_BYTES = 1024 * 1024
_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


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
        env_prefix="FIELDLENS_",
        extra="ignore",  # unrelated .env keys (e.g. provider credentials) are never adopted
        env_file=ENV_FILE,  # anchored to the repository root; real environment variables win
        env_file_encoding="utf-8",
        frozen=True,
        hide_input_in_errors=True,
    )

    host: str = "127.0.0.1"
    port: int = Field(DEFAULT_API_PORT, ge=1, le=65535)
    database_url: SecretStr | None = None
    storage_root: Path = REPO_ROOT / ".local/fieldlens/storage"
    frontend_dist: Path = Path("frontend/dist")
    allowed_hosts: list[str] = Field(default_factory=_default_hosts)
    allowed_origins: list[str] = Field(default_factory=_default_origins)
    db_connect_timeout_s: int = Field(3, ge=1, le=30)

    # Upload bounds: defaults are the owner-approved limits and may only be lowered (tests).
    upload_max_file_bytes: int = Field(MAX_FILE_BYTES, ge=1, le=MAX_FILE_BYTES)
    upload_max_batch_bytes: int = Field(MAX_BATCH_BYTES, ge=1, le=MAX_BATCH_BYTES)
    upload_max_files: int = Field(MAX_FILES, ge=1, le=MAX_FILES)
    upload_max_overhead_bytes: int = Field(MAX_OVERHEAD_BYTES, ge=1024, le=MAX_OVERHEAD_BYTES)

    # Persistent job worker (one heavy job at a time).
    job_worker_enabled: bool = True
    job_lease_seconds: float = Field(600.0, gt=0, le=600.0)
    job_heartbeat_seconds: float = Field(10.0, gt=0, le=10.0)
    job_poll_seconds: float = Field(0.5, gt=0, le=10.0)
    job_stage_delay_s: float = Field(0.0, ge=0, le=60.0)
    staging_max_age_s: float = Field(3600.0, ge=0.5)
    staging_sweep_interval_s: float = Field(600.0, ge=0.1)
    """Test-only pause after each stage step so restart/kill tests can interrupt a job."""

    @field_validator("storage_root")
    @classmethod
    def _anchor_storage_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else REPO_ROOT / value

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if not is_loopback_host(value):
            raise ValueError(
                "FIELDLENS_HOST must be a loopback address (127.0.0.1, ::1, localhost)"
            )
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _expand_references(cls, value: object) -> object:
        """Resolve ``${VAR}`` left verbatim by tools that inject ``.env`` without expansion."""
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw, str) or "${" not in raw:
            return value
        file_values = load_local_env()

        def lookup(match: re.Match[str]) -> str:
            name = match.group(1)
            found = os.environ.get(name)
            if found is None or "${" in found:
                found = file_values.get(name)
            if found is None:
                raise ValueError(f"FIELDLENS_DATABASE_URL references undefined ${{{name}}}")
            return found

        return _REFERENCE.sub(lookup, raw)

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
