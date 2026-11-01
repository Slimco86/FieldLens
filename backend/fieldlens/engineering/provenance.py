"""Calculation-entry marker guard (AX-13): model proposals never feed a calculation.

A record or object is a model proposal when it carries ``evidence_class == "model_proposal"``,
an ``extraction_method`` of ``model_proposal``/``model_read``, or ``validation_state ==
"unverified"``. Calculation entry points call :func:`is_model_proposal` and reject such input;
deterministic parsed values are never marked this way."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MODEL_METHODS = frozenset({"model_proposal", "model_read"})
MARKER_REASON = "model_proposal_not_allowed"


def _get(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def is_model_proposal(item: Any) -> bool:
    return (
        _get(item, "evidence_class") == "model_proposal"
        or _get(item, "extraction_method") in MODEL_METHODS
        or _get(item, "method") in MODEL_METHODS
        or _get(item, "validation_state") == "unverified"
    )
