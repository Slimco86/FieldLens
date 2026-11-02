"""Storage-verification worker: one background thread, one heavy attempt at a time.

The stage re-reads every stored original and compares size and SHA-256. It does not parse
engineering content. Interrupted attempts are recovered from the persisted lease, never
reported as successful."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.evidence.root_guard import StorageRootGuard
from fieldlens.evidence.storage import BlobStore, VerifyOutcome
from fieldlens.extraction.runner import ExtractionRunner
from fieldlens.persistence.session import session_scope
from fieldlens.retrieval.embedder import EmbedderProvider
from fieldlens.retrieval.health import IndexHealth
from fieldlens.retrieval.indexer import IndexRunner

from . import repository as repo

logger = logging.getLogger(__name__)


class JobWorker:
    def __init__(
        self,
        factory: sessionmaker[Session],
        store: BlobStore,
        settings: Settings,
        embedders: EmbedderProvider | None = None,
    ) -> None:
        self._factory = factory
        self._store = store
        self._settings = settings
        self.owner = repo.new_owner()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.root_guard = StorageRootGuard(factory, store)
        self.extraction = ExtractionRunner(
            factory, store, settings, self.owner, self._is_dead_owner, self.root_guard
        )
        self.embedders = embedders or EmbedderProvider(settings)
        self.health = IndexHealth()
        self.indexing = IndexRunner(
            factory, settings, self.owner, self._is_dead_owner, self.embedders, self.health
        )

    # -- recovery ---------------------------------------------------------------------------
    def _is_dead_owner(self, owner: str) -> bool:
        host, _, rest = owner.partition(":")
        pid_text = rest.split(":", 1)[0]
        if host != socket.gethostname() or not pid_text.isdigit():
            return False
        pid = int(pid_text)
        if pid == os.getpid():
            # Known limitation: another live worker in this same process (different owner id)
            # is treated as dead; the app runs exactly one worker per process.
            return owner != self.owner
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def recover_once(self) -> list[UUID]:
        with session_scope(self._factory) as session:
            return repo.recover(session, self._is_dead_owner)

    # -- execution --------------------------------------------------------------------------
    def run_once(self) -> bool:
        """Recover, claim and process at most one job. Returns True when a job was handled."""
        self.recover_once()
        if not self.root_guard.serves_database():
            return False  # wrong storage root: leave the job for a process that can read it
        with session_scope(self._factory) as session:
            claim = repo.claim_next(session, self.owner, self._settings.job_lease_seconds)
        if claim is None:
            return False
        self._process(claim)
        return True

    def _process(self, claim: repo.Claim) -> None:
        lost = threading.Event()
        done = threading.Event()

        def beat() -> None:
            while not done.wait(self._settings.job_heartbeat_seconds):
                try:
                    with session_scope(self._factory) as session:
                        if not repo.heartbeat(session, claim, self._settings.job_lease_seconds):
                            lost.set()
                            return
                except Exception:  # transient DB error: keep trying until the lease lapses
                    logger.warning("heartbeat failed for job %s", claim.job_id)

        beater = threading.Thread(target=beat, name=f"job-heartbeat-{claim.job_id}", daemon=True)
        beater.start()
        try:
            self._verify_all(claim, lost)
        except repo.FenceLost:
            logger.warning("job %s attempt %s lost its fence", claim.job_id, claim.attempt_no)
        except Exception as exc:
            logger.error("job %s failed: %s", claim.job_id, type(exc).__name__)
            try:
                with session_scope(self._factory) as session:
                    repo.finalize_failed(session, claim, "verification_error", type(exc).__name__)
            except repo.FenceLost:
                pass
        finally:
            done.set()
            beater.join(timeout=5)

    def _verify_all(self, claim: repo.Claim, lost: threading.Event) -> None:
        with session_scope(self._factory) as session:
            docs = repo.pending_documents(session, claim)
        total = len(docs)
        processed = sum(1 for d in docs if d["storage_state"] != "pending_verification")
        for doc in docs:
            if lost.is_set():
                raise repo.FenceLost("lease lost")
            with session_scope(self._factory) as session:
                if repo.cancel_requested(session, claim):
                    repo.finalize_cancelled(session, claim)
                    return
            if doc["storage_state"] != "pending_verification":
                continue
            self._pause(lost)
            result = self._store.verify(doc["storage_key"], doc["sha256"], doc["size_bytes"])
            state = "stored" if result.outcome is VerifyOutcome.OK else "quarantined"
            detail = None if state == "stored" else f"verification_{result.outcome.value}"
            processed += 1
            with session_scope(self._factory) as session:
                repo.record_document(session, claim, doc["document_id"], state, detail)
                repo.set_progress(session, claim, processed, total)
        with session_scope(self._factory) as session:
            if repo.cancel_requested(session, claim):
                repo.finalize_cancelled(session, claim)
                return
            repo.publish(session, claim)

    def _pause(self, lost: threading.Event) -> None:
        """Test/diagnostic hook (``job_stage_delay_s``); zero in production."""
        remaining = self._settings.job_stage_delay_s
        while remaining > 0:
            if lost.is_set():
                raise repo.FenceLost("lease lost")
            step = min(0.1, remaining)
            time.sleep(step)
            remaining -= step

    # -- thread -----------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="fieldlens-jobs", daemon=True)
        self._thread.start()

    def _sweep_staging(self) -> None:
        try:
            removed = self._store.sweep_staging(self._settings.staging_max_age_s)
        except Exception as exc:
            logger.error("staging sweep error: %s", type(exc).__name__)
            return
        if removed:
            logger.info("removed %d abandoned staging directories", len(removed))

    def _loop(self) -> None:
        next_sweep = 0.0
        while not self._stop.is_set():
            if time.monotonic() >= next_sweep:
                self._sweep_staging()
                next_sweep = time.monotonic() + self._settings.staging_sweep_interval_s
            try:
                handled = self.run_once() or self.extraction.run_once() or self.indexing.run_once()
            except Exception as exc:
                logger.error("job loop error: %s", type(exc).__name__)
                handled = False
            if not handled:
                self._stop.wait(self._settings.job_poll_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=15)
            self._thread = None
