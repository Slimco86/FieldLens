"""The only output the model may produce: a closed, bounded JSON object (AX-4).

Anything else (extra fields, tool-call-like text, oversized or non-JSON output) is a failed
attempt, never a partial success. This is an internal wire schema; the public DTO is
``contracts.candidates``."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_OUTPUT_BYTES = 65_536
MAX_CANDIDATES = 40
MAX_FLAT = 80


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class WireLocator(_Closed):
    document_id: UUID
    page: int | None = Field(default=None, ge=1, le=100_000)
    line_start: int | None = Field(default=None, ge=1, le=100_000_000)
    line_end: int | None = Field(default=None, ge=1, le=100_000_000)


Subject = dict[Annotated[str, Field(max_length=32)], Annotated[str, Field(max_length=MAX_FLAT)]]


class WireMeasurement(_Closed):
    kind: Literal["measurement"]
    attribute_key: str = Field(max_length=80)
    value_text: str = Field(min_length=1, max_length=200)
    unit: str | None = Field(default=None, max_length=32)
    depth_reference: Literal["MD", "TVD", "TVDSS"] | None = None
    quote: str | None = Field(default=None, max_length=400)
    locator: WireLocator
    subject: Subject = Field(default_factory=dict, max_length=4)
    effective_time_text: str | None = Field(default=None, max_length=80)
    crs_text: str | None = Field(default=None, max_length=120)


class WirePageItem(_Closed):
    kind: Literal["page_read"]
    item_type: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=120)
    sizes_text: list[Annotated[str, Field(max_length=60)]] = Field(
        default_factory=list, max_length=8
    )
    depth_text: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=300)
    quote: str | None = Field(default=None, max_length=400)
    locator: WireLocator
    subject: Subject = Field(default_factory=dict, max_length=4)


WireCandidate = Annotated[WireMeasurement | WirePageItem, Field(discriminator="kind")]


class WireOutput(_Closed):
    candidates: list[WireCandidate] = Field(max_length=MAX_CANDIDATES)


class OutputRejected(Exception):
    """The model output is not an acceptable typed object (reason is a stable code)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_output(text: str) -> WireOutput:
    raw = text.strip()
    if len(raw.encode("utf-8", "replace")) > MAX_OUTPUT_BYTES:
        raise OutputRejected("output_oversized")
    if not raw.startswith("{"):
        raise OutputRejected("malformed_output")
    try:
        json.loads(raw)
    except ValueError as exc:
        raise OutputRejected("malformed_output") from exc
    try:
        return WireOutput.model_validate_json(raw)
    except ValidationError as exc:
        raise OutputRejected("schema_invalid") from exc


def candidate_key(candidate: WireMeasurement | WirePageItem) -> str:
    """Stable identity of a proposal inside one unit, so a fenced retry never duplicates it."""
    body = candidate.model_dump(mode="json", exclude_none=True)
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:32]
