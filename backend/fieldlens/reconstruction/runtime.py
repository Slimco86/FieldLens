"""Composition of the reconstruction package (stage executors and runner)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.jobs.repository import new_owner
from fieldlens.processing.runtime import is_dead_owner
from fieldlens.reconstruction.runner import ReconstructionRunner
from fieldlens.reconstruction.stages import StageExecutor, default_executors


@dataclass
class ReconstructionRuntime:
    executors: list[StageExecutor]
    runner: ReconstructionRunner


def build_runtime(
    factory: sessionmaker[Session],
    settings: Settings,
    *,
    executors: Sequence[StageExecutor] | None = None,
) -> ReconstructionRuntime:
    """S2 and S3 are ``not_available`` by default; no executor here can make a live call."""
    chosen = list(executors) if executors is not None else default_executors(settings)
    owner = new_owner()
    runner = ReconstructionRunner(
        factory, settings, chosen, owner, lambda other: is_dead_owner(other, owner)
    )
    return ReconstructionRuntime(chosen, runner)
