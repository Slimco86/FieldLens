"""Stable error codes and the standard error envelope."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from .base import ContractModel


class ErrorCode(StrEnum):
    """Stable machine-readable error codes. New codes require a contract change."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    CAPACITY_PAUSED = "CAPACITY_PAUSED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    NOT_READY = "NOT_READY"
    FORBIDDEN_HOST = "FORBIDDEN_HOST"
    FORBIDDEN_ORIGIN = "FORBIDDEN_ORIGIN"
    FORBIDDEN_FETCH_SITE = "FORBIDDEN_FETCH_SITE"
    SESSION_TOKEN_INVALID = "SESSION_TOKEN_INVALID"
    CONTEXT_KIND_NOT_ALLOWED = "CONTEXT_KIND_NOT_ALLOWED"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorBody(ContractModel):
    code: ErrorCode
    message: str
    request_id: str
    details: dict[str, Any] | None = Field(
        default=None, description="Sanitized details; never secrets or source bodies."
    )


class ErrorEnvelope(ContractModel):
    """``{error:{code,message,request_id,details}}`` for every non-2xx API response."""

    error: ErrorBody


class ContractError(Exception):
    """Raised by contract helpers; the API maps it to the standard envelope."""

    def __init__(self, code: ErrorCode, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
