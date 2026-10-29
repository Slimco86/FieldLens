"""Project lifecycle request/response DTOs. The stored record is :class:`identity.Project`."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, Field, model_validator

from .base import ContractModel
from .context import PageInfo
from .identity import Project


def _storable(value: Any) -> Any:
    """Reject text PostgreSQL/UTF-8 cannot store (NUL, lone surrogates) before any DB access."""
    if isinstance(value, str) and any(ch == "\x00" or "\ud800" <= ch <= "\udfff" for ch in value):
        raise ValueError("text must not contain NUL or unpaired surrogate characters")
    return value


def _trim(value: Any) -> Any:
    return _storable(value).strip() if isinstance(value, str) else value


ProjectName = Annotated[str, BeforeValidator(_trim), Field(min_length=1, max_length=120)]
"""Server-trimmed name: 1..120 characters after trimming."""

ProjectDescription = Annotated[str, BeforeValidator(_storable), Field(max_length=4000)]


class ProjectCreate(ContractModel):
    """Create request. Identity, timestamps and revision pointers are server-owned."""

    name: ProjectName
    description: ProjectDescription = ""


class ProjectUpdate(ContractModel):
    """Partial edit. Omitted fields are unchanged; explicit nulls are rejected."""

    name: ProjectName | None = None
    description: ProjectDescription | None = None

    @model_validator(mode="after")
    def _non_empty_and_no_nulls(self) -> ProjectUpdate:
        sent = self.model_fields_set
        if not sent:
            raise ValueError("at least one of name or description is required")
        if ("name" in sent and self.name is None) or (
            "description" in sent and self.description is None
        ):
            raise ValueError("name and description cannot be null")
        return self


class ProjectPage(ContractModel):
    """One page of projects, newest first."""

    items: list[Project]
    page: PageInfo
