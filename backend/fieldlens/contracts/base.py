"""Shared base types for closed FieldLens contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, JsonValue

MAX_PAGE_LIMIT = 200
DEFAULT_PAGE_LIMIT = 50
MAX_WINDOW_POINTS = 5000


class ContractModel(BaseModel):
    """Closed model: unknown fields and non-finite floats are rejected."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=False,
        use_attribute_docstrings=True,
    )


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]
"""RFC 3339 timestamp with an offset, normalized to UTC."""


def _finite_json(value: JsonValue) -> JsonValue:
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("JSON metadata numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            _finite_json(item)
    elif isinstance(value, list):
        for item in value:
            _finite_json(item)
    return value


FiniteJsonValue = Annotated[JsonValue, AfterValidator(_finite_json)]
