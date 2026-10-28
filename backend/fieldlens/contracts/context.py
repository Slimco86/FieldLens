"""Selection/time contexts, cache keys and read bounds."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, RootModel, field_validator, model_validator

from .base import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    MAX_WINDOW_POINTS,
    ContractModel,
    UtcDatetime,
)
from .errors import ContractError, ErrorCode

# --- Time ---------------------------------------------------------------------------------


class InstantAsOf(ContractModel):
    kind: Literal["instant"] = "instant"
    instant: UtcDatetime
    """RFC 3339 timestamp with offset, normalized to UTC."""


class DayAsOf(ContractModel):
    kind: Literal["day"] = "day"
    day: date
    timezone: str = Field(min_length=1, description="Explicit IANA timezone for the query.")

    @field_validator("timezone")
    @classmethod
    def _iana(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise ValueError("timezone must be a valid IANA zone name") from exc
        return value


class AsOf(RootModel[Annotated[InstantAsOf | DayAsOf, Field(discriminator="kind")]]):
    """Discriminated historical query time."""


class TimePrecision(StrEnum):
    INSTANT = "instant"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


class SourceEventTime(ContractModel):
    """Source event time. Report/import/revision times are separate fields elsewhere."""

    literal: str = Field(min_length=1, description="Literal source text; never rewritten.")
    precision: TimePrecision
    timezone: str | None = Field(
        default=None, description="Known IANA zone; null stays unknown, never the query zone."
    )
    earliest_effective: UtcDatetime | None = None
    latest_effective: UtcDatetime | None = None

    @model_validator(mode="after")
    def _bounds(self) -> SourceEventTime:
        if (
            self.earliest_effective is not None
            and self.latest_effective is not None
            and self.earliest_effective > self.latest_effective
        ):
            raise ValueError("earliest_effective must be <= latest_effective")
        return self


# --- Contexts -----------------------------------------------------------------------------


class SelectedEntityType(StrEnum):
    FIELD = "field"
    WELL = "well"
    WELLBORE = "wellbore"
    COMPLETION = "completion"
    COMPONENT = "component"
    INTERVAL = "interval"


class SourceContext(ContractModel):
    """Source inspection: labeled observations only; no entity or as-of defaults."""

    kind: Literal["source"] = "source"
    project_id: UUID
    source_revision_id: UUID


class DraftContext(ContractModel):
    """Candidate review only."""

    kind: Literal["draft"] = "draft"
    project_id: UUID
    run_id: UUID
    revision_id: UUID


class QueryContext(ContractModel):
    """Published-model query. Entity fields are explicit nulls when no entity is selected."""

    kind: Literal["model"] = "model"
    project_id: UUID
    revision_id: UUID
    selected_entity_type: SelectedEntityType | None = None
    selected_entity_id: UUID | None = None
    as_of: AsOf | None = None

    @model_validator(mode="after")
    def _entity_pair(self) -> QueryContext:
        if (self.selected_entity_type is None) != (self.selected_entity_id is None):
            raise ValueError("selected_entity_type and selected_entity_id must both be set or null")
        return self


class EvidenceContext(
    RootModel[Annotated[SourceContext | DraftContext | QueryContext, Field(discriminator="kind")]]
):
    """Union of source, draft and model contexts. Endpoints declare the kinds they allow."""


ContextKind = Literal["source", "draft", "model"]


def require_context_kind(
    context: SourceContext | DraftContext | QueryContext, allowed: frozenset[ContextKind]
) -> None:
    """Reject a context kind an endpoint does not allow (e.g. source-only for engineering)."""
    if context.kind not in allowed:
        raise ContractError(
            ErrorCode.CONTEXT_KIND_NOT_ALLOWED,
            f"context kind '{context.kind}' is not allowed here; allowed: {sorted(allowed)}",
            status_code=409,
        )


def require_same_project(path_project_id: UUID, context: EvidenceContext) -> None:
    """Body/path project IDs must agree."""
    if context.root.project_id != path_project_id:
        raise ContractError(
            ErrorCode.NOT_FOUND, "context project does not match the requested project", 404
        )


def context_cache_key(
    context: EvidenceContext,
    *,
    query: dict[str, str | int | float | bool | None] | None = None,
    algorithm_version: str = "",
) -> str:
    """Deterministic key: project, kind, revisions, run, entity, as-of value/precision/zone,
    query parameters and algorithm/survey/index version. Content hashes alone never suffice."""
    payload = {
        "context": context.model_dump(mode="json"),
        "query": dict(sorted((query or {}).items())),
        "algorithm_version": algorithm_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


# --- Bounded reads -------------------------------------------------------------------------


class PageParams(ContractModel):
    """Cursor pagination. Out-of-range limits fail with 422; they are never clamped."""

    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    cursor: str | None = Field(default=None, max_length=2048)


class NumericWindowParams(ContractModel):
    """Display window. Invalid bounds fail rather than silently widening."""

    start: float
    end: float
    limit: int = Field(default=1000, ge=1, le=MAX_WINDOW_POINTS)

    @model_validator(mode="after")
    def _ordered(self) -> NumericWindowParams:
        if not self.start < self.end:
            raise ValueError("window start must be < end")
        return self


class PageInfo(ContractModel):
    limit: int = Field(ge=1, le=MAX_PAGE_LIMIT)
    next_cursor: str | None = None
