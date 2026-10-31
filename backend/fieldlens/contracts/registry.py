"""Documented registry of every public contract DTO.

The registry is the single source for the generated TypeScript client: the OpenAPI document
produced by :func:`fieldlens.app.create_app` merges these schemas into ``components.schemas``,
so DTOs are exported without inventing business endpoints. Add a model here (and review the
regenerated client) when a contract is introduced; ``test_registry_complete`` fails if a public
``ContractModel`` subclass is missing.

Schemas are exported in *serialization* mode: every field with a default is present in a
response, so the TS client does not treat server-populated fields as optional.
"""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from . import (
    activity,
    context,
    errors,
    evidence,
    extraction,
    identity,
    imports,
    projects,
    quality,
    retrieval,
    series,
    system,
)
from .base import ContractModel

REF_TEMPLATE = "#/components/schemas/{model}"

_MODULES = (
    identity,
    evidence,
    context,
    quality,
    errors,
    system,
    projects,
    imports,
    extraction,
    activity,
    retrieval,
    series,
)


def public_models() -> list[type[BaseModel]]:
    """Public DTO classes (non-underscore, defined in a contract module), sorted by name."""
    found: dict[str, type[BaseModel]] = {}
    for module in _MODULES:
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseModel)
                and obj.__module__ == module.__name__
                and not name.startswith("_")
                and obj is not ContractModel
            ):
                found[name] = obj
    return [found[n] for n in sorted(found)]


def export_component_schemas() -> dict[str, Any]:
    """JSON Schema ``$defs`` for every public DTO, keys sorted for deterministic output."""
    models = public_models()
    _, schema = models_json_schema(
        [(m, "serialization") for m in models], ref_template=REF_TEMPLATE
    )
    defs: dict[str, Any] = schema.get("$defs", {})
    return {k: defs[k] for k in sorted(defs)}
