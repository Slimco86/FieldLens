"""Process-level DTOs: session bootstrap and readiness."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import ContractModel


class SessionResponse(ContractModel):
    """Local mutation token; process-local, regenerated on API restart."""

    csrf_token: str = Field(min_length=32)


class ReadinessCheck(ContractModel):
    name: Literal["database", "migrations", "pgvector", "storage_root"]
    ok: bool
    detail: str | None = None


class ReadinessResponse(ContractModel):
    status: Literal["ready"]
    checks: list[ReadinessCheck]


class HealthResponse(ContractModel):
    status: Literal["ok"]
    version: str
