"""Typed, read-only evidence search and source coverage (source mode).

``RetrievalService.search_evidence`` is the server-side implementation behind the
``search_evidence`` tool and the read endpoint; later assistant tasks call it directly. It never
executes caller-supplied SQL: the query text becomes bound parameters and a tsquery built only
from ``[a-z0-9]`` words.

Order of operations (the spec's scope-before-rank rule):

1. Eligibility is a WHERE clause shared by every ranking path: project, requested source
   revision membership, stored (not quarantined) document, current non-superseded extraction run
   with records, complete chunk index of the current chunker version, not invalidated.
2. Exact identifiers resolve first. One canonical entity restricts every later ranking to chunks
   that mention it (no broadening to siblings); several canonicals behind one identifier return
   an explicit ambiguity and no hits.
3. Up to 20 lexical (PostgreSQL ``simple`` full text) and 20 exact-cosine vector candidates are
   ranked inside that scope and fused by reciprocal rank ``1/(60+rank)``.
4. At most 10 chunks and 12,000 estimated tokens are returned.

A missing/failed embedder or an incomplete vector index is reported as ``degraded`` with reasons;
it is never presented as hybrid."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.contracts.context import SourceContext, context_cache_key
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import Coverage, CoverageStatus, EvidenceLink, Locator
from fieldlens.contracts.retrieval import (
    MAX_CONTEXT_TOKENS,
    MAX_EVIDENCE_CHUNKS,
    AmbiguityCandidate,
    DegradedReason,
    DocumentCoverage,
    EmbeddingState,
    EvidenceHit,
    EvidenceSearchResult,
    ExactMatch,
    ExtractionQuality,
    HitSignals,
    HitSupport,
    IdentifierAmbiguity,
    IndexedState,
    IndexState,
    RetrievalMode,
    SearchStatus,
    SourceCoverage,
)
from fieldlens.persistence.session import session_scope

from .chunker import CHUNKER_VERSION
from .embedder import EmbedderProvider, EmbedderUnavailable
from .identifiers import (
    Candidate,
    id_shaped_tokens,
    query_candidates,
    query_tokens,
    query_uuids,
    unqualified,
)
from .indexer import vector_literal
from .text import norm_identifier, search_text

logger = logging.getLogger(__name__)
RRF_K = 60
CANDIDATES = 20
MAX_TERMS = 32
_STOP_WORDS = frozenset(
    "a an and are as at be by do does for from how in is it of on or the to was were what when "
    "where which who with".split()
)
_LINKS_PER_HIT = 5
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_ELIGIBLE = """
FROM evidence_chunk c
JOIN retrieval_index ri ON ri.project_id = c.project_id AND ri.index_id = c.index_id
JOIN extraction_run er ON er.project_id = c.project_id AND er.run_id = c.run_id
JOIN source_revision_document srd
  ON srd.project_id = c.project_id AND srd.document_id = c.document_id
JOIN document_processing dp ON dp.project_id = c.project_id AND dp.document_id = c.document_id
"""
_ELIGIBLE_WHERE = """
c.project_id = :pid AND srd.source_revision_id = :rev
AND ri.kind = 'chunks' AND ri.status = 'complete' AND ri.chunker_version = :cv
AND c.chunker_version = :cv AND c.invalidated_at IS NULL
AND er.superseded = false AND er.status IN ('succeeded', 'partial')
AND dp.storage_state = 'stored'
"""


@dataclass
class _Scope:
    pid: UUID
    rev: UUID
    documents: list[UUID] | None = None
    canonicals: list[str] | None = None

    def where(self) -> tuple[str, dict[str, Any]]:
        clause = _ELIGIBLE_WHERE
        params: dict[str, Any] = {"pid": self.pid, "rev": self.rev, "cv": CHUNKER_VERSION}
        if self.documents is not None:
            clause += " AND c.document_id = ANY(:docs)"
            params["docs"] = self.documents
        if self.canonicals is not None:
            clause += (
                " AND c.chunk_id IN (SELECT ci.chunk_id FROM chunk_identifier ci "
                "WHERE ci.project_id = :pid AND ci.canonical = ANY(:canon))"
            )
            params["canon"] = self.canonicals
        return clause, params


def evidence_link(
    locator: dict[str, Any], document_id: UUID, revision_id: UUID
) -> EvidenceLink | None:
    try:
        loc = Locator.model_validate(
            {**locator, "document_id": document_id, "source_revision_id": revision_id}
        )
        return EvidenceLink(document_id=document_id, source_revision_id=revision_id, locator=loc)
    except ValueError:
        return None


def _or_terms(terms: list[str]) -> str | None:
    return " | ".join(list(dict.fromkeys(terms))[:MAX_TERMS]) or None


def tsqueries_for(tokens: list[str]) -> tuple[str | None, str | None]:
    """(simple, english) tsquery strings from bound text only.

    ``simple`` ORs plain words and turns a token that normalizes to several words (``F-14`` ->
    ``f 14``, ``1234.5`` -> ``1234 5``) into a phrase (``f <-> 14``), so an identifier or number
    must match whole. ``english`` ORs only the plain words, stemmed by PostgreSQL, so
    ``perforations`` reaches ``perforation``; identifiers and numbers are never stemmed.
    Stop words are dropped; every term is ``[a-z0-9]`` only."""
    simple: list[str] = []
    english: list[str] = []
    for token in tokens:
        words = search_text(token).split()
        if len(words) == 1:
            if words[0] not in _STOP_WORDS:
                simple.append(words[0])
                if not words[0].isdigit():
                    english.append(words[0])
        elif words:
            simple.append("(" + " <-> ".join(words) + ")")
    return _or_terms(simple), _or_terms(english)


def rrf(lists: dict[str, list[UUID]]) -> list[tuple[UUID, float]]:
    """Reciprocal-rank fusion, deterministic: score desc, then chunk id."""
    scores: dict[UUID, float] = {}
    for ranked in lists.values():
        for position, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + position)
    return sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))


class RetrievalService:
    def __init__(
        self, factory: sessionmaker[Session], settings: Settings, provider: EmbedderProvider
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._provider = provider

    # -- public API -------------------------------------------------------------------------
    def search_evidence(
        self,
        project_id: UUID,
        query: str,
        *,
        source_revision_id: UUID | None = None,
        document_ids: list[UUID] | None = None,
        limit: int = MAX_EVIDENCE_CHUNKS,
    ) -> EvidenceSearchResult:
        query = _CONTROL.sub(" ", query).strip()  # NUL/control characters never reach SQL
        if not query:
            raise ContractError(ErrorCode.VALIDATION_ERROR, "query must not be empty", 422)
        limit = max(1, min(limit, MAX_EVIDENCE_CHUNKS))
        # The query embedding is computed before any database work so the heavy call never
        # holds a transaction; it may legitimately fail, which degrades (never fakes) the mode.
        embedding: list[float] | None = None
        problem: EmbedderUnavailable | None = None
        status = self._provider.status()
        if status.spec is None:
            problem = EmbedderUnavailable(status.code or "model_missing", status.message or "")
        else:
            try:
                embedding = self._provider.embed_query(query)
            except EmbedderUnavailable as exc:
                problem = exc
            if embedding is not None and not _valid_embedding(embedding, status.spec.dimension):
                embedding = None  # zero/NaN/wrong-size vector: explicit degraded, never silent
                problem = EmbedderUnavailable(
                    "query_embedding_invalid", "query embedding is zero, non-finite or wrong size"
                )
        with session_scope(self._factory) as session:
            # JIT compilation costs seconds on these selective queries and gains nothing.
            session.execute(text("SET LOCAL jit = off"))
            return self._search(
                session,
                project_id,
                query,
                source_revision_id,
                document_ids,
                limit,
                embedding,
                status.spec.fingerprint if status.spec else None,
                problem,
            )

    def source_coverage(
        self, project_id: UUID, source_revision_id: UUID | None = None
    ) -> SourceCoverage:
        status = self._provider.status()
        with session_scope(self._factory) as session:
            revision = _resolve_revision(session, project_id, source_revision_id)
            if revision is None:
                return SourceCoverage(
                    project_id=project_id,
                    source_revision_id=None,
                    chunker_version=CHUNKER_VERSION,
                    embedding=_embedding_state(status),
                    documents=[],
                    index=IndexState(
                        eligible_documents=0,
                        text_indexed_documents=0,
                        vector_indexed_documents=0,
                        pending_documents=0,
                        index_epoch=_epoch([]),
                        embedding_fingerprint=status.spec.fingerprint if status.spec else None,
                    ),
                    notes=["The project has no source revision yet; nothing is indexed."],
                )
            docs = _document_coverage(session, project_id, revision, status)
        index = _index_state(docs, status.spec.fingerprint if status.spec else None)
        notes = []
        if status.spec is None:
            notes.append(
                "Vector search is unavailable; retrieval is degraded to exact identifiers + "
                f"full text ({status.code})."
            )
        return SourceCoverage(
            project_id=project_id,
            source_revision_id=revision,
            chunker_version=CHUNKER_VERSION,
            embedding=_embedding_state(status),
            documents=[d.public for d in docs],
            index=index,
            notes=notes,
        )

    # -- internals --------------------------------------------------------------------------
    def _search(
        self,
        session: Session,
        project_id: UUID,
        query: str,
        revision_arg: UUID | None,
        document_ids: list[UUID] | None,
        limit: int,
        embedding: list[float] | None,
        fingerprint: str | None,
        embed_problem: EmbedderUnavailable | None,
    ) -> EvidenceSearchResult:
        revision = _resolve_revision(session, project_id, revision_arg)
        emb_status = self._provider.status()
        if revision is None:
            return self._empty(
                project_id,
                None,
                query,
                [DegradedReason.NO_INDEXED_DOCUMENTS],
                ["The project has no source revision yet; nothing is searchable."],
                fingerprint,
            )
        docs = _document_coverage(session, project_id, revision, emb_status)
        index = _index_state(docs, fingerprint)
        reasons = _degraded_reasons(docs, index, embed_problem)
        scope = _Scope(project_id, revision)
        if document_ids:
            member = {d.public.document_id for d in docs}
            wanted = [d for d in dict.fromkeys(document_ids) if d in member]
            if len(wanted) != len(set(document_ids)):
                raise ContractError(ErrorCode.NOT_FOUND, "document not found in this revision", 404)
            scope.documents = wanted
        notes: list[str] = []
        exact_matches: list[ExactMatch] = []
        unmatched: list[str] = []

        # 1. Exact identifiers (document ids, well/wellbore labels, model numbers).
        uuid_hits = self._document_id_matches(query, docs, scope)
        ambiguities, canon, exact_matches, matched_all, consumed = self._resolve_identifiers(
            session, scope, query
        )
        exact_matches = [*uuid_hits, *exact_matches]
        known = matched_all | {m.identifier for m in uuid_hits}
        unmatched = [t for t in id_shaped_tokens(query) if t not in known]
        cache_key = self._cache_key(project_id, revision, query, scope, limit, fingerprint, index)
        if ambiguities:
            return EvidenceSearchResult(
                project_id=project_id,
                source_revision_id=revision,
                query=query,
                status=SearchStatus.AMBIGUOUS,
                mode=RetrievalMode.DEGRADED if reasons else RetrievalMode.HYBRID,
                degraded_reasons=reasons,
                evidence_strength="none",
                vector_support_floor=self._settings.retrieval_vector_support_floor,
                hits=[],
                returned_tokens=0,
                exact_matches=exact_matches,
                ambiguities=ambiguities,
                unmatched_identifiers=unmatched,
                index=index,
                cache_key=cache_key,
                notes=["An identifier maps to more than one entity; no evidence is returned."],
            )
        exact_scope = bool(canon or uuid_hits)
        if canon:
            scope.canonicals = canon
        if index.text_indexed_documents == 0:
            notes.append(_why_empty(docs))

        # 2. Ranking inside the scope. Exact identification is a SCOPE (filter), not a ranking
        # list: identifier tokens are removed from the topical full-text query, and the exact
        # list is only a fallback when the query is nothing but an identifier.
        uuids = set(query_uuids(query))
        topical_tokens = [
            tok
            for i, tok in enumerate(query_tokens(query))
            if i not in consumed and norm_identifier(tok) not in uuids
        ]
        topical = bool(topical_tokens)
        lexical = self._lexical(session, scope, topical_tokens)
        vector: list[tuple[UUID, float]] = []
        if embedding is not None and fingerprint is not None:
            vector = self._vector(session, scope, embedding, fingerprint)
        lists = {"lexical": lexical, "vector": [cid for cid, _ in vector]}
        fused = rrf({k: v for k, v in lists.items() if v})
        if not fused and exact_scope:
            fused = rrf({"exact": self._exact_list(session, scope)})
        sim = dict(vector)
        lex_rank = {cid: i for i, cid in enumerate(lexical, start=1)}
        vec_rank = {cid: i for i, (cid, _) in enumerate(vector, start=1)}
        floor = self._settings.retrieval_vector_support_floor
        details = self._load_chunks(session, [cid for cid, _ in fused])

        def support(cid: UUID) -> HitSupport:
            return HitSupport(
                exact=exact_scope,
                lexical=cid in lex_rank,
                vector=cid in sim and sim[cid] >= floor,
            )

        needles = [search_text(u) for u in unmatched]

        def relevant(sp: HitSupport, cid: UUID) -> bool:
            # An identifier-shaped token found in no source identifier (unknown well, model or
            # number) must itself appear in the chunk text, else topical overlap proves nothing.
            row = details.get(cid)
            if row is None or (needles and not all(n in search_text(row.text) for n in needles)):
                return False
            return sp.lexical or sp.vector or (sp.exact and not topical)

        any_supported = any(relevant(support(cid), cid) for cid, _ in fused)
        per_kind_cap = max(1, limit // 2)
        kinds: dict[str, int] = {}
        hits: list[EvidenceHit] = []
        tokens = 0
        for chunk_id, score in fused:
            row = details.get(chunk_id)
            if row is None:
                continue
            sp = support(chunk_id)
            if any_supported and not relevant(sp, chunk_id):
                continue  # noise next to real evidence is dropped, not flagged
            if not exact_scope and kinds.get(row.kind, 0) >= per_kind_cap:
                continue  # diversity guard: one record kind cannot flood an unscoped query
            if len(hits) >= limit or tokens + row.token_count > MAX_CONTEXT_TOKENS:
                break
            tokens += row.token_count
            kinds[row.kind] = kinds.get(row.kind, 0) + 1
            hits.append(
                _hit(
                    row,
                    len(hits) + 1,
                    score,
                    HitSignals(
                        exact=exact_scope,
                        lexical_rank=lex_rank.get(chunk_id),
                        vector_rank=vec_rank.get(chunk_id),
                        vector_similarity=sim.get(chunk_id),
                    ),
                    sp,
                    revision,
                )
            )
        if reasons:
            notes.append(
                "Retrieval is degraded: "
                + ", ".join(r.value for r in reasons)
                + "; results come from exact identifiers and full text"
                + (" plus the vectors that exist." if vector else " only.")
            )
        if not hits and index.text_indexed_documents > 0:
            notes.append("No indexed chunk matched this query within the eligible sources.")
        if hits and not any_supported:
            status = SearchStatus.WEAK_EVIDENCE
            strength = "weak"
            notes.append(
                "No hit has exact, full-text or above-floor vector support (floor "
                f"{floor}, uncalibrated); the hits are flagged and must not be cited as evidence."
            )
        else:
            status = SearchStatus.OK if hits else SearchStatus.NO_RESULTS
            strength = "strong" if hits else "none"
        return EvidenceSearchResult(
            project_id=project_id,
            source_revision_id=revision,
            query=query,
            status=status,
            mode=RetrievalMode.DEGRADED if reasons else RetrievalMode.HYBRID,
            degraded_reasons=reasons,
            evidence_strength=strength,
            vector_support_floor=floor,
            hits=hits,
            returned_tokens=tokens,
            exact_matches=exact_matches,
            unmatched_identifiers=unmatched,
            index=index,
            cache_key=cache_key,
            notes=notes,
        )

    def _empty(
        self,
        project_id: UUID,
        revision: UUID | None,
        query: str,
        reasons: list[DegradedReason],
        notes: list[str],
        fingerprint: str | None,
    ) -> EvidenceSearchResult:
        return EvidenceSearchResult(
            project_id=project_id,
            source_revision_id=revision,
            query=query,
            status=SearchStatus.UNAVAILABLE,
            mode=RetrievalMode.DEGRADED,
            degraded_reasons=reasons,
            evidence_strength="none",
            vector_support_floor=self._settings.retrieval_vector_support_floor,
            hits=[],
            returned_tokens=0,
            index=IndexState(
                eligible_documents=0,
                text_indexed_documents=0,
                vector_indexed_documents=0,
                pending_documents=0,
                index_epoch=_epoch([]),
                embedding_fingerprint=fingerprint,
            ),
            cache_key=hashlib.sha256(f"{project_id}:none:{query}".encode()).hexdigest(),
            notes=notes,
        )

    def _cache_key(
        self,
        project_id: UUID,
        revision: UUID,
        query: str,
        scope: _Scope,
        limit: int,
        fingerprint: str | None,
        index: IndexState,
    ) -> str:
        return context_cache_key(
            _source_context(project_id, revision),
            query={
                "q": query,
                "documents": ",".join(sorted(str(d) for d in scope.documents or [])),
                "limit": limit,
                "index_epoch": index.index_epoch,
            },
            algorithm_version=f"search_evidence/1+{CHUNKER_VERSION}+rrf{RRF_K}+{fingerprint or 'no-vector'}",
        )

    def _document_id_matches(self, query: str, docs: list[_Doc], scope: _Scope) -> list[ExactMatch]:
        member = {str(d.public.document_id): d.public.document_id for d in docs}
        found = [member[u] for u in query_uuids(query) if u in member]
        if not found:
            return []
        scope.documents = [d for d in found if scope.documents is None or d in scope.documents]
        return [
            ExactMatch(identifier=str(d), canonical=str(d), kinds=["document_id"], chunk_count=0)
            for d in found
        ]

    def _resolve_identifiers(
        self, session: Session, scope: _Scope, query: str
    ) -> tuple[list[IdentifierAmbiguity], list[str], list[ExactMatch], set[str], set[int]]:
        candidates = query_candidates(query)
        if not candidates:
            return [], [], [], set(), set()
        where, params = scope.where()
        rows = session.execute(
            text(
                "SELECT ci.identifier, ci.canonical, ci.id_kind, c.document_id, "
                "count(DISTINCT c.chunk_id) AS chunks "
                + _ELIGIBLE
                + " JOIN chunk_identifier ci ON ci.project_id = c.project_id "
                "AND ci.chunk_id = c.chunk_id WHERE " + where + " AND ci.identifier = ANY(:cands) "
                "GROUP BY ci.identifier, ci.canonical, ci.id_kind, c.document_id"
            ),
            {**params, "cands": [c.text for c in candidates]},
        ).all()
        by_text: dict[str, Candidate] = {c.text: c for c in candidates}
        matched = {r.identifier for r in rows}
        # Longest match wins: an identifier inside a longer matched n-gram is dropped.
        spans = {t: by_text[t] for t in matched}
        keep = {
            t
            for t, c in spans.items()
            if not any(
                o.text != t
                and o.start <= c.start
                and c.end <= o.end
                and (o.end - o.start) > (c.end - c.start)
                for o in spans.values()
            )
        }
        grouped: dict[str, dict[str, dict[str, Any]]] = {}
        for r in rows:
            if r.identifier not in keep:
                continue
            entry = grouped.setdefault(r.identifier, {}).setdefault(
                r.canonical, {"kinds": set(), "chunks": 0, "docs": set()}
            )
            entry["kinds"].add(r.id_kind)
            entry["chunks"] += r.chunks
            entry["docs"].add(r.document_id)
        ambiguities: list[IdentifierAmbiguity] = []
        canon: list[str] = []
        exact: list[ExactMatch] = []
        for identifier in sorted(grouped):
            cands = _merge_unqualified(grouped[identifier])
            if len(cands) > 1:
                ambiguities.append(
                    IdentifierAmbiguity(
                        identifier=identifier,
                        candidates=[
                            AmbiguityCandidate(
                                canonical=name,
                                kinds=sorted(v["kinds"]),
                                chunk_count=v["chunks"],
                                document_ids=sorted(v["docs"], key=str),
                            )
                            for name, v in sorted(cands.items())
                        ],
                    )
                )
                continue
            ((name, v),) = cands.items()
            canon.extend(v.get("members", [name]))
            exact.append(
                ExactMatch(
                    identifier=identifier,
                    canonical=name,
                    kinds=sorted(v["kinds"]),
                    chunk_count=v["chunks"],
                )
            )
        consumed = {i for t in keep for i in range(spans[t].start, spans[t].end)}
        return ambiguities, sorted(set(canon)), exact, matched, consumed

    def _exact_list(self, session: Session, scope: _Scope) -> list[UUID]:
        where, params = scope.where()
        rows = session.execute(
            text(
                "SELECT c.chunk_id "
                + _ELIGIBLE
                + " WHERE "
                + where
                + " ORDER BY c.document_id, c.ordinal LIMIT :n"
            ),
            {**params, "n": CANDIDATES},
        ).all()
        return [r.chunk_id for r in rows]

    def _lexical(self, session: Session, scope: _Scope, tokens: list[str]) -> list[UUID]:
        simple, english = tsqueries_for(tokens)
        if simple is None and english is None:
            return []
        where, params = scope.where()
        rows = session.execute(
            text(
                "SELECT c.chunk_id, ts_rank(c.tsv, qs.q) + ts_rank(c.tsv_en, qe.q) AS score "
                + _ELIGIBLE
                + ", to_tsquery('simple', :tss) AS qs(q), to_tsquery('english', :tse) AS qe(q)"
                " WHERE " + where + " AND (c.tsv @@ qs.q OR c.tsv_en @@ qe.q)"
                " ORDER BY score DESC, c.chunk_id LIMIT :n"
            ),
            {**params, "tss": simple or "", "tse": english or "", "n": CANDIDATES},
        ).all()
        return [r.chunk_id for r in rows]

    def _vector(
        self, session: Session, scope: _Scope, embedding: list[float], fingerprint: str
    ) -> list[tuple[UUID, float]]:
        where, params = scope.where()
        rows = session.execute(
            text(
                "SELECT c.chunk_id, 1 - (e.embedding <=> CAST(:qv AS vector)) AS sim "
                + _ELIGIBLE
                + " JOIN chunk_embedding e ON e.project_id = c.project_id AND e.chunk_id = c.chunk_id"
                " AND e.embedding_fingerprint = :fp AND e.chunk_fingerprint = c.chunk_fingerprint"
                " JOIN retrieval_index rv ON rv.project_id = c.project_id AND rv.run_id = c.run_id"
                " AND rv.kind = 'embeddings' AND rv.embedding_fingerprint = :fp"
                " AND rv.chunker_version = :cv AND rv.status = 'complete'"
                " WHERE " + where + " AND vector_dims(e.embedding) = :dim"
                " AND 1 - (e.embedding <=> CAST(:qv AS vector)) >= :min_sim"
                " ORDER BY e.embedding <=> CAST(:qv AS vector), c.chunk_id LIMIT :n"
            ),
            {
                **params,
                "qv": vector_literal(embedding),
                "fp": fingerprint,
                "dim": len(embedding),
                "min_sim": self._settings.retrieval_min_vector_similarity,
                "n": CANDIDATES,
            },
        ).all()
        return [(r.chunk_id, float(r.sim)) for r in rows if math.isfinite(float(r.sim))]

    def _load_chunks(self, session: Session, ids: list[UUID]) -> dict[UUID, Any]:
        if not ids:
            return {}
        rows = session.execute(
            text(
                "SELECT chunk_id, text, token_count, kind, document_id, source_revision_id, "
                "record_ids, first_record_ordinal, last_record_ordinal, locators, "
                "extraction_quality, resolved_entity_id, claim_ids FROM evidence_chunk "
                "WHERE chunk_id = ANY(:ids)"
            ),
            {"ids": ids},
        ).all()
        return {r.chunk_id: r for r in rows}


def _valid_embedding(embedding: list[float], dimension: int) -> bool:
    """A zero, non-finite or wrong-size query vector has no usable cosine direction."""
    return (
        len(embedding) == dimension
        and all(math.isfinite(x) for x in embedding)
        and any(x != 0.0 for x in embedding)
    )


def _merge_unqualified(cands: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """``F-12`` written without a block and ``15/9-F-12`` are one naming when exactly one
    block-qualified label has that short form: a pure naming rule (never a parent/sidetrack
    merge: ``f-12 a`` is a different canonical). Two blocks stay an explicit ambiguity."""
    qualified = [c for c in cands if unqualified(c) is not None]
    if len(qualified) != 1:
        return cands
    q = qualified[0]
    loose = [c for c in cands if c != q]
    if not loose or any(c != unqualified(q) for c in loose):
        return cands
    merged = {
        "kinds": set(cands[q]["kinds"]),
        "chunks": cands[q]["chunks"],
        "docs": set(cands[q]["docs"]),
    }
    for c in loose:
        merged["kinds"] |= cands[c]["kinds"]
        merged["chunks"] += cands[c]["chunks"]
        merged["docs"] |= cands[c]["docs"]
    merged["members"] = [q, *loose]
    return {q: merged}


def _hit(
    row: Any, rank: int, score: float, signals: HitSignals, support: HitSupport, searched: UUID
) -> EvidenceHit:
    links = [
        link
        for loc in row.locators[: _LINKS_PER_HIT * 4]
        if (link := evidence_link(loc, row.document_id, row.source_revision_id)) is not None
    ][:_LINKS_PER_HIT]
    quality = row.extraction_quality
    return EvidenceHit(
        chunk_id=row.chunk_id,
        rank=rank,
        rrf_score=score,
        signals=signals,
        support=support,
        searched_revision_id=searched,
        text=row.text,
        token_count=row.token_count,
        kind=row.kind,
        document_id=row.document_id,
        source_revision_id=row.source_revision_id,
        record_ids=list(row.record_ids),
        first_record_ordinal=row.first_record_ordinal,
        last_record_ordinal=row.last_record_ordinal,
        evidence=links,
        extraction_quality=ExtractionQuality(
            run_status=quality.get("run_status", "unknown"),
            coverage_status=quality.get("coverage_status", "unknown"),
            validation_states=quality.get("validation_states", {}),
            profile_name=quality.get("profile_name"),
            profile_version=quality.get("profile_version"),
        ),
        resolved_entity_id=row.resolved_entity_id,
        claim_ids=list(row.claim_ids or []),
    )


def _source_context(project_id: UUID, revision: UUID) -> Any:
    from fieldlens.contracts.context import EvidenceContext

    return EvidenceContext(SourceContext(project_id=project_id, source_revision_id=revision))


def _resolve_revision(session: Session, project_id: UUID, requested: UUID | None) -> UUID | None:
    project = session.execute(
        text("SELECT latest_source_revision_id FROM project WHERE project_id = :p"),
        {"p": project_id},
    ).first()
    if project is None:
        raise ContractError(ErrorCode.NOT_FOUND, "project not found", 404)
    if requested is None:
        return project.latest_source_revision_id  # type: ignore[no-any-return]
    found = session.execute(
        text("SELECT 1 FROM source_revision WHERE project_id = :p AND source_revision_id = :r"),
        {"p": project_id, "r": requested},
    ).first()
    if found is None:
        raise ContractError(ErrorCode.NOT_FOUND, "source revision not found", 404)
    return requested


def _embedding_state(status: Any) -> EmbeddingState:
    if status.spec is None:
        return EmbeddingState(state=status.state, code=status.code, message=status.message)
    spec = status.spec
    return EmbeddingState(
        state="ready",
        fingerprint=spec.fingerprint,
        model_id=spec.model_id,
        model_revision=spec.model_revision,
        dimension=spec.dimension,
    )


@dataclass
class _Doc:
    public: DocumentCoverage


def _epoch(rows: list[Any]) -> str:
    material = "|".join(sorted(f"{r}" for r in rows))
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def _document_coverage(
    session: Session, project_id: UUID, revision: UUID, status: Any
) -> list[_Doc]:
    fingerprint = status.spec.fingerprint if status.spec else None
    rows = session.execute(
        text(
            """
SELECT sd.document_id, sd.original_filename, sd.format_family, dp.storage_state,
       dp.extraction_state, er.status AS run_status, er.coverage AS run_coverage,
       er.summary AS run_summary, er.error AS run_error,
       ci.index_id AS ci_id, ci.status AS ci_status, ci.chunk_count AS ci_chunks,
       ci.truncated AS ci_truncated, ci.error AS ci_error, ci.detail AS ci_detail,
       ei.status AS ei_status, ei.embedded_count AS ei_embedded, ei.error AS ei_error,
       ei.truncated AS ei_truncated, ei.chunk_count AS ei_chunks, ei.detail AS ei_detail,
       inv.invalid AS inv_count, inv.reason AS inv_reason
FROM source_revision_document srd
JOIN source_document sd ON sd.project_id = srd.project_id AND sd.document_id = srd.document_id
JOIN document_processing dp ON dp.project_id = srd.project_id AND dp.document_id = srd.document_id
LEFT JOIN extraction_run er ON er.project_id = srd.project_id AND er.document_id = srd.document_id
  AND er.superseded = false
LEFT JOIN retrieval_index ci ON ci.run_id = er.run_id AND ci.kind = 'chunks'
  AND ci.chunker_version = :cv
LEFT JOIN retrieval_index ei ON ei.run_id = er.run_id AND ei.kind = 'embeddings'
  AND ei.chunker_version = :cv AND ei.embedding_fingerprint = :fp
LEFT JOIN LATERAL (
  SELECT count(*) AS invalid, max(x.invalidated_reason) AS reason FROM evidence_chunk x
  WHERE x.index_id = ci.index_id AND x.invalidated_at IS NOT NULL
) inv ON true
WHERE srd.project_id = :pid AND srd.source_revision_id = :rev
ORDER BY sd.original_filename, sd.document_id
"""
        ),
        {"pid": project_id, "rev": revision, "cv": CHUNKER_VERSION, "fp": fingerprint},
    ).all()
    out = []
    for r in rows:
        out.append(_Doc(_one_document(r, status)))
    return out


def _coverage_dto(raw: dict[str, Any] | None) -> Coverage | None:
    if not raw:
        return None
    total, inspected = raw.get("total"), raw.get("inspected")
    reasons = list(raw.get("reasons") or [])
    complete = total is not None and inspected == total and not reasons
    state = (
        CoverageStatus.COMPLETE
        if complete
        else (CoverageStatus.PARTIAL if total is not None else CoverageStatus.UNKNOWN)
    )
    if state is CoverageStatus.UNKNOWN and inspected is not None and not reasons:
        reasons = ["total unknown"]
    try:
        return Coverage(
            status=state,
            unit=raw.get("unit"),
            inspected=inspected,
            total=total,
            missing_ranges=list(raw.get("missing_ranges") or []),
            reasons=reasons,
        )
    except ValueError:
        return None


def _one_document(r: Any, status: Any) -> DocumentCoverage:
    not_indexed: list[str] = []
    notes = list((r.run_summary or {}).get("coverage_notes", [])) if r.run_summary else []
    run_status = r.run_status or (r.extraction_state or "not_extracted")
    text_state: IndexedState
    if r.storage_state != "stored":
        text_state = IndexedState.NOT_INDEXABLE
        not_indexed.append(f"original is {r.storage_state}; excluded from retrieval")
    elif r.run_status is None:
        text_state = IndexedState.NOT_INDEXABLE
        not_indexed.append("extraction has not run yet; nothing to index")
    elif r.run_status == "unsupported":
        text_state = IndexedState.NOT_INDEXABLE
        not_indexed.append("no native profile recognizes this content; nothing was extracted")
    elif r.run_status not in ("succeeded", "partial"):
        text_state = IndexedState.NOT_INDEXABLE
        code = (r.run_error or {}).get("code") if r.run_error else None
        not_indexed.append(f"extraction {r.run_status}" + (f" ({code})" if code else ""))
    elif r.ci_status is None:
        text_state = IndexedState.NOT_STARTED
        not_indexed.append("text index not built yet")
    elif r.ci_status == "complete":
        text_state = IndexedState.PARTIAL if r.ci_truncated else IndexedState.COMPLETE
        if r.ci_truncated:
            not_indexed.append(
                "records after ordinal "
                f"{(r.ci_detail or {}).get('last_record_ordinal')} are not indexed (chunk cap)"
            )
    else:
        text_state = IndexedState(r.ci_status)
        if r.ci_status == "failed":
            not_indexed.append(f"text index failed ({(r.ci_error or {}).get('code')})")
        else:
            not_indexed.append(f"text index {r.ci_status}")
    invalid = r.inv_count or 0
    if r.ci_status == "complete" and invalid:
        if invalid >= (r.ci_chunks or 0):
            text_state = IndexedState.INVALIDATED
            not_indexed.append(
                f"all chunks invalidated ({r.inv_reason or 'unknown reason'}); not searchable"
            )
        else:
            not_indexed.append(f"{invalid} chunks invalidated ({r.inv_reason}); not searchable")
    if r.run_status == "partial":
        not_indexed.append("extraction itself was partial; unextracted content is not searchable")
    vector_state: IndexedState
    if status.spec is None:
        vector_state = (
            IndexedState.DISABLED if status.state == "disabled" else IndexedState.UNAVAILABLE
        )
    elif text_state in (
        IndexedState.NOT_INDEXABLE,
        IndexedState.NOT_STARTED,
        IndexedState.INVALIDATED,
    ):
        vector_state = text_state
    elif r.ei_status is None:
        vector_state = IndexedState.NOT_STARTED
    elif r.ei_status == "complete":
        vector_state = IndexedState.PARTIAL if r.ei_truncated else IndexedState.COMPLETE
        if r.ei_truncated:
            not_indexed.append(
                f"vectors cover the first {r.ei_embedded} of {r.ei_chunks} chunks "
                "(embedding cap); the rest is exact/full-text searchable only"
            )
    else:
        vector_state = IndexedState(r.ei_status)
    if text_state is IndexedState.PARTIAL and vector_state is IndexedState.COMPLETE:
        vector_state = IndexedState.PARTIAL
    excluded = (
        int((r.ei_detail or {}).get("excluded_numeric_table_chunks", 0)) if r.ei_detail else 0
    )
    vector_notes: list[str] = []
    if excluded and vector_state in (IndexedState.COMPLETE, IndexedState.PARTIAL):
        vector_notes.append(
            f"{excluded} numeric-table chunks are excluded from embedding by policy (numeric "
            "tables); they remain exact-identifier and full-text searchable"
        )
    return DocumentCoverage(
        document_id=r.document_id,
        filename=r.original_filename,
        format_family=r.format_family,
        extraction_status=run_status,
        text_index=text_state,
        vector_index=vector_state,
        chunk_count=max(0, (r.ci_chunks or 0) - invalid) if r.ci_status == "complete" else 0,
        embedded_count=r.ei_embedded or 0,
        extraction_coverage=_coverage_dto(r.run_coverage),
        not_indexed=not_indexed,
        vector_excluded_chunks=excluded,
        vector_notes=vector_notes,
        coverage_notes=notes,
    )


def _why_empty(docs: list[_Doc]) -> str:
    """Explain an empty envelope: which documents are pending, invalid or not indexable."""
    counts: dict[str, int] = {}
    for d in docs:
        counts[d.public.text_index.value] = counts.get(d.public.text_index.value, 0) + 1
    if not docs:
        return "The searched revision has no documents."
    parts = ", ".join(f"{n} {state}" for state, n in sorted(counts.items()))
    return f"No document is searchable ({parts}); see coverage for the per-document reasons."


def _index_state(docs: list[_Doc], fingerprint: str | None) -> IndexState:
    text_docs = [
        d for d in docs if d.public.text_index in (IndexedState.COMPLETE, IndexedState.PARTIAL)
    ]
    vector_docs = [
        d
        for d in text_docs
        if d.public.vector_index in (IndexedState.COMPLETE, IndexedState.PARTIAL)
    ]
    indexable = [d for d in docs if d.public.text_index is not IndexedState.NOT_INDEXABLE]
    return IndexState(
        eligible_documents=len(docs),
        text_indexed_documents=len(text_docs),
        vector_indexed_documents=len(vector_docs),
        pending_documents=len(indexable) - len(text_docs),
        index_epoch=_epoch(
            [
                (
                    d.public.document_id,
                    d.public.text_index.value,
                    d.public.vector_index.value,
                    d.public.chunk_count,
                    d.public.embedded_count,
                )
                for d in docs
            ]
        ),
        embedding_fingerprint=fingerprint,
    )


def _degraded_reasons(
    docs: list[_Doc], index: IndexState, problem: EmbedderUnavailable | None
) -> list[DegradedReason]:
    reasons: list[DegradedReason] = []
    if problem is not None:
        try:
            reasons.append(DegradedReason(problem.code))
        except ValueError:
            reasons.append(DegradedReason.EMBEDDING_FAILED)
    if index.text_indexed_documents == 0:
        reasons.append(DegradedReason.NO_INDEXED_DOCUMENTS)
    elif problem is None:
        usable = [
            d for d in docs if d.public.text_index in (IndexedState.COMPLETE, IndexedState.PARTIAL)
        ]
        if any(
            d.public.vector_index not in (IndexedState.COMPLETE, IndexedState.PARTIAL)
            for d in usable
        ):
            reasons.append(DegradedReason.VECTOR_INDEX_INCOMPLETE)
        if any(d.public.vector_index is IndexedState.PARTIAL for d in usable):
            reasons.append(DegradedReason.VECTOR_INDEX_PARTIAL)
    return list(dict.fromkeys(reasons))
