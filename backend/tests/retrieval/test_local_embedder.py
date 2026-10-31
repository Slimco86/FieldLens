"""Opt-in: the real local embedder (BAAI/bge-small-en-v1.5 int8 ONNX via FastEmbed).

    uv run python scripts/fetch_embedding_model.py          # explicit one-off setup, not a test
    uv run pytest backend/tests/retrieval/test_local_embedder.py -m local_embedder -s

Excluded from default runs (``-m 'not local_embedder'``) and skipped when the model is absent;
it never downloads (the loader is ``local_files_only`` and the suite denies external sockets).
It records dimension, load time, per-chunk latency, RSS and the similarity distribution used to
choose ``retrieval_min_vector_similarity``. Synthetic content: no claim about real-data recall."""

from __future__ import annotations

import resource
import statistics
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.engine import URL

from fieldlens.retrieval import model_manifest as mm
from fieldlens.retrieval.chunker import RecordIn, chunk_records
from fieldlens.retrieval.embedder import FastEmbedEmbedder
from tests.retrieval import test_chunker
from tests.retrieval.support import attr, make_world, rec

pytestmark = pytest.mark.local_embedder

if mm.verify_model_dir(mm.DEFAULT_DIR) is not None:  # pragma: no cover - environment dependent
    pytest.skip("local embedding model is not installed", allow_module_level=True)


def _rss_mib() -> float:
    with open("/proc/self/status") as handle:
        for line in handle:
            if line.startswith("VmRSS"):
                return int(line.split()[1]) / 1024
    return 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_real_embedder_dimension_norm_fingerprint_latency_and_rss(record_property: Any) -> None:
    before = _rss_mib()
    t0 = time.perf_counter()
    embedder = FastEmbedEmbedder(mm.DEFAULT_DIR)
    embedder.embed_documents(["warm up"])
    load_s = time.perf_counter() - t0
    assert embedder.spec.dimension == 384 and embedder.spec.quantization == "int8-onnx"
    assert embedder.spec.model_revision.endswith(mm.SOURCE_REVISION)
    assert FastEmbedEmbedder(mm.DEFAULT_DIR).spec.fingerprint == embedder.spec.fingerprint

    records: list[RecordIn] = test_chunker.table(700)
    chunks = list(chunk_records(records, "0" * 64))[:64]
    texts = [c.text for c in chunks]
    t0 = time.perf_counter()
    vectors = embedder.embed_documents(texts)
    per_chunk_ms = (time.perf_counter() - t0) / len(texts) * 1000
    assert len(vectors) == len(texts) and all(len(v) == 384 for v in vectors)
    assert abs(_cosine(vectors[0], vectors[0]) - 1.0) < 1e-3  # L2 normalized
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    stats = {
        "load_s": round(load_s, 2),
        "per_chunk_ms": round(per_chunk_ms, 1),
        "rss_before_mib": round(before),
        "rss_after_mib": round(_rss_mib()),
        "peak_rss_mib": round(peak),
    }
    for key, value in stats.items():
        record_property(key, value)
    print("real embedder:", stats)
    assert peak < 1536, "architecture worker RSS ceiling (1536 MiB)"


def test_chunks_fit_the_embedder_window_by_the_real_tokenizer() -> None:
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(mm.DEFAULT_DIR / "tokenizer.json"))
    chunks = list(chunk_records(test_chunker.table(1500), "0" * 64))
    worst = max(len(tokenizer.encode(c.text).ids) for c in chunks)
    print("worst wordpieces per synthetic chunk:", worst)
    assert worst <= mm.MAX_TOKENS


def test_real_similarity_ordering_and_distribution(record_property: Any) -> None:
    embedder = FastEmbedEmbedder(mm.DEFAULT_DIR)
    corpus = {
        "gr": "[las_curve] wellbore_label=15/9-F-12\nunits: GR [gAPI]\n#1 mnemonic=GR | description=Gamma ray, natural radioactivity of the formation | unit=gAPI",
        "prod": "[production_day] wellbore_label=15/9-F-14\n#7 date=2016-03-02 | bore_oil_vol=812.4 Sm3 | bore_wat_vol=95.2 Sm3",
        "casing": "[casing_point] wellbore_label=15/9-F-14\n#2 size=9.625 in | shoe_md=3210 m | grade=L-80",
        "perf": "[perforation_interval] wellbore_label=15/9-F-12\n#3 top_md=3047 | base_md=3062 | note=Hugin reperforation",
    }
    keys = list(corpus)
    docs = embedder.embed_documents([corpus[k] for k in keys])
    cases = {
        "which instrument measures natural radioactivity": "gr",
        "how much oil was produced in March 2016": "prod",
        "what is the steel grade of the large casing string": "casing",
        "where was the well perforated again": "perf",
    }
    right = 0
    related: list[float] = []
    unrelated: list[float] = []
    for question, answer in cases.items():
        q = embedder.embed_query(question)
        sims = {k: _cosine(q, d) for k, d in zip(keys, docs, strict=True)}
        right += max(sims, key=lambda k: sims[k]) == answer
        related.append(sims[answer])
        unrelated += [v for k, v in sims.items() if k != answer]
    off_topic = [
        _cosine(embedder.embed_query(q), d)
        for q in ("quarterly marketing budget forecast", "zzzz qqqq wwww")
        for d in docs
    ]
    summary = {
        "top1_correct": f"{right}/{len(cases)}",
        "related_min": round(min(related), 3),
        "unrelated_max": round(max(unrelated), 3),
        "unrelated_median": round(statistics.median(unrelated), 3),
        "off_topic_max": round(max(off_topic), 3),
    }
    for key, value in summary.items():
        record_property(key, value)
    print("real similarity:", summary)
    assert right == len(cases), summary


def test_hybrid_search_with_the_real_embedder_end_to_end(migrated_url: URL, tmp_path: Path) -> None:
    world = make_world(migrated_url, tmp_path, embedding_provider="fastembed")
    pid = world.project()
    world.add_doc(
        pid,
        "log.las",
        [
            rec(
                "las_curve",
                {"wellbore_label": "15/9-F-12"},
                [
                    attr("mnemonic", "GR"),
                    attr("description", "Gamma ray, natural radioactivity of the formation"),
                    attr("unit", "gAPI"),
                ],
            )
        ],
    )
    world.add_doc(
        pid,
        "prod.xlsx",
        [
            rec(
                "production_day",
                {"wellbore_label": "15/9-F-14"},
                [attr("bore_oil_vol", "812.4", "Sm3", number=812.4)],
            )
        ],
    )
    world.index()
    out = world.search(pid, "which instrument measures natural radioactivity")
    assert out["mode"] == "hybrid", out["degraded_reasons"]
    assert out["hits"][0]["kind"] == "las_curve"
    assert out["hits"][0]["signals"]["vector_rank"] == 1


def test_real_model_similarity_distributions_off_topic_vs_in_domain(
    migrated_url: URL, tmp_path: Path
) -> None:
    """Prints (does not assert) the similarity distributions the uncalibrated floor/margin are
    judged against: real int8 bge-small, synthetic gold corpus."""
    from tests.retrieval.test_retrieval_gold import build

    world = make_world(
        migrated_url, tmp_path, embedding_provider="fastembed", retrieval_vector_support_floor=0.68
    )
    pid = world.project()
    build(world, pid)
    world.index()
    off_topic = [
        "who won the football match",
        "seismic velocity model",
        "cement bond log",
        "wellhead",
        "quarterly marketing budget forecast",
        "how do I bake sourdough bread",
    ]
    in_domain = [
        "natural radioactivity measurement tool",
        "how much oil came out in March",
        "steel grade of the large pipe",
        "where was the formation top picked",
        "what device isolates the production zone",
        "drilling assembly with a steerable bit",
        "stuck pipe incident while tripping",
        "when was the well shot again",
    ]
    rows = {}
    for label, queries in (("off-topic", off_topic), ("in-domain", in_domain)):
        for q in queries:
            out = world.search(pid, q)
            sims = sorted(
                h["signals"]["vector_similarity"]
                for h in out["hits"]
                if h["signals"]["vector_similarity"] is not None
            )
            top = sims[-1] if sims else None
            median = sims[len(sims) // 2] if sims else None
            rows[q] = (
                label,
                out["status"],
                out["evidence_strength"],
                top,
                median,
                len(out["hits"]),
            )
            print(
                f"{label:9s} {out['status']:13s} {out['evidence_strength']:6s} "
                f"top={top if top is None else round(top, 3)} "
                f"median={median if median is None else round(median, 3)} hits={len(out['hits'])} "
                f"| {q}"
            )
    assert all(r[1] in ("ok", "weak_evidence", "no_results") for r in rows.values())
