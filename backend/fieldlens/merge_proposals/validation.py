"""Server-side validation of model output. Nothing from the model is trusted.

Order per proposed group: structural (refs exist in the block, target is the block's target, no
duplicates) -> evidence (cited document is one shown for the block, the quote occurs in that
document and names both parties) -> deterministic guards G1..G6. A structural or evidence failure
drops the group with a counted code; a guard failure keeps it as a ``blocked`` proposal that can
never be accepted."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

from fieldlens.identity.merges import ActiveMerge

from . import guards
from .blocking import Block, MemberCandidate
from .designator import designator_pattern, literal_pattern, normalize_text
from .evidence import SourceText
from .guards import G7, GuardCheck, Party
from .prompt import RawGroup, refs_for


@dataclass(frozen=True)
class EvidenceItem:
    document_id: UUID
    content_sha256: str
    quote: str

    def as_json(self) -> dict[str, str]:
        return {
            "document_id": str(self.document_id),
            "content_sha256": self.content_sha256,
            "quote": self.quote,
        }


@dataclass
class ValidProposal:
    block: Block
    members: list[tuple[MemberCandidate, list[EvidenceItem]]]
    checks: list[GuardCheck]
    rationale: str
    status: str  # pending | blocked
    drops: list[str] = field(default_factory=list)


class Dropped(Exception):
    """A group failed structural/evidence validation; ``code`` is the counted reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _party_pattern(party: Party, *, allow_short: bool) -> re.Pattern[str]:
    if party.kind == "wellbore" and party.designator is not None:
        return designator_pattern(party.designator, allow_short=allow_short)
    return literal_pattern(party.name)


def names_in(quote: str, party: Party, *, allow_short: bool) -> bool:
    pattern = _party_pattern(party, allow_short=allow_short)
    return bool(pattern.search(normalize_text(quote)))


def verify_quote(
    source: SourceText,
    project_id: UUID,
    block: Block,
    member: Party,
    document_id: UUID,
    quote: str,
) -> EvidenceItem:
    """G7 for one evidence item; raises ``Dropped`` with the failing reason."""
    if document_id not in block.all_documents:
        raise Dropped("unknown_document")
    sha = source.content_sha(project_id, document_id)
    present = source.contains(project_id, document_id, quote) if sha else None
    if sha is None or present is None:
        raise Dropped("source_unavailable")
    if not present:
        raise Dropped("quote_not_found")
    if not names_in(quote, member, allow_short=False):
        raise Dropped("quote_lacks_member")
    # The member's own spelling may contain the target's designator ("Well F12 (Volve)"); it must
    # not count as naming the target, so the target is looked for outside the member's name.
    own = (
        _party_pattern(member, allow_short=False)
        if member.kind == "wellbore"
        and member.designator is not None
        and not member.designator.block
        else literal_pattern(member.name)
    )
    outside = own.sub(" ", normalize_text(quote))
    if not names_in(outside, block.target, allow_short=block.allow_short_target):
        raise Dropped("quote_lacks_target")
    return EvidenceItem(document_id, sha, quote)


def validate_group(
    group: RawGroup,
    block: Block,
    *,
    source: SourceText,
    project_id: UUID,
    merges: list[ActiveMerge],
    resolved_keys: set[str],
    taken: set[tuple[str, str, str]],
) -> ValidProposal:
    """Return the validated proposal or raise ``Dropped``."""
    refs = refs_for(block)
    if group.target != "t":
        raise Dropped("bad_target")
    if len(set(group.members)) != len(group.members):
        raise Dropped("duplicate_ref")
    chosen: list[tuple[str, MemberCandidate]] = []
    for ref in group.members:
        cand = refs.get(ref)
        if cand is None:
            raise Dropped("unknown_ref")
        chosen.append((ref, cand))
    by_ref = dict(chosen)
    evidence: dict[str, list[EvidenceItem]] = {ref: [] for ref in by_ref}
    for item in group.evidence:
        cand = by_ref.get(item.member)
        if cand is None:
            raise Dropped("bad_evidence_member")
        evidence[item.member].append(
            verify_quote(source, project_id, block, cand.party, item.document_id, item.quote)
        )
    if any(not items for items in evidence.values()):
        raise Dropped("evidence_missing")
    for _, cand in chosen:
        if (block.target.key, cand.party.kind, cand.party.key) in taken:
            raise Dropped("duplicate_proposal")
    checks = guards.evaluate(
        block.target, [c.party for _, c in chosen], merges, in_project_keys=resolved_keys
    )
    checks.append(
        GuardCheck(G7, True, "every merged name has a verified quote naming both parties")
    )
    return ValidProposal(
        block,
        [(cand, evidence[ref]) for ref, cand in chosen],
        checks,
        group.rationale.strip(),
        "blocked" if guards.failed(checks) else "pending",
    )
