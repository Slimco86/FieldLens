"""QA repair round (October 31): planner statistics, control characters, mode honesty,
weak-evidence flagging, invalidation coverage, stemming, document-level well identity, exact
scope as a filter, diversity guard, numeric-table vector policy. Synthetic; fake embedders."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import pytest

from fieldlens.persistence.session import session_scope
from fieldlens.retrieval import chunker
from fieldlens.retrieval.chunker import RecordIn, chunk_records, vector_policy_of
from fieldlens.retrieval.embedder import FakeHashEmbedder
from fieldlens.retrieval.indexer import invalidate_document_chunks
from fieldlens.retrieval.search import tsqueries_for
from tests.retrieval.support import World, attr, make_world, rec


def note(text: str, label: str = "15/9-F-12", kind: str = "report_note") -> dict[str, Any]:
    return rec(kind, {"wellbore_label": label}, [attr("remark", text)])


# --- 1. planner statistics / first-search latency ------------------------------------------


def test_analyze_runs_after_index_jobs_and_first_search_is_fast(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "big.xlsx", [note(f"reading alpha{i} beta gamma") for i in range(6000)])
    world.index(limit=2000)
    rows = world.sql(
        "SELECT relname, last_analyze FROM pg_stat_user_tables WHERE relname IN "
        "('evidence_chunk','chunk_identifier','chunk_embedding','retrieval_index')"
    )
    assert len(rows) == 4 and all(r.last_analyze is not None for r in rows), rows
    stats = world.sql("SELECT reltuples FROM pg_class WHERE relname = 'evidence_chunk'")[0][0]
    actual = world.sql("SELECT count(*) FROM evidence_chunk")[0][0]
    assert actual > 100 and abs(stats - actual) / actual < 0.1, (stats, actual)
    started = time.perf_counter()
    out = world.search(pid, "F-12 reading alpha77 beta")
    assert out["hits"]
    assert time.perf_counter() - started < 3.0  # deterministic guard is the stats check above


def test_analyze_can_be_switched_off_for_measurement(migrated_url: Any, tmp_path: Any) -> None:
    world = make_world(migrated_url, tmp_path, retrieval_analyze_after_index=False)
    pid = world.project()
    world.add_doc(pid, "a.pdf", [note("alpha")])
    world.index()
    row = world.sql(
        "SELECT last_analyze FROM pg_stat_user_tables WHERE relname = 'evidence_chunk'"
    )[0]
    assert row.last_analyze is None


# --- 2. control characters ------------------------------------------------------------------


def test_nul_and_control_characters_are_rejected_at_the_route_and_safe_in_the_service(
    world: World,
) -> None:
    pid = world.project()
    world.add_doc(pid, "a.pdf", [note("packer setting depth")])
    world.index()
    client = world.api.client
    base = f"/api/v1/projects/{pid}/retrieval/search"
    for bad in ("a\x00b", "\x00", "x\x07y", "\x1f", "F-12\x00"):
        r = client.get(base, params={"q": bad})
        assert r.status_code == 422, (bad, r.status_code)
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(base, params={"q": "   "}).status_code == 422
    assert client.get(base, params={"q": "packer", "document_id": "a\x00"}).status_code == 422
    assert client.get(base, params={"q": "packer", "source_revision_id": "\x00"}).status_code == 422
    assert (
        client.get(
            f"/api/v1/projects/{pid}/retrieval/coverage", params={"source_revision_id": "\x00"}
        ).status_code
        == 422
    )
    assert client.get(base, params={"q": "tab\tand\nnewline ok packer"}).status_code == 200
    out = world.api.client.app.state.retrieval.search_evidence(UUID(pid), "packer\x00 depth\x07")
    assert out.hits  # control characters become spaces; no database error


# --- 3. mode honesty ------------------------------------------------------------------------


class BadQuery(FakeHashEmbedder):
    def __init__(self, mode: str) -> None:
        super().__init__()  # same spec/fingerprint as the index embedder
        self.mode = mode

    def embed_query(self, text: str) -> list[float]:
        n = self.spec.dimension
        return {
            "zero": [0.0] * n,
            "nan": [float("nan")] * n,
            "short": [0.1] * 10,
            "inf": [float("inf")] * n,
        }[self.mode]


@pytest.mark.parametrize("mode", ["zero", "nan", "short", "inf"])
def test_invalid_query_embeddings_are_explicit_degraded_not_hybrid(world: World, mode: str) -> None:
    pid = world.project()
    world.add_doc(pid, "a.pdf", [note("packer setting depth")])
    world.index()
    world.set_embedder(BadQuery(mode))
    out = world.search(pid, "packer setting depth")
    assert out["mode"] == "degraded"
    assert out["degraded_reasons"] == ["query_embedding_invalid"]
    assert out["hits"] and all(h["signals"]["vector_rank"] is None for h in out["hits"])


# --- 4. relevance signal --------------------------------------------------------------------


class Pinned(FakeHashEmbedder):
    """Maps one nonsense question to the vector of a chosen chunk text: a vector-only match."""

    def __init__(self, question: str, target_text: str) -> None:
        super().__init__(name="pinned")
        self.question, self.target = question, target_text

    def embed_query(self, text: str) -> list[float]:
        return self._vec(self.target if text == self.question else text)


def test_nonsense_and_foreign_uuid_queries_are_weak_evidence_never_ok(
    migrated_url: Any, tmp_path: Any
) -> None:
    world = make_world(migrated_url, tmp_path, retrieval_vector_support_floor=0.6)
    a, b = world.project("A"), world.project("B")
    world.add_doc(a, "a.pdf", [note(f"packer setting depth report {i}") for i in range(5)])
    other = world.add_doc(b, "b.pdf", [note("secret")])
    world.index()
    for q in ("qzxv wplk mnbt", "zebra violin cheese", str(other.document_id)):
        out = world.search(a, q)
        assert out["status"] in ("weak_evidence", "no_results"), (q, out["status"])
        assert out["evidence_strength"] in ("weak", "none")
        assert all(
            not (h["support"]["exact"] or h["support"]["lexical"] or h["support"]["vector"])
            for h in out["hits"]
        )
        assert out["vector_support_floor"] == 0.6
    assert world.search(a, str(other.document_id))["unmatched_identifiers"] == [
        str(other.document_id)
    ]


def test_lexical_query_stays_ok_and_vector_only_query_above_floor_is_supported(
    migrated_url: Any, tmp_path: Any
) -> None:
    world = make_world(migrated_url, tmp_path, retrieval_vector_support_floor=0.6)
    pid = world.project()
    target = "packer setting depth report number one"
    world.add_doc(pid, "a.pdf", [note(target)])
    world.add_doc(pid, "b.pdf", [note("casing cement volume other wording")])
    world.set_embedder(Pinned("what holds the tubing", target))
    world.index()
    lexical = world.search(pid, "packer setting depth")
    assert lexical["status"] == "ok" and lexical["evidence_strength"] == "strong"
    assert lexical["hits"][0]["support"]["lexical"] is True
    vector_only = world.search(pid, "what holds the tubing")
    assert vector_only["status"] == "ok"
    top = vector_only["hits"][0]
    assert top["support"] == {"exact": False, "lexical": False, "vector": True}
    assert top["signals"]["vector_similarity"] >= 0.6
    assert all(h["support"]["vector"] for h in vector_only["hits"])  # noise below floor dropped


def test_id_only_query_needs_no_topical_support(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "a.pdf", [note("zzz unrelated wording", label="15/9-F-12")])
    world.index()
    out = world.search(pid, "F-12")
    assert out["status"] == "ok" and out["hits"][0]["support"]["exact"] is True


# --- 5. invalidation coverage ---------------------------------------------------------------


def test_invalidated_documents_are_reported_and_the_empty_envelope_explains(world: World) -> None:
    pid = world.project()
    doc = world.add_doc(pid, "a.pdf", [note("alpha invalidated wording")])
    world.index()
    with session_scope(world.factory) as session:
        invalidate_document_chunks(session, UUID(pid), doc.document_id, "source_removed")
    cov = world.coverage(pid)
    d = cov["documents"][0]
    assert d["text_index"] == "invalidated" and d["vector_index"] == "invalidated"
    assert d["chunk_count"] == 0 and any("source_removed" in x for x in d["not_indexed"])
    assert cov["index"]["text_indexed_documents"] == 0
    out = world.search(pid, "alpha")
    assert out["status"] == "no_results" and out["hits"] == []
    assert "no_indexed_documents" in out["degraded_reasons"]
    assert any("1 invalidated" in n for n in out["notes"])


# --- 6a. stemming ---------------------------------------------------------------------------


def test_stemmed_and_exact_lexical_without_vectors(world_no_embedder: World) -> None:
    world = world_no_embedder
    pid = world.project()
    world.add_doc(
        pid,
        "perf.dat",
        [
            rec(
                "perforation_interval",
                {"wellbore_label": "15/9-F-5"},
                [
                    attr("top_md", "3047", None, number=3047.0),
                    attr("note", "reperforation campaign"),
                ],
            )
        ],
    )
    world.add_doc(
        pid,
        "tub.xml",
        [
            rec(
                "tubular_component",
                {"wellbore_label": "15/9-F-5"},
                [
                    attr("description", "production tubing 4.5 in"),
                    attr("od", "4.5", "in", number=4.5),
                ],
            )
        ],
    )
    world.add_doc(
        pid,
        "cas.pdf",
        [
            rec(
                "casing_point",
                {"wellbore_label": "15/9-F-5"},
                [attr("description", "casing shoe"), attr("shoe_md", "3210", "m", number=3210.0)],
            )
        ],
    )
    world.add_doc(
        pid,
        "cmp.pdf",
        [
            rec(
                "completion_string",
                {"wellbore_label": "15/9-F-5"},
                [attr("description", "completion packer assembly")],
            )
        ],
    )
    world.index()
    cases = {
        "what perforations were made in F-5": "perforation_interval",
        "which perforation": "perforation_interval",
        "tubings and their sizes in F-5": "tubular_component",
        "casings used": "casing_point",
        "completions installed in F-5": "completion_string",
    }
    for q, kind in cases.items():
        out = world.search(pid, q)
        assert kind in {h["kind"] for h in out["hits"][:3]}, (q, [h["kind"] for h in out["hits"]])
    # numbers and identifiers stay exact phrases: no stemming, no prefix matching
    assert tsqueries_for(["3047", "perforations", "F-5"]) == (
        "3047 | perforations | (f <-> 5)",
        "perforations",
    )
    assert world.search(pid, "30470")["hits"] == [] or all(
        "3047" not in h["text"].replace("30470", "") for h in world.search(pid, "30470")["hits"]
    )
    exact_number = world.search(pid, "top_md 3047")
    assert exact_number["hits"][0]["kind"] == "perforation_interval"


# --- 6b. document-level well identity -------------------------------------------------------


def test_single_well_document_chunks_are_reachable_by_well_plus_topic(world: World) -> None:
    pid = world.project()
    las = [
        rec(
            "las_header",
            {"well_name": "15/9-F-12", "well_key": "15/9-F-12"},
            [attr("well", "15/9-F-12")],
        ),
        rec(
            "las_curve",
            {},
            [attr("mnemonic", "GR"), attr("description", "gamma ray"), attr("unit", "gAPI")],
        ),
        rec("las_curve", {}, [attr("mnemonic", "RHOB"), attr("description", "bulk density")]),
    ]
    world.add_doc(pid, "log.las", las)
    world.add_doc(
        pid,
        "other.las",
        [
            rec(
                "las_header",
                {"well_name": "15/9-F-14", "well_key": "15/9-F-14"},
                [attr("well", "x")],
            ),
            rec("las_curve", {}, [attr("mnemonic", "GR"), attr("description", "gamma ray")]),
        ],
    )
    world.index()
    out = world.search(pid, "F-12 gamma ray")
    kinds = [h["kind"] for h in out["hits"]]
    assert "las_curve" in kinds, kinds
    doc12 = str(world.docs["log.las"].document_id)
    assert {h["document_id"] for h in out["hits"]} == {doc12}  # not F-14's identical curve
    kinds_by_doc = world.sql(
        "SELECT DISTINCT id_kind FROM chunk_identifier ci JOIN evidence_chunk c USING (chunk_id) "
        "WHERE c.kind = 'las_curve'"
    )
    assert {r[0] for r in kinds_by_doc} == {"document_well"}


def test_multi_well_or_unidentified_documents_get_no_document_identity(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "picks.dat",
        [
            rec("formation_pick", {"wellbore_label": "15/9-F-12"}, [attr("surface", "Hugin top")]),
            rec(
                "formation_pick",
                {"wellbore_label": "15/9-F-14"},
                [attr("surface", "Skagerrak top")],
            ),
            rec("formation_pick", {}, [attr("surface", "Unlabelled orphan pick")]),
        ],
    )
    world.index()
    assert (
        world.sql("SELECT count(*) FROM chunk_identifier WHERE id_kind='document_well'")[0][0] == 0
    )
    out = world.search(pid, "F-12 orphan pick")
    assert all("Unlabelled" not in h["text"] for h in out["hits"])


# --- 6c. exact identification is a scope, not a ranking list --------------------------------


def test_topical_chunks_outrank_bulk_rows_of_the_same_well(world: World) -> None:
    pid = world.project()
    stations = [
        rec(
            "survey_note",
            {"wellbore_label": "15/9-F-12", "well_key": "15/9-F-12"},
            [attr("remark", f"station reading {i} inclination azimuth")],
        )
        for i in range(80)
    ]
    world.add_doc(pid, "survey.pdf", stations)
    world.add_doc(
        pid,
        "cas.pdf",
        [
            rec(
                "casing_point",
                {"wellbore_label": "15/9-F-12", "well_key": "15/9-F-12"},
                [attr("description", "casing shoe depth 3210 m")],
            )
        ],
    )
    world.add_doc(
        pid,
        "tub.pdf",
        [
            rec(
                "tubular_component",
                {"wellbore_label": "15/9-F-12", "well_key": "15/9-F-12"},
                [attr("description", "tubing size 4.5 in")],
            )
        ],
    )
    world.add_doc(
        pid,
        "bha.pdf",
        [
            rec(
                "bha_run",
                {"wellbore_label": "15/9-F-12", "well_key": "15/9-F-12"},
                [attr("description", "rotary steerable assembly")],
            )
        ],
    )
    world.index()
    casing = world.search(pid, "casing shoe depth F-12")
    assert casing["hits"][0]["kind"] == "casing_point", [h["kind"] for h in casing["hits"]]
    tubing = world.search(pid, "tubing size F-12")
    assert tubing["hits"][0]["kind"] == "tubular_component", [h["kind"] for h in tubing["hits"]]
    assert all(h["signals"]["exact"] for h in casing["hits"])


# --- 6d. diversity --------------------------------------------------------------------------


def test_one_record_kind_cannot_flood_an_unscoped_query(world: World) -> None:
    pid = world.project()
    for i in range(30):
        world.add_doc(
            pid, f"p{i}.xlsx", [note("pressure test volume", label=f"W{i}", kind="production_note")]
        )
    for i in range(3):
        world.add_doc(
            pid, f"c{i}.pdf", [note("pressure test casing", label=f"C{i}", kind="casing_point")]
        )
    world.index(limit=500)
    out = world.search(pid, "pressure test")
    kinds = [h["kind"] for h in out["hits"]]
    assert kinds.count("production_note") <= 5 and "casing_point" in kinds, kinds
    scoped = world.search(pid, "W3 pressure test")
    assert scoped["exact_matches"]  # an exact scope is not diversified away


# --- chunker hard cap / numeric policy ------------------------------------------------------


def _r(i: int, kind: str, attrs: list[dict[str, Any]]) -> RecordIn:
    return RecordIn(
        i,
        UUID(int=i + 1),
        kind,
        {"wellbore_label": "W"},
        {"kind": "text", "line_start": 1, "line_end": 1},
        None,
        "unreviewed",
        attrs,
    )


def test_hard_cap_is_480_and_version_bumped() -> None:
    assert chunker.MAX_TOKENS == 480 and chunker.CHUNKER_VERSION == "chunker-2"
    assert chunker.TARGET_TOKENS == 400


def test_numeric_dominated_rule_is_deterministic_and_documented() -> None:
    nums = [
        _r(
            i,
            "custom_series",
            [attr("a", "1.5", "m", number=1.5), attr("b", "2", None, number=2.0)],
        )
        for i in range(10)
    ]
    assert vector_policy_of("custom_series", nums) == "numeric_table"
    assert vector_policy_of("production_day", nums[:1]) == "numeric_table"  # explicit kind
    assert vector_policy_of("trajectory_station", nums[:1]) == "numeric_table"
    assert vector_policy_of("custom_series", nums[:7]) == "embed"  # too few records for a table
    prose = [
        *nums[:9],
        _r(99, "custom_series", [attr("remark", "a long free text remark about the well")]),
    ]
    assert vector_policy_of("custom_series", prose) == "embed"  # prose present
    mixed = [
        _r(i, "custom_series", [attr("a", "1", None, number=1.0), attr("t", "label")])
        for i in range(10)
    ]
    assert vector_policy_of("custom_series", mixed) == "embed"  # ratio 0.5 < 0.8
    chunks = list(chunk_records(nums, "0" * 64))
    assert {c.vector_policy for c in chunks} == {"numeric_table"}


def test_numeric_tables_are_excluded_by_policy_not_partial_and_stay_searchable(
    world: World,
) -> None:
    pid = world.project()
    prod = [
        rec(
            "production_day",
            {"wellbore_label": "15/9-F-14"},
            [
                attr("bore_oil_vol", f"{800 + i}.4", "Sm3", number=800.0 + i),
                attr("bore_wat_vol", "95.2", "Sm3", number=95.2),
            ],
        )
        for i in range(300)
    ]
    world.add_doc(pid, "production.xlsx", prod)
    world.add_doc(pid, "notes.pdf", [note("packer setting depth report", label="15/9-F-14")])
    world.index(limit=500)
    cov = {d["filename"]: d for d in world.coverage(pid)["documents"]}
    p = cov["production.xlsx"]
    assert p["text_index"] == "complete" and p["vector_index"] == "complete"
    assert p["embedded_count"] == 0 and p["vector_excluded_chunks"] == p["chunk_count"] > 0
    assert any("excluded from embedding by policy" in x for x in p["vector_notes"])
    assert p["not_indexed"] == []
    assert (
        cov["notes.pdf"]["vector_index"] == "complete"
        and cov["notes.pdf"]["vector_excluded_chunks"] == 0
    )
    assert world.sql("SELECT count(*) FROM chunk_embedding")[0][0] == 1
    out = world.search(pid, "F-14 packer setting depth")
    assert out["mode"] == "hybrid" and out["degraded_reasons"] == []  # not degraded by policy
    prod_hits = world.search(pid, "15/9-F-14 bore_oil_vol 805.4")
    assert prod_hits["status"] == "ok"
    prod_hit = next(h for h in prod_hits["hits"] if h["kind"] == "production_day")
    assert prod_hit["signals"]["vector_rank"] is None and prod_hit["support"]["lexical"]
    assert world.search(pid, "production oil volume")["hits"]  # full text still covers it


def test_envelope_revision_semantics(world: World) -> None:
    pid = world.project()
    first = world.add_doc(pid, "a.pdf", [note("alpha wording")])
    second = world.add_doc(pid, "b.pdf", [note("beta wording")])
    world.index()
    out = world.search(pid, "alpha")
    assert out["source_revision_id"] == str(second.revision_id)  # the searched revision
    hit = out["hits"][0]
    assert hit["searched_revision_id"] == str(second.revision_id)
    assert hit["source_revision_id"] == str(first.revision_id)  # originating extraction revision
