"""Write path for the agent activity log (what the TASK-036 harness calls).

Every write is one short transaction that locks the unit row, so step numbers stay total and
gapless under concurrency. Writes are fenced: ``start_unit`` returns a handle holding the fence
counter, and recovery, resume and finalize all move or check it, so a stale worker can never
append to or finalize a unit that a newer attempt owns. Steps carry a caller-supplied
``step_key``; replaying a key returns the stored step without a duplicate or double-counted usage.
The step_key convention is owned by the TASK-036 harness. A replay returns the stored step
WITHOUT comparing content, so reusing a key with different content is silently ignored.
Evidence locator free-text fields are redacted and cut to 200 characters (the step is flagged
``truncated``); oversized evidence raises ``EvidenceTooLarge``.

Usage (harness)::

    log = ActivityLog(factory)
    log.recover_interrupted()                     # once at startup: running -> interrupted
    h = log.start_unit(project_id, revision_id, "extract:doc42:v1", question)
    log.append_step(h, "tool_call", "read page 3", step_key="tool:1", tool_name="read_page",
                    outcome="ok", evidence=[link], usage=StepUsage(input_tokens=120))
    log.finalize(h, "succeeded", "completed")
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.contracts.activity import AgentStepKind, AgentStepOutcome, AgentUnitState
from fieldlens.contracts.evidence import EvidenceLink
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from .sanitize import QUESTION_LIMIT, SUMMARY_LIMIT, bound_text, sanitize_detail

MAX_STEPS = 200
MAX_REGULAR_STEPS = 190  # the last 10 are reserved for lifecycle marks (interrupt/resume)
MAX_EVIDENCE_LINKS = 8
MAX_EVIDENCE_BYTES = 12288
LOCATOR_TEXT_LIMIT = 200
LOCATOR_LIST_LIMIT = 20
# Free-text locator fields (contracts/evidence.py). Identity fields (document/revision ids,
# page, line numbers, sha256 hashes, kind) are never altered.
_LOCATOR_TEXT_FIELDS = (
    "table_id",
    "cell_id",
    "sheet",
    "cell_range",
    "namespace_uri",
    "element_path",
    "attribute_name",
    "column_name",
    "las_section",
    "las_mnemonic",
    "extractor_version",
)
STOP_PROCESS_INTERRUPTED = "process_interrupted"


class ActivityLogError(Exception):
    """Base class; messages never include payload text."""


class ScopeError(ActivityLogError):
    """Project/revision/document outside the unit's scope."""


class FenceLost(ActivityLogError):
    """The caller's attempt was superseded (recovery or a newer retry)."""


class UnitFinalized(ActivityLogError):
    """The unit is not running; it cannot be appended to or finalized again."""


class UnitConflict(ActivityLogError):
    """The unit is running under another attempt; recover it before retrying."""


class StepLimitExceeded(ActivityLogError):
    pass


class EvidenceTooLarge(ActivityLogError):
    """Serialized evidence links exceed the stored bound (never a raw database error)."""


@dataclass(frozen=True)
class UnitHandle:
    unit_id: UUID
    project_id: UUID
    fence: int
    resumed: bool = False


@dataclass(frozen=True)
class StepUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if (
            self.input_tokens < 0
            or self.cached_input_tokens < 0
            or self.output_tokens < 0
            or self.cost_usd < 0
        ):
            raise ActivityLogError("usage values must be non-negative")


@dataclass(frozen=True)
class StoredStep:
    step_id: UUID
    step_no: int
    created: bool
    """False when the step key already existed (idempotent replay)."""


def _lock_unit(s: Session, project_id: UUID, unit_id: UUID) -> Any:
    row = (
        s.execute(
            select(m.agent_work_unit)
            .where(
                m.agent_work_unit.c.project_id == project_id,
                m.agent_work_unit.c.unit_id == unit_id,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ScopeError("unit not found in project")
    return row


def _clean_evidence(links: list[EvidenceLink]) -> tuple[list[dict[str, Any]], bool]:
    """Dump links, redacting and bounding free-text locator fields; True when any was cut."""
    cut_any = False
    out: list[dict[str, Any]] = []
    for link in links:
        dumped = link.model_dump(mode="json")
        loc = dumped["locator"]
        for name in _LOCATOR_TEXT_FIELDS:
            if isinstance(loc.get(name), str):
                loc[name], cut = bound_text(loc[name], LOCATOR_TEXT_LIMIT)
                cut_any = cut_any or cut
        uids = loc.get("source_uids")
        if isinstance(uids, list):
            if len(uids) > LOCATOR_LIST_LIMIT:
                cut_any = True
            kept = []
            for uid in uids[:LOCATOR_LIST_LIMIT]:
                text, cut = bound_text(str(uid), LOCATOR_TEXT_LIMIT)
                kept.append(text)
                cut_any = cut_any or cut
            loc["source_uids"] = kept
        out.append(dumped)
    if len(json.dumps(out, ensure_ascii=False).encode()) > MAX_EVIDENCE_BYTES:
        raise EvidenceTooLarge("evidence links exceed the stored size bound; cite fewer or smaller")
    return out, cut_any


def _add_step(
    s: Session,
    unit: Any,
    kind: str,
    summary: str,
    *,
    step_key: str,
    outcome: str | None = None,
    tool_name: str | None = None,
    detail: dict[str, Any] | None = None,
    evidence: list[EvidenceLink] | None = None,
    usage: StepUsage | None = None,
    limit: int = MAX_REGULAR_STEPS,
) -> StoredStep:
    existing = s.execute(
        select(m.agent_step.c.step_id, m.agent_step.c.step_no).where(
            m.agent_step.c.unit_id == unit["unit_id"], m.agent_step.c.step_key == step_key
        )
    ).first()
    if existing is not None:
        return StoredStep(existing.step_id, existing.step_no, False)
    if unit["step_count"] >= min(limit, MAX_STEPS):
        raise StepLimitExceeded("step limit reached")
    text, cut = bound_text(summary or "(no summary)", SUMMARY_LIMIT)
    clean, detail_cut = sanitize_detail(detail)
    links = evidence or []
    if len(links) > MAX_EVIDENCE_LINKS:
        raise ScopeError("too many evidence links")
    _check_evidence(s, unit, links)
    stored_links, links_cut = _clean_evidence(links)
    step_no = unit["step_count"] + 1
    step_id = s.execute(
        insert(m.agent_step)
        .values(
            project_id=unit["project_id"],
            unit_id=unit["unit_id"],
            step_no=step_no,
            step_key=step_key,
            kind=kind,
            outcome=outcome,
            tool_name=tool_name[:64] if tool_name else None,
            summary=text,
            detail=clean,
            evidence=stored_links,
            truncated=cut or detail_cut or links_cut,
        )
        .returning(m.agent_step.c.step_id)
    ).scalar_one()
    u = usage or StepUsage()
    s.execute(
        update(m.agent_work_unit)
        .where(m.agent_work_unit.c.unit_id == unit["unit_id"])
        .values(
            step_count=step_no,
            tool_call_count=m.agent_work_unit.c.tool_call_count + int(kind == "tool_call"),
            candidate_count=m.agent_work_unit.c.candidate_count + int(kind == "candidate"),
            input_tokens=m.agent_work_unit.c.input_tokens + u.input_tokens,
            cached_input_tokens=m.agent_work_unit.c.cached_input_tokens + u.cached_input_tokens,
            output_tokens=m.agent_work_unit.c.output_tokens + u.output_tokens,
            cost_usd=m.agent_work_unit.c.cost_usd + u.cost_usd,
            updated_at=func.now(),
        )
    )
    return StoredStep(step_id, step_no, True)


def _check_evidence(s: Session, unit: Any, links: list[EvidenceLink]) -> None:
    for link in links:
        if link.source_revision_id not in (None, unit["source_revision_id"]):
            raise ScopeError("evidence is outside the unit's source revision")
        if link.document_id is None:
            continue
        found = s.execute(
            select(m.source_revision_document.c.document_id).where(
                m.source_revision_document.c.project_id == unit["project_id"],
                m.source_revision_document.c.source_revision_id == unit["source_revision_id"],
                m.source_revision_document.c.document_id == link.document_id,
            )
        ).first()
        if found is None:
            raise ScopeError("evidence document is outside the project/revision scope")


def _fenced(s: Session, handle: UnitHandle) -> Any:
    unit = _lock_unit(s, handle.project_id, handle.unit_id)
    if unit["fence_counter"] != handle.fence:
        raise FenceLost("attempt superseded")
    if unit["state"] != "running":
        raise UnitFinalized(f"unit is {unit['state']}")
    return unit


class ActivityLog:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def start_unit(
        self, project_id: UUID, source_revision_id: UUID, unit_key: str, question: str
    ) -> UnitHandle:
        """Create the unit, or resume an interrupted one with the same key (fence + 1)."""
        if not 1 <= len(unit_key) <= 200:
            raise ActivityLogError("unit_key must be 1..200 characters")
        for attempt in range(2):
            try:
                with session_scope(self._factory) as s:
                    return self._start(s, project_id, source_revision_id, unit_key, question)
            except IntegrityError:
                if attempt:  # lost the insert race twice: surface as a conflict
                    raise UnitConflict("unit could not be created") from None
        raise UnitConflict("unit could not be created")  # pragma: no cover

    def _start(
        self, s: Session, project_id: UUID, revision_id: UUID, unit_key: str, question: str
    ) -> UnitHandle:
        t = m.agent_work_unit
        row = (
            s.execute(
                select(t)
                .where(t.c.project_id == project_id, t.c.unit_key == unit_key)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if row is None:
            owned = s.execute(
                select(m.source_revision.c.source_revision_id).where(
                    m.source_revision.c.project_id == project_id,
                    m.source_revision.c.source_revision_id == revision_id,
                )
            ).first()
            if owned is None:
                raise ScopeError("source revision not found in project")
            text, _ = bound_text(question.strip() or "(no question)", QUESTION_LIMIT)
            unit_id = s.execute(
                insert(t)
                .values(
                    project_id=project_id,
                    source_revision_id=revision_id,
                    unit_key=unit_key,
                    question=text,
                )
                .returning(t.c.unit_id)
            ).scalar_one()
            return UnitHandle(unit_id, project_id, 1)
        if row["source_revision_id"] != revision_id:
            raise ScopeError("unit key belongs to a different source revision")
        if row["state"] == "running":
            raise UnitConflict("unit is running under another attempt; recover it first")
        if row["state"] != "interrupted":
            raise UnitFinalized(f"unit already {row['state']}")
        fence = row["fence_counter"] + 1
        s.execute(
            update(t)
            .where(t.c.unit_id == row["unit_id"])
            .values(
                state="running",
                stop_reason=None,
                stop_detail=None,
                finished_at=None,
                fence_counter=fence,
                attempt_count=row["attempt_count"] + 1,
                updated_at=func.now(),
            )
        )
        refreshed = _lock_unit(s, project_id, row["unit_id"])
        _add_step(
            s,
            refreshed,
            "lifecycle",
            f"resumed (attempt {row['attempt_count'] + 1})",
            step_key=f"lifecycle:resumed:{fence}",
            limit=MAX_STEPS,
        )
        return UnitHandle(row["unit_id"], project_id, fence, resumed=True)

    def append_step(
        self,
        handle: UnitHandle,
        kind: AgentStepKind | str,
        summary: str,
        *,
        step_key: str,
        outcome: AgentStepOutcome | str | None = None,
        tool_name: str | None = None,
        detail: dict[str, Any] | None = None,
        evidence: list[EvidenceLink] | None = None,
        usage: StepUsage | None = None,
    ) -> StoredStep:
        """Append one step (or return the stored one when ``step_key`` was already written)."""
        kind_v = AgentStepKind(kind).value
        outcome_v = AgentStepOutcome(outcome).value if outcome is not None else None
        if kind_v == "lifecycle":
            raise ActivityLogError("lifecycle steps are written by the log itself")
        if not 1 <= len(step_key) <= 120:
            raise ActivityLogError("step_key must be 1..120 characters")
        if kind_v == "tool_call" and not tool_name:
            raise ActivityLogError("tool_call steps need a tool_name")
        with session_scope(self._factory) as s:
            unit = _fenced(s, handle)
            return _add_step(
                s,
                unit,
                kind_v,
                summary,
                step_key=step_key,
                outcome=outcome_v,
                tool_name=tool_name,
                detail=detail,
                evidence=evidence,
                usage=usage,
            )

    def finalize(
        self,
        handle: UnitHandle,
        state: AgentUnitState | str,
        stop_reason: str,
        stop_detail: str | None = None,
    ) -> None:
        """Move a running unit to a final state exactly once (a second call raises)."""
        state_v = AgentUnitState(state).value
        if state_v == "running":
            raise ActivityLogError("finalize needs a final state")
        reason, _ = bound_text(stop_reason.strip() or "unspecified", 64)
        detail = bound_text(stop_detail, 600)[0] if stop_detail else None
        with session_scope(self._factory) as s:
            _fenced(s, handle)
            s.execute(
                update(m.agent_work_unit)
                .where(m.agent_work_unit.c.unit_id == handle.unit_id)
                .values(
                    state=state_v,
                    stop_reason=reason,
                    stop_detail=detail,
                    finished_at=func.now(),
                    updated_at=func.now(),
                )
            )

    def recover_interrupted(self, project_id: UUID | None = None) -> list[UUID]:
        """After a restart: every running unit becomes ``interrupted`` and its fence advances.

        Never marks anything successful and never re-runs work. Returns the unit ids changed.
        """
        t = m.agent_work_unit
        with session_scope(self._factory) as s:
            query = select(t.c.project_id, t.c.unit_id).where(t.c.state == "running")
            if project_id is not None:
                query = query.where(t.c.project_id == project_id)
            targets = s.execute(query.order_by(t.c.unit_id)).all()
        recovered: list[UUID] = []
        for pid, uid in targets:
            with session_scope(self._factory) as s:
                unit = _lock_unit(s, pid, uid)
                if unit["state"] != "running":
                    continue
                fence = unit["fence_counter"] + 1
                _add_step(
                    s,
                    unit,
                    "lifecycle",
                    "interrupted: the process stopped before this unit finished",
                    step_key=f"lifecycle:interrupted:{fence}",
                    outcome="error",
                    limit=MAX_STEPS,
                )
                s.execute(
                    update(t)
                    .where(t.c.unit_id == uid)
                    .values(
                        state="interrupted",
                        stop_reason=STOP_PROCESS_INTERRUPTED,
                        fence_counter=fence,
                        finished_at=func.now(),
                        updated_at=func.now(),
                    )
                )
                recovered.append(uid)
        return recovered
