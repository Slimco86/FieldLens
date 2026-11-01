"""The model step: block -> prompt -> provider -> parse -> server-side validation -> persist.

One ``WorkUnit`` per call (budget reserved and settled by the existing ledger). The proposer
never changes identity; it only stores ``pending``/``blocked`` proposals for review."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

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

from . import service
from .blocking import Block, build_dataset
from .evidence import SourceText
from .prompt import PROMPT_VERSION, OutputError, block_labels, build_messages, parse_output
from .validation import Dropped, ValidProposal, validate_group

log = logging.getLogger(__name__)

MAX_BLOCKS_PER_CALL = 4
MAX_CALLS = 3


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
            deadline_s=60.0,
            max_output_tokens=2048,
            max_reserved_usd=Decimal("0.10"),
        )
    )
    effort: Any = None
    max_blocks_per_call: int = MAX_BLOCKS_PER_CALL
    max_calls: int = MAX_CALLS


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

    def estimate(self, project_id: UUID) -> MergeProposalEstimate:
        with self._factory() as s:
            ds = build_dataset(s, project_id)
        chunks = self._chunks(ds.blocks)[: self._config.max_calls]
        sent = sum(len(c) for c in chunks)
        per = self._config.limits.max_reserved_usd
        return MergeProposalEstimate(
            blocks=sent,
            deferred_blocks=ds.deferred_blocks + len(ds.blocks) - sent,
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
            taken = service.taken_pairs(s, project_id)
        chunks = self._chunks(ds.blocks)
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
                proposals, drops, calls,
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
        index: int, blocks: int, reason: str, attempts: int, cost: Decimal | None
    ) -> dict[str, Any]:
        return {
            "index": index,
            "outcome": "failed",
            "reason": reason,
            "blocks": blocks,
            "attempts": attempts,
            "input_tokens": None,
            "output_tokens": None,
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
    ) -> None:
        cfg = self._config
        labelled = block_labels(chunk)
        messages, included = build_messages(labelled, self._source, project_id)
        unit = WorkUnit(
            provider=self._provider,
            ledger=self._ledger,
            period_id=cfg.period_id,
            pricing_id=cfg.pricing_id,
            pricing=cfg.pricing,
            model=cfg.model,
            request_key=f"merge-proposals:{run_id}:{index}",
            work_unit=f"merge-proposals:{index}"[:120],
            limits=cfg.limits,
            cancel=cancel,
            effort=cfg.effort,
        )
        cost: Decimal | None = None
        try:
            with unit:
                response = unit.step(messages)
            closed = unit.closed
            cost = closed.committed_usd if closed is not None else None
            raw = parse_output(response.text())
            usage = response.usage
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
                    "input_tokens": usage.input_tokens if usage else None,
                    "output_tokens": usage.output_tokens if usage else None,
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
            calls.append(
                self._failed(index, len(included), failure_reason(exc), unit.attempts, cost)
            )
