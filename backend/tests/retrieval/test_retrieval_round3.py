"""QA round 2 repairs: relevance bar for vector-only hits, nonexistent sidetrack suffix,
document-level identity blocked by attribute wells, lexical support by discriminative terms,
production vocabulary, ANALYZE drift/visibility, failed-job requeue. Synthetic fixtures."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import pytest

from fieldlens.persistence.session import session_scope
from fieldlens.retrieval import indexer
from fieldlens.retrieval.embedder import FakeHashEmbedder
from fieldlens.retrieval.indexer import requeue_failed_jobs
from fieldlens.retrieval.search import query_terms
from tests.retrieval.support import World, attr, make_world, rec


def note(text: str, label: str = "15/9-F-12", kind: str = "report_note") -> dict[str, Any]:
    return rec(kind, {"wellbore_label": label}, [attr("remark", text)])


class Basis(FakeHashEmbedder):
    """Document vectors with a pinned cosine to one shared query direction ``u`` (the last
    axis): ``cos_by_needle`` gives each document its cosine to a pinned query, exactly."""

    def __init__(self) -> None:
        super().__init__(name="basis")
        self.index: dict[str, int] = {}
        self.cos_by_needle: dict[str, float] = {}
        self.pinned: set[str] = set()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for t in texts:
            k = self.index.setdefault(t, len(self.index))
            a = next((c for n, c in self.cos_by_needle.items() if n in t), 0.0)
            v = [0.0] * self.spec.dimension
            v[k] = math.sqrt(1.0 - a * a)
            v[self.spec.dimension - 1] = a
            out.append(v)
        return out

    def embed_query(self, text: str) -> list[float]:
        if text not in self.pinned:
            return super().embed_query(text)
        v = [0.0] * self.spec.dimension
        v[self.spec.dimension - 1] = 1.0
        return v


def _noise_world(
    migrated_url: Any, tmp_path: Any, question: str, cosines: dict[str, float]
) -> tuple[World, str]:
    world = make_world(migrated_url, tmp_path, retrieval_vector_support_floor=0.68)
    pid = world.project()
    basis = Basis()
    basis.cos_by_needle = cosines
    basis.pinned = {question}
    for i, word in enumerate(["alpha", "bravo", "charlie", "delta", "echo"]):
        world.add_doc(pid, f"{word}.pdf", [note(f"{word} unrelated wording {i}", label=f"W{i}")])
    world.set_embedder(basis)
    world.index()
    return world, pid


# --- A. relevance bar -------------------------------------------------------------------------


def test_noise_level_vector_hits_are_weak_evidence_not_ok(migrated_url: Any, tmp_path: Any) -> None:
    QUESTION = "who won the football match"
    COS = {"alpha": 0.63, "bravo": 0.62, "charlie": 0.62, "delta": 0.61}
    world, pid = _noise_world(migrated_url, tmp_path, QUESTION, COS)
    out = world.search(pid, QUESTION)
    assert out["status"] == "weak_evidence" and out["evidence_strength"] == "weak"
    assert out["hits"] and all(not h["support"]["strong"] for h in out["hits"])
    top = max(h["signals"]["vector_similarity"] for h in out["hits"])
    assert 0.6 < top < 0.64  # the noise-level similarity is returned for the assistant to see
    assert any("must not be cited" in n for n in out["notes"])


def test_above_floor_but_without_margin_over_the_median_is_still_weak(
    migrated_url: Any, tmp_path: Any
) -> None:
    QUESTION = "seismic velocity model"
    COS = {w: 0.72 for w in ("alpha", "bravo", "charlie", "delta", "echo")}
    world, pid = _noise_world(migrated_url, tmp_path, QUESTION, COS)
    out = world.search(pid, QUESTION)
    assert out["status"] == "weak_evidence"
    assert all(h["support"]["vector"] and not h["support"]["strong"] for h in out["hits"])


def test_clear_vector_winner_is_strong_and_noise_next_to_it_is_dropped(
    migrated_url: Any, tmp_path: Any
) -> None:
    QUESTION = "what holds the string"
    COS = {"alpha": 0.80, "bravo": 0.62, "charlie": 0.60, "delta": 0.58}
    world, pid = _noise_world(migrated_url, tmp_path, QUESTION, COS)
    out = world.search(pid, QUESTION)
    assert out["status"] == "ok" and out["evidence_strength"] == "strong"
    assert len(out["hits"]) == 1 and out["hits"][0]["support"] == {
        "exact": False,
        "lexical": False,
        "vector": True,
        "strong": True,
    }
    assert out["hits"][0]["signals"]["vector_similarity"] == pytest.approx(0.80, abs=1e-6)


def test_default_floor_is_raised_and_labelled_uncalibrated() -> None:
    from fieldlens.config import Settings

    s = Settings(_env_file=None)
    assert s.retrieval_vector_support_floor == 0.68 and s.retrieval_vector_margin == 0.04
    doc = (Settings.model_fields["retrieval_vector_margin"].description or "") + (
        Settings.__doc__ or ""
    )
    from pathlib import Path

    src = Path(__import__("fieldlens.config", fromlist=["x"]).__file__).read_text()
    assert "UNCALIBRATED" in src and doc is not None


# --- B. nonexistent sidetrack suffix ----------------------------------------------------------


def _bore(label: str, key: str, text: str) -> dict[str, Any]:
    return rec(
        "trajectory_station",
        {"wellbore_label": label, "well_key": key},
        [attr("md", "1000.5", "m", number=1000.5), attr("remark", text)],
    )


def test_a_suffix_no_source_names_never_resolves_to_the_parent(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "f12.xlsx", [_bore("15/9-F-12", "15/9-F-12", "main bore station")] * 12)
    world.index()
    for q, missing in (
        ("F-12 A trajectory station", "f-12 a"),
        ("F-12 Z trajectory station", "f-12 z"),
        ("F-12 T2 trajectory station", "f-12 t2"),
    ):
        out = world.search(pid, q)
        assert out["status"] in ("weak_evidence", "no_results"), (q, out["status"])
        assert out["evidence_strength"] != "strong" and missing in out["unmatched_identifiers"]
        assert out["exact_matches"] == []  # the parent is not reported as the match
        assert all(not h["support"]["strong"] for h in out["hits"])
    plain = world.search(pid, "F-12 trajectory station")
    assert plain["status"] == "ok" and plain["unmatched_identifiers"] == []


def test_existing_sidetracks_resolve_to_their_own_entity_only(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "main.xlsx", [_bore("15/9-F-12", "15/9-F-12", "parent bore station")] * 6)
    world.add_doc(pid, "side.xlsx", [_bore("15/9-F-12 A", "15/9-F-12", "sidetrack station")] * 6)
    world.index()
    side = world.search(pid, "F-12 A trajectory station")
    assert side["status"] == "ok" and side["unmatched_identifiers"] == []
    assert [m["canonical"] for m in side["exact_matches"]] == ["15/9-f-12 a"]
    assert side["hits"] and all("sidetrack station" in h["text"] for h in side["hits"])
    parent = world.search(pid, "F-12 trajectory station")
    assert parent["status"] == "ok"
    assert parent["hits"] and all("parent bore station" in h["text"] for h in parent["hits"])
    assert not any("sidetrack" in h["text"] for h in parent["hits"])  # child data stays out


# --- C. document-level identity blocked by a different well in an attribute --------------------


def test_attribute_well_blocks_the_document_level_identity(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "mixed.las",
        [
            rec(
                "las_header",
                {"well_name": "15/9-F-12", "well_key": "15/9-F-12"},
                [attr("well", "15/9-F-12")],
            ),
            rec(
                "las_curve",
                {},
                [
                    attr("mnemonic", "GR"),
                    attr("description", "gamma ray"),
                    attr("well", "15/9-F-14"),
                ],
            ),
        ],
    )
    world.index()
    f12 = world.search(pid, "F-12 gamma ray")
    assert all(h["kind"] != "las_curve" for h in f12["hits"])  # the F-14 curve is not F-12's
    f14 = world.search(pid, "F-14 gamma ray")
    assert f14["hits"] and f14["hits"][0]["kind"] == "las_curve"
    assert (
        world.sql("SELECT count(*) FROM chunk_identifier WHERE id_kind='document_well'")[0][0] == 0
    )


# --- D. lexical support by discriminative terms, production vocabulary -------------------------


def test_query_terms_expand_production_vocabulary_and_keep_exact_terms() -> None:
    t = query_terms(["oil", "rate", "F-5", "2010", "perforations"])
    assert t.plain == ["oil", "gas", "water", "vol", "perforations"]
    assert t.exact == ["(f <-> 5)", "2010"]


def _production(n: int) -> list[dict[str, Any]]:
    return [
        rec(
            "production_day",
            {"wellbore_label": "15/9-F-5"},
            [
                attr("bore_oil_vol", f"{100 + i}.5", "Sm3", number=100.0 + i),
                attr("avg_choke_size_p", "12", "%", number=12.0),
            ],
        )
        for i in range(n)
    ]


def test_a_word_that_is_only_a_unit_or_key_name_in_most_rows_does_not_support(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "prod.xlsx",
        [
            rec(
                "production_day",
                {"wellbore_label": "15/9-F-12"},
                [
                    attr("avg_choke_size_p", "12", "%", number=12.0),
                    attr("bore_oil_vol", f"{i}.5", "Sm3", number=float(i)),
                ],
            )
            for i in range(1500)
        ],
    )
    world.add_doc(
        pid,
        "tub.xml",
        [
            rec(
                "tubular_component",
                {"wellbore_label": "15/9-F-12"},
                [
                    attr("description", "production tubing 4.5 in"),
                    attr("od", "4.5", "in", number=4.5),
                ],
            )
        ],
    )
    world.index(limit=500)
    out = world.search(pid, "tubing size F-12")
    assert out["status"] == "ok" and out["hits"][0]["kind"] == "tubular_component"
    assert all(h["kind"] != "production_day" or not h["support"]["lexical"] for h in out["hits"])
    assert [h["kind"] for h in out["hits"]].count("production_day") == 0  # noise dropped


def test_oil_rate_reaches_production_chunks_not_trajectory(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "prod.xlsx", _production(400))
    world.add_doc(
        pid,
        "traj.xlsx",
        [
            rec(
                "trajectory_station",
                {"wellbore_label": "15/9-F-5"},
                [
                    attr("md", f"{1000 + i}.5", "m", number=1000.5 + i),
                    attr("rop", "rate of penetration", None),
                ],
            )
            for i in range(60)
        ],
    )
    world.index(limit=500)
    out = world.search(pid, "oil rate F-5")
    assert out["status"] == "ok" and out["hits"][0]["kind"] == "production_day"
    assert out["exact_matches"][0]["canonical"] == "15/9-f-5"


# --- E. ANALYZE cost and visibility ----------------------------------------------------------


def test_analyze_runs_on_drift_not_after_every_job_and_failure_is_visible(
    world: World, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pid = world.project()
    world.add_doc(pid, "big.xlsx", [note(f"reading alpha{i} beta gamma") for i in range(3000)])
    world.index(limit=500)
    stamp = lambda: world.sql(  # noqa: E731
        "SELECT last_analyze FROM pg_stat_user_tables WHERE relname = 'evidence_chunk'"
    )[0][0]
    first = stamp()
    assert first is not None
    world.add_doc(pid, "tiny.pdf", [note("one more note")])  # 0.1% drift: no new ANALYZE
    world.index(limit=500)
    assert stamp() == first
    assert world.coverage(pid)["warnings"] == []
    monkeypatch.setattr(indexer, "ANALYZED_TABLES", ("no_such_table",))
    world.add_doc(pid, "another.pdf", [note("another note")])
    with caplog.at_level("ERROR"):
        world.index(limit=500)
    assert any("ANALYZE failed" in r.message for r in caplog.records)
    warnings = world.coverage(pid)["warnings"]
    assert warnings and "planner statistics refresh failed" in warnings[0]
    monkeypatch.undo()
    world.add_doc(pid, "recover.pdf", [note("recovery note")])
    world.index(limit=500)
    assert world.coverage(pid)["warnings"] == []


# --- requeue of exhausted failed jobs ---------------------------------------------------------


class Broken(FakeHashEmbedder):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise RuntimeError("down")


def test_failed_index_jobs_are_requeued_on_process_start_and_on_demand(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "a.pdf", [note("alpha wording to embed")])
    world.set_embedder(Broken())
    world.index()
    cov = world.coverage(pid)["documents"][0]
    assert cov["text_index"] == "complete" and cov["vector_index"] == "failed"
    world.set_embedder(FakeHashEmbedder())
    world.index()  # same process: a failed job is not retried by itself
    assert world.coverage(pid)["documents"][0]["vector_index"] == "failed"
    with session_scope(world.factory) as session:
        assert requeue_failed_jobs(session, UUID(int=5)) == 0  # other project: untouched
    world.api.worker.indexing._startup_requeued = False  # "process start"
    world.index()
    assert world.coverage(pid)["documents"][0]["vector_index"] == "complete"
    with session_scope(world.factory) as session:
        assert requeue_failed_jobs(session, UUID(pid)) == 0  # nothing failed any more


# --- round 3: frequent words, real sidetrack subject shapes ---------------------------------


def test_all_frequent_or_schema_words_give_no_lexical_support(
    migrated_url: Any, tmp_path: Any
) -> None:
    world = make_world(migrated_url, tmp_path, retrieval_vector_support_floor=0.68)
    pid = world.project()
    for i in range(60):
        world.add_doc(pid, f"n{i}.pdf", [note(f"well depth size reading {i}", label=f"W{i}")])
    world.add_doc(pid, "p.pdf", [note("packer setting min value", label="WP")])
    world.index(limit=500)
    for q in ("well", "size", "tell me about the well", "the well depth size", "min"):
        out = world.search(pid, q)
        assert out["status"] == "weak_evidence", (q, out["status"])
        assert all(not h["support"]["lexical"] for h in out["hits"]), q
    legit = world.search(pid, "packer setting")
    assert legit["status"] == "ok" and legit["hits"][0]["support"]["lexical"]


def _perf(subject: dict[str, str], n: int = 3) -> list[dict[str, Any]]:
    return [
        rec(
            "perforation_interval",
            subject,
            [attr("top_md", f"{3000 + i}", None, number=3000.0 + i)],
        )
        for i in range(n)
    ]


def test_sidetrack_rows_with_real_subject_shapes_stay_out_of_the_parent_query(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "parent.dat",
        _perf({"well_key": "15/9-F-11", "well_name": "NO 15/9-F-11", "remark": "parent"}),
    )
    world.add_doc(
        pid,
        "b.dat",
        _perf({"well_key": "15/9-F-11", "well_name": "NO 15/9-F-11 B", "wellbore_suffix": "B"}),
    )
    world.add_doc(
        pid,
        "a.dat",
        _perf({"well_key": "15/9-F-11", "well_name": "NO 15/9-F-11", "wellbore_suffix": "A"}),
    )
    world.add_doc(
        pid, "t.dat", _perf({"well_key": "15/9-F-11", "wellbore_label": "NO 15/9-F-11 T2"})
    )
    world.index()
    parent = world.search(pid, "F-11 perforation")
    docs = {h["document_id"] for h in parent["hits"]}
    assert docs == {str(world.docs["parent.dat"].document_id)}, docs
    assert parent["hits"] and parent["status"] == "ok"
    for q, name in (
        ("F-11 B perforation", "b.dat"),
        ("F-11 A perforation", "a.dat"),
        ("F-11 T2 perforation", "t.dat"),
    ):
        out = world.search(pid, q)
        assert out["status"] == "ok" and out["unmatched_identifiers"] == [], (
            q,
            out["unmatched_identifiers"],
        )
        assert {h["document_id"] for h in out["hits"]} == {str(world.docs[name].document_id)}, q


def test_identifier_change_bumps_the_chunker_version_so_indexes_are_rebuilt() -> None:
    from fieldlens.retrieval.chunker import CHUNKER_VERSION

    assert CHUNKER_VERSION != "chunker-2"  # stored identifiers changed: chunker-2 rows are deleted
