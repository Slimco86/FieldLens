"""Fixtures for merge-proposal tests: synthetic project, scripted stub provider, fake source text.
No network and no model call anywhere (D7)."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.runner import RequestLimits
from fieldlens.assistant.stub import StubProvider
from fieldlens.identity.resolver import resolve_project
from fieldlens.merge_proposals.designator import normalize_text
from fieldlens.merge_proposals.proposer import OUTPUT_BASE_TOKENS, MergeProposer, ProposerConfig
from fieldlens.persistence.session import session_scope
from tests.assistant_support import MODEL, PRICING
from tests.retrieval.support import World, attr, rec


def subj(well: str | None, key: str | None, suffix: str | None = None) -> dict[str, Any]:
    return {
        "well_name": well,
        "wellbore_name": None,
        "wellbore_label": well,
        "well_key": key,
        "wellbore_suffix": suffix,
    }


class FakeSource:
    """SourceText over in-memory text; the content sha is the real stored one."""

    def __init__(self, world: World, texts: dict[UUID, str]) -> None:
        self._world = world
        self.texts = texts

    def content_sha(self, project_id: UUID, document_id: UUID) -> str | None:
        rows = self._world.sql(
            "SELECT sha256 FROM source_document WHERE document_id = :d", d=document_id
        )
        return str(rows[0][0]) if rows else None

    def contains(self, project_id: UUID, document_id: UUID, quote: str) -> bool | None:
        body = self.texts.get(document_id)
        return None if body is None else normalize_text(quote) in normalize_text(body)

    def snippets(
        self, project_id: UUID, document_id: UUID, pattern: re.Pattern[str], limit: int
    ) -> list[tuple[int, str]]:
        body = self.texts.get(document_id, "")
        hits = [(n, ln.strip()) for n, ln in enumerate(body.splitlines(), 1) if pattern.search(ln)]
        return hits[:limit]


def seed(world: World) -> tuple[str, dict[str, UUID]]:
    """Resolved wellbores F-12, F-12 A, F-14; unresolved spellings of F-12 and F-12 A and F-11."""
    pid = world.project()
    base = world.add_doc(
        pid,
        "wells.txt",
        [
            rec("note", subj("NO 15/9-F-12", "15/9-F-12"), [attr("note.text", "x")]),
            rec("note", subj("NO 15/9-F-12 A", "15/9-F-12", "A"), [attr("note.text", "x")]),
            rec("note", subj("NO 15/9-F-14", "15/9-F-14"), [attr("note.text", "x")]),
        ],
    )
    alias = world.add_doc(
        pid,
        "alias.txt",
        [
            rec("note", subj("Well F12 (Volve)", None), [attr("note.text", "x")]),
            rec("note", subj("Well F12A (Volve)", None), [attr("note.text", "x")]),
            rec("note", subj("Well F11 (Volve)", None), [attr("note.text", "x")]),
        ],
    )
    with session_scope(world.factory) as s:
        resolve_project(s, UUID(pid))
    return pid, {"base": base.document_id, "alias": alias.document_id}


def make_proposer(
    world: World,
    source: FakeSource,
    script: list[Any],
    *,
    max_reserved: str = "0.10",
    blocks_per_call: int = 4,
    max_calls: int = 3,
) -> tuple[MergeProposer, StubProvider]:
    ledger = BudgetLedger(world.factory)
    period = ledger.ensure_period(
        "t57",
        ledger_cap_usd=Decimal("150"),
        warn_usd=Decimal("100"),
        unattended_block_usd=Decimal("120"),
    )
    ledger.confirm_balance(period, Decimal("150"), "test fixture")
    pricing_id = ledger.register_pricing(PRICING, "synthetic test rates")
    provider = StubProvider(script)
    cfg = ProposerConfig(
        period_id=period,
        pricing_id=pricing_id,
        pricing=PRICING,
        model=MODEL,
        limits=RequestLimits(
            max_attempts=2,
            max_tool_calls=0,
            max_output_tokens=OUTPUT_BASE_TOKENS,
            max_reserved_usd=Decimal(max_reserved),
            retry_backoff_s=0.0,
        ),
        max_blocks_per_call=blocks_per_call,
        max_calls=max_calls,
    )
    return MergeProposer(world.factory, ledger, provider, cfg, source), provider


def group(block: str, target: str, members: list[str], evidence: list[dict[str, str]]) -> str:
    return json.dumps(
        {
            "groups": [
                {
                    "block": block,
                    "target": target,
                    "members": members,
                    "evidence": evidence,
                    "rationale": "same well",
                }
            ]
        }
    )


def count(world: World, table: str) -> int:
    return int(world.sql(f"SELECT count(*) FROM {table}")[0][0])  # noqa: S608
