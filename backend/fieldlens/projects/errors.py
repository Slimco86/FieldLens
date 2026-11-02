"""Errors shared by the project-deletion path and the guards that reject work for a deleting project."""

from __future__ import annotations

from fieldlens.contracts.errors import ContractError, ErrorCode


def deleting_error() -> ContractError:
    return ContractError(
        ErrorCode.CONFLICT,
        "the project is being deleted; no new uploads or runs are accepted",
        409,
        {"reason": "project_deleting"},
    )
