"""Composition of the processing package (provider, step, page counter, runner)."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.evidence.root_guard import StorageRootGuard
from fieldlens.evidence.storage import BlobStore
from fieldlens.jobs.repository import new_owner
from fieldlens.processing.runner import ProcessingRunner
from fieldlens.processing.service import PageCounter
from fieldlens.processing.steps import PageProvider, ProcessingStep, StubProvider, StubStep


@dataclass
class ProcessingRuntime:
    counter: PageCounter
    provider: PageProvider
    step: ProcessingStep
    runner: ProcessingRunner


def is_dead_owner(owner: str, own: str) -> bool:
    """Same-host owner whose process is gone; another owner id in this process counts as dead."""
    host, _, rest = owner.partition(":")
    pid_text = rest.split(":", 1)[0]
    if host != socket.gethostname() or not pid_text.isdigit():
        return False
    pid = int(pid_text)
    if pid == os.getpid():
        return owner != own
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def build_runtime(
    factory: sessionmaker[Session],
    store: BlobStore,
    settings: Settings,
    *,
    provider: PageProvider | None = None,
    step: ProcessingStep | None = None,
) -> ProcessingRuntime:
    """Stub provider and stub step by default: a settings value cannot select a live provider."""
    counter = PageCounter(store)
    chosen_provider = provider or StubProvider(settings)
    chosen_step = step or StubStep()
    owner = new_owner()
    runner = ProcessingRunner(
        factory,
        counter,
        settings,
        chosen_provider,
        chosen_step,
        owner,
        lambda other: is_dead_owner(other, owner),
        StorageRootGuard(factory, store),
    )
    return ProcessingRuntime(counter, chosen_provider, chosen_step, runner)
