"""Opt-in: chunking and exact/full-text retrieval over the approved local Volve subset.

    FIELDLENS_LOCAL_DATA_ROOT=... uv run pytest backend/tests/retrieval/test_local_data_retrieval.py -m local_data -s

Read-only, in place, nothing transmitted. The embedder is the offline fake here, so this shows
chunk bounds/number safety and exact-ID + lexical behavior on REAL extracted observations; it says
nothing about real-model semantic recall (see test_local_embedder.py for the real model)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.engine import URL

from fieldlens.extraction.runner import _time
from fieldlens.ingestion.inspect import inspect_file
from fieldlens.profiles import registry
from fieldlens.profiles.types import ParseContext
from fieldlens.retrieval.chunker import MAX_TOKENS, RecordIn, _cell, chunk_records
from tests.retrieval.support import World, make_world

pytestmark = pytest.mark.local_data

_ROOT_ENV = os.environ.get("FIELDLENS_LOCAL_DATA_ROOT")
if not _ROOT_ENV or not Path(_ROOT_ENV).is_dir():
    pytest.skip("FIELDLENS_LOCAL_DATA_ROOT is not set to a directory", allow_module_level=True)
ROOT = Path(_ROOT_ENV)

WITSML = "WITSML Realtime drilling data/Norway-Statoil-NO 15_$47$_9-{w}/1/{obj}/1.xml"
SURVEY = "Well_technical_data/WellWellbore/15_9-{w}/15_9-{w}/Standard Survey Report_Volve F_{w}_{w}_{w}_ACTUAL.pdf"
LAS = "Well_logs_pr_WELL/15_9-{w}/02.LWD_EWL/WL_RAW_BHPR-GR-MECH_MWD_1.LAS"
WELLS = ("F-12", "F-14", "F-5")
SMALL = [
    "Geophysical_Interpretations/Wells/Well_perforations_Volve.dat",
    "Geophysical_Interpretations/Wells/Well_picks_Volve_v1.dat",
]
PRODUCTION = "Production_data/Volve production data.xlsx"


def _paths(with_production: bool) -> list[str]:
    out = list(SMALL) + ([PRODUCTION] if with_production else [])
    for w in WELLS:
        out += [WITSML.format(w=w, obj=o) for o in ("tubular", "bhaRun", "wbGeometry")]
        out += [SURVEY.format(w=w), LAS.format(w=w)]
    return out


def _parse(rel: str) -> list[Any]:
    path = ROOT / rel
    family = inspect_file(
        path, path.name, max_file_bytes=2 * 1024**3, remaining_batch_bytes=2 * 1024**3
    ).format_family
    profile = registry.detect(path, family, path.name)[0]
    out = profile.parse(path, ParseContext(uuid4(), uuid4(), "0" * 64, path.name))
    return list(out.records)


def _row(rec: Any) -> dict[str, Any]:
    return {
        "kind": rec.kind,
        "subject": rec.subject,
        "locator": rec.locator,
        "effective_time": _time(rec.effective_time),
        "validation_state": rec.validation_state,
        "attributes": [a.to_json() for a in rec.attrs],
    }


def test_real_subset_chunks_are_bounded_complete_and_number_safe() -> None:
    total_records = total_chunks = 0
    for rel in _paths(with_production=True):
        records = [
            RecordIn(
                i,
                uuid4(),
                r.kind,
                r.subject,
                r.locator,
                None,
                r.validation_state,
                [a.to_json() for a in r.attrs],
            )
            for i, r in enumerate(_parse(rel))
        ]
        chunks = list(chunk_records(records, "0" * 64))
        assert all(1 <= c.token_count <= MAX_TOKENS for c in chunks), rel
        assert {i for c in chunks for i in c.record_ids} == {r.record_id for r in records}, rel
        by_record: dict[Any, str] = {}
        for c in chunks:
            for rid in c.record_ids:
                by_record[rid] = by_record.get(rid, "") + "\n" + c.text
        step = max(1, len(records) // 400)
        for rec in records[::step]:
            for attr in rec.attributes:
                cell = _cell(attr, rec.kind)
                head, _, value = cell.partition("=")
                if len(cell) < 200:  # whole cells (numbers with their unit) are never cut
                    assert cell in by_record[rec.record_id], (rel, cell)
        total_records += len(records)
        total_chunks += len(chunks)
    print(f"real subset: {total_records} records -> {total_chunks} chunks")


def test_real_subset_worst_wordpiece_count_by_the_real_tokenizer() -> None:
    from fieldlens.retrieval import model_manifest as mm

    if mm.verify_model_dir(mm.DEFAULT_DIR) is not None:
        pytest.skip("local embedding model is not installed")
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(mm.DEFAULT_DIR / "tokenizer.json"))
    worst = worst_est = n_embed = n_numeric = 0
    for rel in _paths(with_production=True):
        records = [
            RecordIn(
                i,
                uuid4(),
                r.kind,
                r.subject,
                r.locator,
                None,
                r.validation_state,
                [a.to_json() for a in r.attrs],
            )
            for i, r in enumerate(_parse(rel))
        ]
        for c in chunk_records(records, "0" * 64):
            worst = max(worst, len(tokenizer.encode(c.text).ids))
            worst_est = max(worst_est, c.token_count)
            n_numeric += c.vector_policy == "numeric_table"
            n_embed += c.vector_policy == "embed"
    print(
        f"worst wordpieces {worst} (worst estimate {worst_est}); embed={n_embed} numeric={n_numeric}"
    )
    assert worst <= mm.MAX_TOKENS and worst_est <= MAX_TOKENS


@pytest.mark.parametrize("analyze", [False, True], ids=["no-analyze", "analyze"])
def test_real_subset_first_search_latency_with_the_production_workbook(
    migrated_url: URL, tmp_path: Path, analyze: bool
) -> None:
    import time

    world = make_world(migrated_url, tmp_path, retrieval_analyze_after_index=analyze)
    pid = world.project("Volve full subset")
    for rel in _paths(with_production=True):
        world.add_doc(pid, Path(rel).name, [_row(r) for r in _parse(rel)])
    t0 = time.perf_counter()
    world.index(limit=2000)
    index_s = time.perf_counter() - t0
    timings = []
    for q in ("F-12 survey measured depth", "what perforations were made in F-5", "gamma ray"):
        t1 = time.perf_counter()
        out = world.search(pid, q)
        timings.append((q, round(time.perf_counter() - t1, 2), out["status"], out["mode"]))
    print(f"analyze={analyze}: index {index_s:.1f}s, first searches {timings}")
    if analyze:
        assert timings[0][1] < 5.0, timings


@pytest.fixture
def real_world(migrated_url: URL, tmp_path: Path) -> tuple[World, str]:
    world = make_world(migrated_url, tmp_path)
    pid = world.project("Volve subset")
    for rel in _paths(with_production=False):
        world.add_doc(pid, Path(rel).name, [_row(r) for r in _parse(rel)])
    world.index(limit=400)
    return world, pid


def test_real_subset_exact_ids_and_source_lookup(real_world: tuple[World, str]) -> None:
    world, pid = real_world
    cov = world.coverage(pid)
    assert all(d["text_index"] == "complete" for d in cov["documents"]), cov["documents"]
    results = {}
    for well in WELLS:
        out = world.search(pid, f"{well} survey measured depth")
        results[well] = (
            out["status"],
            [m["canonical"] for m in out["exact_matches"]],
            [a["identifier"] for a in out["ambiguities"]],
            len(out["hits"]),
        )
        print(
            well,
            results[well],
            [
                (c["canonical"], c["kinds"], c["chunk_count"])
                for a in out["ambiguities"]
                for c in a["candidates"]
            ],
        )
        assert out["status"] in ("ok", "ambiguous")
        if out["status"] == "ok":
            assert out["hits"], well
            assert all(well in h["text"] or well.replace("-", "") in h["text"] for h in out["hits"])
    perf = world.search(pid, "perforation interval")
    assert any(h["kind"] == "perforation_interval" for h in perf["hits"])
    picks = world.search(pid, "formation pick top")
    assert any(h["kind"] == "formation_pick" for h in picks["hits"])
    cross = world.search(pid, "F-5 tubular component")
    print("F-5 tubular:", cross["status"], [h["kind"] for h in cross["hits"]])
