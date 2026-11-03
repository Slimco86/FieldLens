"""Typed, redacted application configuration (environment prefix ``FIELDLENS_``).

Values come from the process environment first, then the repository-root ``.env``.
Pass ``_env_file=None`` for an explicit, file-independent configuration.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from collections.abc import Mapping
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator
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
        extra="ignore",  # unrelated .env keys are never adopted; only MODEL_API_KEY is aliased
        env_file=ENV_FILE,  # anchored to the repository root; real environment variables win
        env_file_encoding="utf-8",
        frozen=True,
        hide_input_in_errors=True,
    )

    host: str = "127.0.0.1"
    port: int = Field(DEFAULT_API_PORT, ge=1, le=65535)
    database_url: SecretStr | None = None
    storage_root: Path = REPO_ROOT / ".local/fieldlens/storage"
    lane: str = Field("main", pattern=r"^[A-Za-z0-9._-]{1,32}$")
    """Development lane name; identifies this process in DB ``application_name`` and failures."""
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

    # Meta provider (server-side only). The single provider key is MODEL_API_KEY (process
    # environment, else the root .env; owner decision 2026-10-30 13:41 EDT). It is the only
    # non-FIELDLENS_/POSTGRES_ name adopted, is held as a secret and is never logged or echoed.
    # An absent/blank key fails closed with a typed error before any dispatch. Limits default to
    # MI-5 and may only be lowered, except the tool-call bound (configurable, default 6).
    meta_api_key: SecretStr | None = Field(None, validation_alias="MODEL_API_KEY")
    meta_base_url: str = "https://api.meta.ai/v1"
    meta_model: str = "muse-spark-1.3"
    budget_ledger_cap_usd: Decimal = Field(Decimal("150"), gt=0, le=Decimal("150"))
    budget_warn_usd: Decimal = Field(Decimal("100"), gt=0, le=Decimal("150"))
    budget_unattended_block_usd: Decimal = Field(Decimal("120"), gt=0, le=Decimal("150"))
    provider_max_attempts: int = Field(4, ge=1, le=4)
    provider_max_tool_calls: int = Field(6, ge=1, le=64)
    provider_deadline_s: float = Field(90.0, gt=0, le=90.0)
    provider_max_output_tokens: int = Field(4096, ge=1, le=4096)
    provider_max_reserved_usd: Decimal = Field(Decimal("0.50"), gt=0, le=Decimal("0.50"))
    provider_image_token_bound: int = Field(8192, ge=1, le=1_000_000)

    @field_validator("meta_api_key")
    @classmethod
    def _blank_key_is_absent(cls, value: SecretStr | None) -> SecretStr | None:
        return value if value is not None and value.get_secret_value().strip() else None

    # Local retrieval embeddings (TASK-011). Meta has no embeddings endpoint for our key, so the
    # only real backend is the pinned local FastEmbed model; ``none`` forces the degraded
    # (exact + full text) retrieval mode, ``fake`` is the deterministic offline test embedder.
    embedding_provider: Literal["fastembed", "fake", "none"] = "fastembed"
    embedding_model_dir: Path | None = None
    retrieval_max_chunks_per_document: int = Field(50_000, ge=1, le=200_000)
    retrieval_max_embedded_chunks_per_document: int = Field(3000, ge=1, le=200_000)
    """Safety bound on embedded chunks per document (CPU budget ~0.15-0.2 s/chunk). Numeric
    tables are excluded by policy before this applies; if non-numeric content ever exceeds it the
    document honestly reports a partial vector index."""
    retrieval_analyze_after_index: bool = True
    retrieval_vector_support_floor: float = Field(0.68, ge=-1.0, le=1.0)
    retrieval_vector_margin: float = Field(0.04, ge=0.0, le=1.0)
    """Cosine a vector-only hit must reach, and stand ``retrieval_vector_margin`` above the median
    of the vector candidates, to count as strong. UNCALIBRATED: the int8 bge-small model puts
    off-topic text at 0.50-0.63, in-domain paraphrases at about 0.6-0.8; calibrate with the G1 gold
    set before relying on it. Vector-only results below it are returned but flagged weak."""
    retrieval_max_attempts: int = Field(3, ge=1, le=10)
    retrieval_min_vector_similarity: float = Field(0.0, ge=-1.0, le=1.0)

    @field_validator("embedding_model_dir", mode="before")
    @classmethod
    def _blank_model_dir_is_default(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    # Native-profile extraction (TASK-009).
    extraction_max_attempts: int = Field(3, ge=1, le=10)

    # Model-proposed extraction harness (TASK-036, AX-12/AX-14). Offline by default.
    page_image_long_side: int = Field(1600, ge=200, le=2400)
    """Longest side in px of a rendered page image; 2,400 is a hard cap (AX-12)."""
    page_image_cache_mb: int = Field(64, ge=1, le=1024)
    page_render_concurrency: int = Field(2, ge=1, le=8)
    extraction_max_pages: int = Field(12, ge=1, le=60)
    """Triage cap: candidate pages read per document (AX-14)."""
    extraction_read_concurrency: int = Field(3, ge=1, le=8)
    extraction_page_reserve_usd: Decimal = Field(Decimal("0.25"), gt=0, le=Decimal("0.50"))

    # Staged document processing runs (TASK-054, PROCESSING_FLOW D3/D7/D8). The stub provider is
    # the default and never spends. ``meta`` (TASK-055 model step) needs explicit configuration:
    # MODEL_API_KEY, both owner rates and a per-run cap below; otherwise the app starts on the
    # stub, reports ``provider_misconfigured`` and refuses processing requests (TASK-072).
    processing_provider: Literal["stub", "meta"] = "stub"
    processing_max_pages: int = Field(500, ge=1, le=500)
    """Pages per document and per run (D3); larger documents need an explicit page range."""
    processing_total_cap_usd: Decimal = Field(Decimal("5"), gt=0, le=Decimal("5"))
    """Aggregate live-spend cap for developing/testing the processing flow (D7)."""
    processing_document_concurrency: int = Field(2, ge=1, le=4)
    processing_input_tokens_per_page: int = Field(1600, ge=1, le=100_000)
    processing_output_tokens_per_page: int = Field(400, ge=1, le=100_000)
    """UNCALIBRATED per-page token assumptions behind the estimate (model route)."""
    processing_stub_input_usd_per_mtok: Decimal = Field(Decimal("0.30"), gt=0)
    processing_stub_output_usd_per_mtok: Decimal = Field(Decimal("2.50"), gt=0)
    """Illustrative stub rates, labelled as such in every estimate; never an owner rate card."""
    processing_model_pages: int = Field(5, ge=1, le=20)
    """Default page count (first pages) of a model estimate that names no page range (TASK-075:
    no longer a bound; the user chooses 1..total)."""
    processing_pages_per_call: int = Field(10, ge=1, le=20)
    """TASK-075: a model selection is sent in sequential calls of at most this many pages."""
    processing_run_cap_usd: Decimal | None = Field(None, gt=0, le=Decimal("5"))
    """DEPRECATED (TASK-075): no longer applies to the model route (a confirmed run is the
    authorization); still gates the stub route."""
    processing_meta_input_usd_per_mtok: Decimal | None = Field(None, gt=0)
    processing_meta_output_usd_per_mtok: Decimal | None = Field(None, gt=0)
    """Owner-supplied Meta rates for the ``meta`` provider; the code assumes none."""
    processing_live_period: str = Field("processing-live", min_length=1, max_length=64)
    """Budget-ledger period the live model step reserves against."""
    processing_lease_seconds: float = Field(60.0, gt=0)
    processing_heartbeat_seconds: float = Field(10.0, gt=0)
    processing_stage_delay_s: float = Field(0.0, ge=0.0, le=5.0)
    """Test-only pause after each page so cancel/restart tests can interrupt a run."""

    # Per-wellbore reconstruction runs (TASK-068). Stub planning rates only; no live call exists.
    reconstruction_concurrency: int = Field(2, ge=1, le=2)
    """Runs executing at once (RECONSTRUCTION_RUN.md: bounded concurrency of at most two)."""

    # S5 visual-reference research (TASK-079). OFF by default; only equipment name hints leave the
    # application. Loop/step limits, no USD limit (owner decision).
    visual_research_backend: str = "off"
    """``off`` is the only backend shipped; a search backend is plugged in through the
    ``SearchBackend`` protocol of the asset-spec research module."""

    @field_validator("visual_research_backend")
    @classmethod
    def _research_backend_known(cls, value: str) -> str:
        if value not in ("off",):
            raise ValueError("FIELDLENS_VISUAL_RESEARCH_BACKEND must be one of: off")
        return value

    visual_research_max_queries: int = Field(6, ge=1, le=20)
    visual_research_max_pages: int = Field(10, ge=1, le=30)
    visual_research_deadline_s: float = Field(120.0, gt=0, le=600)
    """Per component."""

    local_data_root: Path | None = None
    """Opt-in read-only root of the local Volve subset (tests only); unset => local_data skips."""

    @field_validator(
        "processing_provider",
        "processing_run_cap_usd",
        "processing_meta_input_usd_per_mtok",
        "processing_meta_output_usd_per_mtok",
        "processing_model_pages",
        "processing_pages_per_call",
        mode="before",
    )
    @classmethod
    def _blank_processing_value_is_default(cls, value: object, info: ValidationInfo) -> object:
        """``scripts/init_env.py`` lists these keys empty: a blank value means 'not set'."""
        if isinstance(value, str) and not value.strip():
            defaults: dict[str, object] = {
                "processing_provider": "stub",
                "processing_model_pages": 5,
                "processing_pages_per_call": 10,
            }
            return defaults.get(str(info.field_name))  # the optional fields default to None
        return value

    @field_validator("local_data_root", mode="before")
    @classmethod
    def _blank_data_root_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("storage_root")
    @classmethod
    def _anchor_storage_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else REPO_ROOT / value

    @field_validator("meta_base_url")
    @classmethod
    def _meta_base_url_scheme(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(value)
        if parts.scheme == "https" and parts.hostname:
            return value.rstrip("/")
        if parts.scheme == "http" and parts.hostname and is_loopback_host(parts.hostname):
            return value.rstrip("/")  # loopback fakes only
        raise ValueError("FIELDLENS_META_BASE_URL must be https (or loopback http)")

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
        data["meta_api_key"] = "***" if self.meta_api_key is not None else None
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()


_IGNORED_UNPREFIXED = re.compile(
    r"^(PROCESSING_(PROVIDER|RUN_CAP_USD|MODEL_PAGES|META_[A-Z0-9_]+)|META_[A-Z0-9_]+)$"
)
_ENV_KEY_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def ignored_unprefixed_keys(
    environ: Mapping[str, str] | None = None, env_file: Path | str | None = ENV_FILE
) -> list[str]:
    """Sorted names (never values) of unprefixed processing/meta settings present in the process
    environment or the ``.env`` file. Settings only read ``FIELDLENS_*``, so these are ignored."""
    names: set[str] = set()
    for key in os.environ if environ is None else environ:
        if _IGNORED_UNPREFIXED.match(key):
            names.add(key)
    if env_file is not None:
        path = Path(env_file)
        try:
            lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        except (OSError, UnicodeDecodeError):
            lines = []
        for line in lines:
            match = _ENV_KEY_LINE.match(line)
            if match and _IGNORED_UNPREFIXED.match(match.group(1)):
                names.add(match.group(1))
    return sorted(names)


def warn_ignored_unprefixed(
    log: logging.Logger,
    environ: Mapping[str, str] | None = None,
    env_file: Path | str | None = ENV_FILE,
) -> list[str]:
    """One warning per ignored unprefixed key, naming the prefixed variable to use."""
    names = ignored_unprefixed_keys(environ, env_file)
    for name in names:
        log.warning(
            "%s is set but ignored: settings read only FIELDLENS_-prefixed variables; "
            "use FIELDLENS_%s",
            name,
            name,
        )
    return names
