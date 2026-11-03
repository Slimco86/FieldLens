"""The model step: block -> prompt -> provider -> parse -> server-side validation -> persist.

One ``WorkUnit`` per call (budget reserved and settled by the existing ledger). The proposer
never changes identity; it only stores ``pending``/``blocked`` proposals for review."""

from __future__ import annotations

import dataclasses
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.errors import (
    AssistantError,
    BudgetExceeded,
    ProviderMalformed,
    ProviderRefusal,
    ProviderTimeout,
    ProviderTruncated,
    ProviderUnavailable,
    RequestCancelled,
    RequestLimitExceeded,
)
from fieldlens.assistant.provider import CancelToken, Pricing, Provider
from fieldlens.assistant.runner import RequestLimits, WorkUnit
from fieldlens.contracts.merge_proposals import MergeProposalEstimate, MergeProposalRun

from . import guards, service
from .blocking import Block, Dataset, MemberCandidate, build_dataset
from .evidence import SourceText
from .prompt import PROMPT_VERSION, OutputError, block_labels, build_messages, parse_output
from .tables import merge_proposal_run as run_table
from .validation import Dropped, ValidProposal, validate_group

log = logging.getLogger(__name__)

MAX_BLOCKS_PER_CALL = 4
MAX_CALLS = 3
OUTPUT_BASE_TOKENS = 8192
OUTPUT_TOKENS_PER_BLOCK = 1024
OUTPUT_FREE_BLOCKS = 2
CONTEXT_WELLBORES = 40


def output_bound(configured: int, blocks: int) -> int:
    """Output tokens for a call of ``blocks`` blocks: reasoning plus a JSON group per ambiguous
    pair must fit. Never below the configured bound; the truncation retry doubles it (capped)."""
    extra = max(blocks - OUTPUT_FREE_BLOCKS, 0) * OUTPUT_TOKENS_PER_BLOCK
    return configured + extra


@dataclass(frozen=True)
class PlanExplanation:
    """Why the S3 stage will or will not call the model (shown in the stage message)."""

    kind: str  # will_run | recheck | none_found | reused | no_candidates
    text: str


@dataclass(frozen=True)
class ProposerConfig:
    period_id: UUID
    pricing_id: UUID
    pricing: Pricing
    model: str
    limits: RequestLimits = field(
        default_factory=lambda: RequestLimits(
            max_attempts=2,
            max_tool_calls=0,
            deadline_s=240.0,
            max_output_tokens=OUTPUT_BASE_TOKENS,
            max_reserved_usd=Decimal("0.60"),
        )
    )
    effort: Any = "medium"
    """TASK-086: ``medium`` gives room to judge ambiguous pairs (survey matches only on station
    count/MD range); the bound (8192 + 1024 per block beyond 2) covers reasoning plus JSON, and the
    single truncation retry (``minimal`` effort, doubled bound) shares the reservation."""
    max_blocks_per_call: int = MAX_BLOCKS_PER_CALL
    max_calls: int = MAX_CALLS


TRUNCATED_MESSAGE = "The model ran out of output space; try again (a retry was already attempted)"


def failure_text(reason: str) -> str:
    """Readable text for a stable failure code (the code itself stays the identifier)."""
    return TRUNCATED_MESSAGE if reason == "output_truncated" else reason


def failure_reason(exc: BaseException) -> str:
    if isinstance(exc, ProviderRefusal):
        return "provider_refused"
    if isinstance(exc, ProviderTruncated):
        return "output_truncated"
    if isinstance(exc, ProviderMalformed | OutputError):
        return "malformed_output"
    if isinstance(exc, ProviderTimeout):
        return "provider_timeout"
    if isinstance(exc, RequestCancelled):
        return "request_cancelled"
    if isinstance(exc, BudgetExceeded):
        return "budget_exhausted"
    if isinstance(exc, RequestLimitExceeded):
        return "budget_exhausted" if exc.limit == "reserved_cost" else f"limit_{exc.limit}"
    if isinstance(exc, ProviderUnavailable):
        return "provider_unavailable"
    if isinstance(exc, AssistantError):
        return str(exc.code)
    return "internal_error"


class MergeProposer:
    def __init__(
        self,
        factory: sessionmaker[Session],
        ledger: BudgetLedger,
        provider: Provider,
        config: ProposerConfig,
        source: SourceText,
    ) -> None:
        self._factory = factory
        self._ledger = ledger
        self._provider = provider
        self._config = config
        self._source = source

    def _chunks(self, blocks: list[Block]) -> list[list[Block]]:
        n = self._config.max_blocks_per_call
        return [blocks[i : i + n] for i in range(0, len(blocks), n)]

    def _todo(
        self, session: Session, project_id: UUID, ds: Dataset
    ) -> tuple[list[Block], set[tuple[str, str, str]]]:
        """Blocks that still need a model call, decided BEFORE any call (D1).

        A pair that already has a pending/blocked/accepted proposal is not sent again, a block
        with no remaining candidate is dropped, and an unchanged dataset that a previous run of
        this model and prompt evaluated completely (nothing deferred) needs no call at all."""
        taken = service.taken_pairs(session, project_id)
        if self._evaluated(session, project_id, ds) is not None and ds.deferred_blocks == 0:
            return [], taken
        todo: list[Block] = []
        for b in ds.blocks:
            members: list[MemberCandidate] = [
                c for c in b.members if (b.target.key, c.party.kind, c.party.key) not in taken
            ]
            if members:
                todo.append(
                    Block(b.target, b.target_documents, members, b.allow_short_target, b.family)
                )
        return todo, taken

    def _run_row(self, session: Session, project_id: UUID, *, empty_only: bool = False) -> Any:
        q = select(
            run_table.c.run_id,
            run_table.c.created_at,
            run_table.c.blocks,
            run_table.c.proposals_created,
            run_table.c.dataset_fingerprint,
            run_table.c.prompt_version,
            run_table.c.guard_version,
            run_table.c.model_id,
            run_table.c.deferred_blocks,
        ).where(
            run_table.c.project_id == project_id,
            run_table.c.state == "succeeded",
            run_table.c.deferred_blocks == 0,
        )
        if empty_only:
            q = q.where(run_table.c.proposals_created == 0)
        return session.execute(q.order_by(run_table.c.created_at.desc()).limit(1)).first()

    def _evaluated(self, session: Session, project_id: UUID, ds: Dataset) -> Any:
        """A succeeded, fully evaluated run of exactly this state: same identity inputs, candidate
        evidence (plan fingerprint), guard version, model and prompt version (A-3)."""
        return session.execute(
            select(run_table.c.run_id, run_table.c.created_at, run_table.c.blocks)
            .where(
                run_table.c.project_id == project_id,
                run_table.c.state == "succeeded",
                run_table.c.dataset_fingerprint == ds.plan_fingerprint,
                run_table.c.model_id == self._config.model,
                run_table.c.prompt_version == PROMPT_VERSION,
                run_table.c.guard_version == guards.GUARD_VERSION,
                run_table.c.deferred_blocks == 0,
            )
            .order_by(run_table.c.created_at.desc())
            .limit(1)
        ).first()

    def explain(self, project_id: UUID) -> PlanExplanation:
        """Plain reason for the plan: distinguishes "the model found none" from "reused" (A-3)."""
        with self._factory() as s:
            ds = build_dataset(s, project_id)
            todo, taken = self._todo(s, project_id, ds)
            done = self._evaluated(s, project_id, ds)
            empty = self._run_row(s, project_id, empty_only=True)
            n_pairs = sum(len(b.members) for b in ds.blocks)
        if not ds.blocks:
            return PlanExplanation("no_candidates", "no wellbore names need matching")
        if todo:
            if empty is not None and done is None:
                changed = [
                    label
                    for label, differs in (
                        (
                            "candidate evidence or wellbore names",
                            empty.dataset_fingerprint != ds.plan_fingerprint,
                        ),
                        ("guard rules", empty.guard_version != guards.GUARD_VERSION),
                        ("model prompt", empty.prompt_version != PROMPT_VERSION),
                        ("model", empty.model_id != self._config.model),
                    )
                    if differs
                ]
                return PlanExplanation(
                    "recheck",
                    "asking the model again: the last run found no matches, but "
                    + (", ".join(changed) or "the inputs")
                    + " changed since",
                )
            return PlanExplanation("will_run", "new wellbore names or evidence to review")
        if done is not None and done.blocks and not taken:
            return PlanExplanation(
                "none_found",
                f"the model reviewed {done.blocks} name group(s) on {done.created_at:%Y-%m-%d} "
                "and found no matches; names, survey evidence, guard rules and prompt are "
                "unchanged, so it was not asked again",
            )
        if done is not None:
            return PlanExplanation(
                "reused",
                f"earlier results were reused: the model already reviewed these "
                f"{done.blocks} name group(s) on {done.created_at:%Y-%m-%d} and its proposals "
                "are stored; names, survey evidence, guard rules and prompt are unchanged",
            )
        return PlanExplanation(
            "reused",
            f"earlier results were reused: all {n_pairs} candidate pair(s) already have a "
            "proposal or a decision",
        )

    def estimate(self, project_id: UUID) -> MergeProposalEstimate:
        with self._factory() as s:
            ds = build_dataset(s, project_id)
            todo, _ = self._todo(s, project_id, ds)
        chunks = self._chunks(todo)[: self._config.max_calls]
        sent = sum(len(c) for c in chunks)
        per = self._config.limits.max_reserved_usd
        return MergeProposalEstimate(
            blocks=sent,
            deferred_blocks=ds.deferred_blocks + len(todo) - sent,
            calls=len(chunks),
            max_reserved_usd_per_call=per,
            upper_bound_usd=per * len(chunks),
            dataset_fingerprint=ds.fingerprint,
            provider_configured=True,
        )

    def run(self, project_id: UUID, cancel: CancelToken | None = None) -> MergeProposalRun:
        cancel = cancel or CancelToken()
        started = datetime.now(UTC)
        run_id = uuid4()
        with self._factory() as s:
            service.require_project(s, project_id)
            ds = build_dataset(s, project_id)
            todo, taken = self._todo(s, project_id, ds)
        chunks = self._chunks(todo)
        deferred = ds.deferred_blocks + sum(len(c) for c in chunks[self._config.max_calls :])
        chunks = chunks[: self._config.max_calls]
        resolved_keys = set(ds.resolved)
        proposals: list[ValidProposal] = []
        drops: Counter[str] = Counter()
        calls: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            if cancel.cancelled:
                calls.append(self._failed(index, len(chunk), "request_cancelled", 0, None))
                continue
            self._call(
                project_id, run_id, index, chunk, ds.merges, resolved_keys, taken, cancel,
                proposals, drops, calls, sorted(ds.resolved),
            )  # fmt: skip
        ok = sum(1 for c in calls if c["outcome"] == "ok")
        if not chunks:
            state, reason = "no_candidates", None
        elif ok == len(calls):
            state, reason = "succeeded", None
        elif ok:
            state, reason = "partial", next(c["reason"] for c in calls if c["outcome"] == "failed")
        else:
            state, reason = "failed", calls[0]["reason"]
        with self._factory.begin() as s:
            stored = service.store_run(
                s,
                project_id,
                state=state,
                reason=reason,
                model_id=self._config.model,
                prompt_version=PROMPT_VERSION,
                fingerprint=ds.fingerprint,
                run_fingerprint=ds.plan_fingerprint,
                blocks=sum(len(c) for c in chunks),
                deferred=deferred,
                proposals=proposals,
                drops=drops,
                calls=calls,
                created_at=started,
            )
        with self._factory() as s:
            return service.get_run(s, project_id, stored)

    @staticmethod
    def _failed(
        index: int,
        blocks: int,
        reason: str,
        attempts: int,
        cost: Decimal | None,
        tokens: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        return {
            "index": index,
            "outcome": "failed",
            "reason": reason,
            "blocks": blocks,
            "attempts": attempts,
            "input_tokens": tokens[0] if tokens and attempts else None,
            "output_tokens": tokens[1] if tokens and attempts else None,
            "cost_usd": str(cost) if cost is not None else None,
        }

    def _call(
        self,
        project_id: UUID,
        run_id: UUID,
        index: int,
        chunk: list[Block],
        merges: Any,
        resolved_keys: set[str],
        taken: set[tuple[str, str, str]],
        cancel: CancelToken,
        proposals: list[ValidProposal],
        drops: Counter[str],
        calls: list[dict[str, Any]],
        wellbores: list[str],
    ) -> None:
        cfg = self._config
        labelled = block_labels(chunk)
        context = {"wellbores": wellbores[:CONTEXT_WELLBORES], "wellbore_count": len(wellbores)}
        messages, included = build_messages(labelled, self._source, project_id, context)
        limits = dataclasses.replace(
            cfg.limits,
            max_output_tokens=output_bound(cfg.limits.max_output_tokens, len(included)),
        )
        unit = WorkUnit(
            provider=self._provider,
            ledger=self._ledger,
            period_id=cfg.period_id,
            pricing_id=cfg.pricing_id,
            pricing=cfg.pricing,
            model=cfg.model,
            request_key=f"merge-proposals:{run_id}:{index}",
            work_unit=f"merge-proposals:{index}"[:120],
            limits=limits,
            cancel=cancel,
            effort=cfg.effort,
        )
        cost: Decimal | None = None
        try:
            with unit:
                response = unit.step_retry_truncated(
                    messages, retry_cap=limits.max_output_tokens * 2
                )
            closed = unit.closed
            cost = closed.committed_usd if closed is not None else None
            raw = parse_output(response.text())
            tok_in, tok_out = unit.token_usage()
            has_usage = response.usage is not None
            local: list[ValidProposal] = []
            local_drops: Counter[str] = Counter()
            for group in raw.groups:
                block = labelled.get(group.block)
                if block is None or group.block not in included:
                    local_drops["unknown_block"] += 1
                    continue
                try:
                    local.append(
                        validate_group(
                            group,
                            block,
                            source=self._source,
                            project_id=project_id,
                            merges=merges,
                            resolved_keys=resolved_keys,
                            taken=taken,
                        )
                    )
                except Dropped as dropped:
                    local_drops[dropped.code] += 1
            for p in local:
                for cand, _ in p.members:
                    taken.add((p.block.target.key, cand.party.kind, cand.party.key))
            proposals.extend(local)
            drops.update(local_drops)
            calls.append(
                {
                    "index": index,
                    "outcome": "ok",
                    "reason": None,
                    "blocks": len(included),
                    "attempts": unit.attempts,
                    "input_tokens": tok_in if has_usage else None,
                    "output_tokens": tok_out if has_usage else None,
                    "cost_usd": str(cost) if cost is not None else None,
                }
            )
        except Exception as exc:  # noqa: BLE001 - every failure is mapped to a stable reason
            if not isinstance(exc, AssistantError | OutputError):
                log.exception("merge proposal call failed")
            try:
                closed = unit.close()
                cost = closed.committed_usd if closed is not None else None
            except Exception:  # noqa: BLE001
                log.exception("merge proposal settle failed")
            tokens: tuple[int, int] | None = None
            try:
                tokens = unit.token_usage()
            except Exception:  # noqa: BLE001
                log.exception("merge proposal token read failed")
            calls.append(
                self._failed(index, len(included), failure_reason(exc), unit.attempts, cost, tokens)
            )
