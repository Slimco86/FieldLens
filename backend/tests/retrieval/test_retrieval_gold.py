"""RG-2 offline gold set (SYNTHETIC; invented values; fake hash embedder).

This proves the pipeline mechanics - exact IDs, lexical, vector fusion, bounds, determinism and
unanswerable controls - against fixtures built here. It does NOT measure recall on real Volve
sources or with the real embedding model; that evidence is the opt-in local-data/embedder runs
and the G1 gold cases, and RG-2 stays unverified for real data until those are recorded."""

from __future__ import annotations

from uuid import UUID

import pytest

from fieldlens.retrieval.search import RRF_K, rrf
from tests.retrieval.support import World, attr, rec

WELLS = {"F-12": "15/9-F-12", "F-14": "15/9-F-14", "F-5": "15/9-F-5"}


def _traj(well: str, base: int) -> list[dict[str, object]]:
    return [
        rec(
            "trajectory_station",
            {"well_name": well, "wellbore_label": well},
            [
                attr("md", f"{base + i * 25}.0", "m", number=float(base + i * 25)),
                attr("tvd", f"{base - 40 + i * 24}.5", "m", number=float(base - 40 + i * 24)),
                attr("azimuth", f"{120 + i}.0", "deg", number=float(120 + i)),
            ],
            locator={"kind": "xlsx", "sheet": "Survey", "cell_range": f"A{i + 2}:D{i + 2}"},
        )
        for i in range(12)
    ]


def _single(
    kind: str, well: str, items: list[tuple[str, str, str | None]]
) -> list[dict[str, object]]:
    return [
        rec(
            kind,
            {"well_name": well, "wellbore_label": well},
            [
                attr(k, v, u, number=float(v) if v.replace(".", "").isdigit() else None)
                for k, v, u in items
            ],
        )
    ]


def build(world: World, pid: str) -> dict[str, UUID]:
    d = world.add_doc
    docs = {
        "traj12": d(pid, "traj12.xlsx", _traj(WELLS["F-12"], 2000)),
        "traj14": d(pid, "traj14.xlsx", _traj(WELLS["F-14"], 3000)),
        "perf12": d(
            pid,
            "perf.dat",
            _single(
                "perforation_interval",
                WELLS["F-12"],
                [
                    ("top_md", "3047", None),
                    ("base_md", "3062", None),
                    ("note", "Hugin reperforation campaign", None),
                ],
            ),
        ),
        "prod14": d(
            pid,
            "prod.xlsx",
            _single(
                "production_day",
                WELLS["F-14"],
                [
                    ("oil_volume", "812.4", "Sm3"),
                    ("water_volume", "95.2", "Sm3"),
                    ("date", "2016-03-02", None),
                ],
            ),
        ),
        "las12": d(
            pid,
            "log.las",
            _single(
                "las_curve",
                WELLS["F-12"],
                [
                    ("mnemonic", "GRAX", None),
                    ("description", "Gamma ray axial measurement", None),
                    ("unit", "gAPI", None),
                ],
            ),
        ),
        "cas14": d(
            pid,
            "casing.pdf",
            _single(
                "casing_point",
                WELLS["F-14"],
                [
                    ("size", "9.625", "in"),
                    ("shoe_md", "3210", "m"),
                    ("grade", "L-80 premium thread", None),
                ],
            ),
        ),
        "pick": d(
            pid,
            "picks.dat",
            _single(
                "formation_pick",
                WELLS["F-5"],
                [("surface", "Skagerrak Formation top", None), ("md", "3388.2", "m")],
            ),
        ),
        "pkr": d(
            pid,
            "equipment.pdf",
            [
                rec(
                    "tubular_component",
                    {"wellbore_label": WELLS["F-5"]},
                    [
                        attr("model_number", "XJ-450", None),
                        attr("description", "Retrievable production packer, 7 in", None),
                        attr("outer_diameter", "6.151", "in", number=6.151),
                    ],
                )
            ],
        ),
        "bha": d(
            pid,
            "bha.xml",
            _single(
                "bha_run",
                WELLS["F-14"],
                [
                    ("description", "Rotary steerable assembly with 8.5 in PDC bit", None),
                    ("run", "2", None),
                ],
            ),
        ),
        "geo": d(
            pid,
            "report.pdf",
            [
                rec(
                    "report_note",
                    {"wellbore_label": WELLS["F-12"]},
                    [attr("remark", "Stuck pipe event while tripping, jars fired at 2871 m")],
                )
            ],
        ),
    }
    return {k: v.document_id for k, v in docs.items()}


# (query, document key that must hold a top-5 hit). 24 answerable cases: 4 exact-ID.
EXACT = [
    ("15/9-F-14 production oil", "prod14"),
    ("F-5 packer", "pkr"),
    ("XJ-450", "pkr"),
    ("F-12 gamma ray curve", "las12"),
]
ANSWERABLE = [
    ("Which interval was reperforated in the Hugin?", "perf12"),
    ("What is the top and base measured depth of the perforation?", "perf12"),
    ("What oil volume was produced on 2016-03-02?", "prod14"),
    ("water volume Sm3", "prod14"),
    ("What does the GRAX curve measure?", "las12"),
    ("gamma ray gAPI curve unit", "las12"),
    ("What is the casing shoe depth?", "cas14"),
    ("9.625 in casing grade L-80", "cas14"),
    ("Where is the Skagerrak top picked?", "pick"),
    ("formation top measured depth 3388.2", "pick"),
    ("What is the outer diameter of the retrievable packer?", "pkr"),
    ("production packer 7 in", "pkr"),
    ("rotary steerable PDC bit", "bha"),
    ("Which BHA run used an 8.5 in bit?", "bha"),
    ("stuck pipe jars fired", "geo"),
    ("tripping event at 2871 m", "geo"),
    ("azimuth of the survey stations for 15/9-F-12", "traj12"),
    ("trajectory md tvd azimuth 15/9-F-14", "traj14"),
    ("survey station measured depth 2025.0", "traj12"),
    ("survey station measured depth 3050.0", "traj14"),
]


@pytest.fixture
def gold(world: World) -> tuple[World, str, dict[str, UUID]]:
    pid = world.project()
    docs = build(world, pid)
    world.index()
    return world, pid, docs


def _top5_docs(out: dict[str, object]) -> list[str]:
    hits = out["hits"]
    assert isinstance(hits, list)
    return [h["document_id"] for h in hits[:5]]


def test_gold_top5_recall_and_exact_ids(gold: tuple[World, str, dict[str, UUID]]) -> None:
    world, pid, docs = gold
    exact_ok = 0
    for query, key in EXACT:
        out = world.search(pid, query)
        if str(docs[key]) in _top5_docs(out):
            exact_ok += 1
    assert exact_ok == 4, "all four exact-ID cases must find the correct record"
    answered = 0
    misses = []
    for query, key in [*EXACT, *ANSWERABLE]:
        out = world.search(pid, query)
        if str(docs[key]) in _top5_docs(out):
            answered += 1
        else:
            misses.append(query)
    assert len(EXACT) + len(ANSWERABLE) == 24
    print(f"synthetic gold top-5 recall: {answered}/24 misses={misses}")
    assert answered >= 22, misses


def test_unanswerable_controls_do_not_invent_evidence(
    gold: tuple[World, str, dict[str, UUID]],
) -> None:
    world, pid, _ = gold
    unknown_well = world.search(pid, "F-99 casing shoe depth")
    assert unknown_well["unmatched_identifiers"] == ["f-99"]
    assert all("F-99" not in h["text"] for h in unknown_well["hits"])
    unknown_model = world.search(pid, "ZX-9000-Q packer")
    assert unknown_model["unmatched_identifiers"] == ["zx-9000-q"]
    nonsense = world.search(pid, "quarterly revenue forecast marketing budget")
    assert nonsense["status"] == "no_results" and nonsense["hits"] == []
    gibberish = world.search(pid, "qzxv wplk mnbt")
    assert gibberish["hits"] == []


def test_results_are_bounded_to_ten_chunks_and_twelve_thousand_tokens(world: World) -> None:
    pid = world.project()
    # 60 documents, each a separate chunk matching the query
    for i in range(60):
        world.add_doc(
            pid,
            f"n{i}.pdf",
            [
                rec(
                    "report_note",
                    {"wellbore_label": f"W{i}"},
                    [attr("remark", "pressure test " * 8)],
                )
            ],
        )
    world.index(limit=500)
    out = world.search(pid, "pressure test", limit=10)
    assert len(out["hits"]) == 10 and out["returned_tokens"] <= 12_000
    assert out["max_chunks"] == 10 and out["max_tokens"] == 12_000
    assert sum(h["token_count"] for h in out["hits"]) == out["returned_tokens"]
    over = world.api.client.get(
        f"/api/v1/projects/{pid}/retrieval/search", params={"q": "pressure", "limit": 11}
    )
    assert over.status_code == 422


def test_rrf_fusion_is_deterministic_and_matches_the_recipe() -> None:
    a, b, c, d = (UUID(int=i) for i in (1, 2, 3, 4))
    lists = {"lexical": [a, b, c], "vector": [b, a, d]}
    fused = rrf(lists)
    assert fused == rrf({"vector": [b, a, d], "lexical": [a, b, c]})
    scores = dict(fused)
    assert scores[a] == pytest.approx(1 / (RRF_K + 1) + 1 / (RRF_K + 2))
    assert scores[b] == pytest.approx(1 / (RRF_K + 2) + 1 / (RRF_K + 1))
    assert scores[c] == pytest.approx(1 / (RRF_K + 3)) and scores[d] == pytest.approx(
        1 / (RRF_K + 3)
    )
    assert RRF_K == 60
    # equal scores break ties by chunk id, never by insertion order
    assert [x for x, _ in fused] == [a, b, c, d]


def test_repeated_search_is_identical_and_cache_key_tracks_index_and_query(
    gold: tuple[World, str, dict[str, UUID]],
) -> None:
    world, pid, docs = gold
    one = world.search(pid, "casing shoe depth")
    two = world.search(pid, "casing shoe depth")
    assert one == two
    other = world.search(pid, "casing shoe depth now")
    assert other["cache_key"] != one["cache_key"]
    scoped = world.search(pid, "casing shoe depth", document_id=str(docs["cas14"]))
    assert scoped["cache_key"] != one["cache_key"]
    before = one["cache_key"]
    world.add_doc(
        pid, "late.pdf", [rec("report_note", {"wellbore_label": "W"}, [attr("remark", "late")])]
    )
    world.index()
    assert world.search(pid, "casing shoe depth")["cache_key"] != before
