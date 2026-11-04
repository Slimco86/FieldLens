"""Chat turn runner: worker threads claim queued turns, run them and write one terminal state.

* a turn is claimed with a lease (heartbeat while running) and every terminal write is fenced by
  the lease owner, so a recovered/cancelled/purged turn is never overwritten by a late worker;
* a cancel request is polled and turned into a cooperative cancel of the provider/tool loop;
* a turn is never resumed after a restart (that would call the provider twice): it becomes
  ``failed``/``interrupted`` and the user asks again.
"""

from __future__ import annotations

import logging
import threading
from uuid import UUID

from sqlalchemy.exc import OperationalError

from fieldlens.assistant.provider import CancelToken
from fieldlens.chat import repository as repo
from fieldlens.chat.executor import TurnOutcome, execute_turn, failure_for
from fieldlens.chat.runtime import ChatRuntime
from fieldlens.contracts.chat import ChatUsage
from fieldlens.jobs.repository import new_owner
from fieldlens.processing.runtime import is_dead_owner

logger = logging.getLogger(__name__)
HEARTBEAT_S = 1.0


class ChatRunner:
    def __init__(self, runtime: ChatRuntime, *, workers: int = 2, poll_s: float = 0.5) -> None:
        self._rt = runtime
        self._workers = workers
        self._poll_s = poll_s
        self.owner = new_owner()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # -- lifecycle ---------------------------------------------------------------------------
    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        self.recover_once()
        for i in range(self._workers):
            t = threading.Thread(target=self._loop, name=f"chat-turn-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
        self._threads.clear()

    def recover_once(self) -> list[UUID]:
        try:
            return list(repo.recover(self._rt.factory, lambda o: is_dead_owner(o, self.owner)))
        except OperationalError:
            logger.warning("chat recovery skipped: storage unavailable")
            return []

    # -- work --------------------------------------------------------------------------------
    def _loop(self) -> None:
        idle_ticks = 0
        while not self._stop.is_set():
            try:
                if self.run_one():
                    idle_ticks = 0
                    continue
            except OperationalError:
                logger.warning("chat runner: storage unavailable")
            except Exception:  # noqa: BLE001 - the loop must survive any single failure
                logger.exception("chat runner iteration failed")
            idle_ticks += 1
            if idle_ticks % 60 == 0:
                self.recover_once()
            self._stop.wait(self._poll_s)

    def run_one(self) -> bool:
        """Claim and run one turn. Returns False when nothing was queued."""
        rt = self._rt
        claim = repo.claim_next(rt.factory, self.owner, rt.limits.lease_s)
        if claim is None:
            return False
        cancel = CancelToken()
        done = threading.Event()
        watcher = threading.Thread(
            target=self._watch, args=(claim.turn_id, cancel, done), name="chat-watch", daemon=True
        )
        watcher.start()
        try:
            outcome = execute_turn(rt, claim, cancel)
        except Exception as exc:  # noqa: BLE001 - never leave a turn running
            logger.exception("chat turn %s crashed", claim.turn_id)
            state, failure = failure_for(exc)
            outcome = TurnOutcome(state, failure=failure, usage=ChatUsage())
        finally:
            done.set()
            watcher.join(timeout=2)
        repo.finalize(
            rt.factory,
            claim,
            self.owner,
            state=outcome.state,
            answer=outcome.answer,
            failure=outcome.failure,
            usage=outcome.usage,
            tool_calls=outcome.tool_calls,
        )
        return True

    def _watch(self, tid: UUID, cancel: CancelToken, done: threading.Event) -> None:
        while not done.wait(HEARTBEAT_S):
            try:
                if not repo.extend_lease(
                    self._rt.factory, tid, self.owner, self._rt.limits.lease_s
                ):
                    cancel.cancel()  # the turn is no longer ours (recovered/purged): stop work
                    return
                if repo.cancel_requested(self._rt.factory, tid):
                    cancel.cancel()
            except OperationalError:
                continue
