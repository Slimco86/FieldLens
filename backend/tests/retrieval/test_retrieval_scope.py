"""RG-1 / RG-8 scope: exact identifiers, eligibility before ranking, no cross-project or
inactive/superseded evidence, source-observation labeling. Synthetic fixtures, PostgreSQL."""

from __future__ import annotations

from uuid import UUID

from tests.retrieval.support import World, attr, rec


def assert_no_evidence(out: dict[str, object]) -> None:
    """Topical overlap with other wells is flagged noise, never evidence for the missing one."""
    assert out["status"] in ("weak_evidence", "no_results"), out["status"]
    hits = out["hits"]
    assert isinstance(hits, list)
    assert all(
        not any(h["support"][k] for k in ("exact", "lexical", "vector"))
        or out["status"] == "weak_evidence"
        for h in hits
    )


def survey(well: str, label: str, n: int = 3, md0: int = 1000) -> list[dict[str, object]]:
    return [
        rec(
            "trajectory_station",
            {"well_name": well, "wellbore_label": label, "well_key": well.split(" ")[-1]},
            [
                attr("md", str(md0 + i * 30) + ".5", "m", number=md0 + i * 30 + 0.5),
                attr("incl", f"{40 + i}.2", "deg", number=40 + i + 0.2),
            ],
            locator={"kind": "xlsx", "sheet": "Survey", "cell_range": f"A{i + 2}:C{i + 2}"},
        )
        for i in range(n)
    ]


def test_exact_id_returns_only_the_mapped_entity(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "f12.xlsx", survey("15/9-F-12", "15/9-F-12"))
    world.add_doc(pid, "f14.xlsx", survey("15/9-F-14", "15/9-F-14"))
    world.index()
    out = world.search(pid, "F-12 trajectory station md")
    assert out["status"] == "ok"
    assert out["exact_matches"][0]["canonical"] == "15/9-f-12"
    assert out["hits"], out
    for hit in out["hits"]:
        assert "15/9-F-12" in hit["text"] and "15/9-F-14" not in hit["text"]
        assert hit["label"] == "source_observation"
        assert hit["resolved_entity_id"] is None and hit["claim_ids"] == []
        assert hit["extraction_quality"]["validation_states"] == {"unreviewed": 3}
        assert hit["evidence"][0]["locator"]["kind"] == "xlsx"
        assert hit["signals"]["exact"] is True


def test_identifier_in_two_blocks_is_explicit_ambiguity(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "a.xlsx", survey("15/9-F-12", "15/9-F-12"))
    world.add_doc(pid, "b.xlsx", survey("25/1-F-12", "25/1-F-12"))
    world.index()
    out = world.search(pid, "F-12 trajectory station")
    assert out["status"] == "ambiguous" and out["hits"] == []
    cands = {c["canonical"] for c in out["ambiguities"][0]["candidates"]}
    assert cands == {"15/9-f-12", "25/1-f-12"}
    # the fully written identifier resolves to exactly one entity
    unique = world.search(pid, "25/1-F-12 trajectory station")
    assert unique["status"] == "ok"
    assert {h["text"].count("25/1-F-12") > 0 for h in unique["hits"]} == {True}
    assert all("15/9-F-12" not in h["text"] for h in unique["hits"])


def test_sidetrack_label_does_not_broaden_to_parent_or_siblings(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "main.xlsx", survey("15/9-F-12", "15/9-F-12"))
    # the sidetrack records name only their own bore (no parent well field)
    world.add_doc(pid, "side.xlsx", survey("15/9-F-12 A", "15/9-F-12 A", md0=2000))
    world.index()
    side = world.search(pid, "F-12 A trajectory station")
    assert [m["canonical"] for m in side["exact_matches"]] == ["15/9-f-12 a"]
    assert side["hits"] and all("15/9-F-12 A" in h["text"] for h in side["hits"])
    parent = world.search(pid, "F-12 trajectory station")
    assert all("wellbore_label=15/9-F-12 A" not in h["text"] for h in parent["hits"])
    assert parent["hits"]


def test_unknown_identifier_is_reported_not_guessed(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "f12.xlsx", survey("15/9-F-12", "15/9-F-12"))
    world.index()
    out = world.search(pid, "F-99 casing depth")
    assert out["unmatched_identifiers"] == ["f-99"]
    assert out["exact_matches"] == []
    assert all("F-99" not in h["text"] for h in out["hits"])


def test_document_id_is_an_exact_identifier(world: World) -> None:
    pid = world.project()
    a = world.add_doc(pid, "a.xlsx", survey("15/9-F-12", "15/9-F-12"))
    world.add_doc(pid, "b.xlsx", survey("15/9-F-14", "15/9-F-14"))
    world.index()
    out = world.search(pid, f"what is in {a.document_id}")
    assert out["exact_matches"][0]["kinds"] == ["document_id"]
    assert {h["document_id"] for h in out["hits"]} == {str(a.document_id)}
    stranger = world.search(pid, "00000000-0000-4000-8000-000000000000 trajectory station")
    assert "00000000-0000-4000-8000-000000000000" in stranger["unmatched_identifiers"]


def test_cross_project_evidence_is_never_returned(world: World) -> None:
    a, b = world.project("A"), world.project("B")
    world.add_doc(a, "a.xlsx", survey("15/9-F-12", "15/9-F-12"))
    other = world.add_doc(b, "b.xlsx", survey("15/9-F-12", "15/9-F-12", n=40))
    world.index()
    out = world.search(a, "F-12 trajectory station md incl")
    assert out["hits"] and {h["document_id"] for h in out["hits"]}.isdisjoint(
        {str(other.document_id)}
    )
    # B's document id is not a member of A: filtering by it is a 404, not an empty success
    r = world.api.client.get(
        f"/api/v1/projects/{a}/retrieval/search",
        params={"q": "survey", "document_id": str(other.document_id)},
    )
    assert r.status_code == 404
    # and B's own id typed into the query matches nothing in A
    leak = world.search(a, f"{other.document_id}")
    assert leak["hits"] == [] and str(other.document_id) in leak["unmatched_identifiers"]
    r = world.api.client.get(f"/api/v1/projects/{UUID(int=1)}/retrieval/search", params={"q": "x"})
    assert r.status_code == 404


def test_eligibility_is_applied_before_ranking_not_after(world: World) -> None:
    """Thirty strongly matching chunks in another project must not crowd out one eligible hit."""
    a, b = world.project("A"), world.project("B")
    world.add_doc(
        a,
        "weak.xlsx",
        [rec("note", {"well_name": "W"}, [attr("remark", "packer setting depth note")])],
    )
    for i in range(30):
        world.add_doc(
            b,
            f"strong{i}.xlsx",
            [
                rec(
                    "note",
                    {"well_name": "W"},
                    [attr("remark", "packer setting depth " * 5 + f"variant {i}")],
                )
            ],
        )
    world.index(limit=500)
    out = world.search(a, "packer setting depth")
    assert len(out["hits"]) == 1 and "packer setting depth note" in out["hits"][0]["text"]


def test_superseded_replaced_inactive_and_invalidated_sources_are_not_returned(
    world: World,
) -> None:
    pid = world.project()
    old = world.add_doc(pid, "v1.xlsx", survey("15/9-F-12", "15/9-F-12"))
    keep = world.add_doc(pid, "keep.xlsx", survey("15/9-F-14", "15/9-F-14"))
    first_revision = old.revision_id
    new = world.add_doc(
        pid, "v2.xlsx", survey("15/9-F-12", "15/9-F-12", md0=5000), replaces=old.document_id
    )
    world.index()
    latest = world.search(pid, "F-12 trajectory station md")
    assert {h["document_id"] for h in latest["hits"]} == {str(new.document_id)}
    # the older revision still resolves its own membership, never the replacement
    earlier = world.search(pid, "F-12 trajectory station", source_revision_id=str(first_revision))
    assert {h["document_id"] for h in earlier["hits"]} <= {str(old.document_id)}
    assert str(new.document_id) not in {h["document_id"] for h in earlier["hits"]}

    # explicit chunk invalidation (the hook TASK-039 removal will call) hides a document at once
    from fieldlens.persistence.session import session_scope
    from fieldlens.retrieval.indexer import invalidate_document_chunks

    with session_scope(world.factory) as session:
        wrong_revision = invalidate_document_chunks(
            session, UUID(pid), keep.document_id, "x", source_revision_id=UUID(int=7)
        )
        assert wrong_revision == 0
        other_project = invalidate_document_chunks(session, UUID(int=9), keep.document_id, "x")
        assert other_project == 0
    assert world.search(pid, "F-14 trajectory station")["hits"]
    with session_scope(world.factory) as session:
        assert (
            invalidate_document_chunks(session, UUID(pid), keep.document_id, "source_removed") == 1
        )
    assert_no_evidence(world.search(pid, "F-14 trajectory station"))

    # a quarantined original and a superseded extraction run are excluded as well
    world.sql(
        "UPDATE document_processing SET storage_state = 'quarantined' WHERE document_id = :d",
        d=new.document_id,
    )
    assert world.search(pid, "F-12 trajectory station md")["hits"] == []
    world.sql(
        "UPDATE document_processing SET storage_state = 'stored' WHERE document_id = :d",
        d=new.document_id,
    )
    world.sql("UPDATE extraction_run SET superseded = true WHERE run_id = :r", r=new.run_id)
    assert world.search(pid, "F-12 trajectory station md")["hits"] == []


def test_failed_or_unsupported_extraction_is_not_searchable_and_is_explained(
    world: World,
) -> None:
    pid = world.project()
    world.add_doc(pid, "ok.xlsx", survey("15/9-F-12", "15/9-F-12"))
    world.add_doc(pid, "bad.pdf", survey("15/9-F-77", "15/9-F-77"), run_status="failed")
    world.add_doc(pid, "none.bin", [], run_status="unsupported")
    world.index()
    assert_no_evidence(world.search(pid, "F-77 trajectory station"))
    cov = {d["filename"]: d for d in world.coverage(pid)["documents"]}
    assert cov["ok.xlsx"]["text_index"] == "complete"
    assert cov["bad.pdf"]["text_index"] == "not_indexable"
    assert any("failed" in x for x in cov["bad.pdf"]["not_indexed"])
    assert cov["none.bin"]["text_index"] == "not_indexable"
    assert any("no native profile" in x for x in cov["none.bin"]["not_indexed"])


def test_unqualified_and_block_qualified_spellings_of_one_label_are_one_naming(
    world: World,
) -> None:
    """A survey writes the bore as ``F-12`` with well key 15/9-F-12; other sources write
    ``15/9-F-12``. With one block present, ``F-12`` reaches both without becoming ambiguous."""
    pid = world.project()
    world.add_doc(pid, "survey.pdf", survey("Volve F", "F-12"))
    world.add_doc(pid, "witsml.xml", survey("15/9-F-12", "15/9-F-12", md0=4000))
    world.add_doc(pid, "other.xlsx", survey("15/9-F-14", "15/9-F-14", md0=5000))
    world.index()
    out = world.search(pid, "F-12 trajectory station")
    assert out["status"] == "ok" and out["ambiguities"] == []
    assert out["exact_matches"][0]["canonical"] == "15/9-f-12"
    assert {h["document_id"] for h in out["hits"]} == {
        str(world.docs["survey.pdf"].document_id),
        str(world.docs["witsml.xml"].document_id),
    }
    # a second block makes the same short form ambiguous again
    world.add_doc(pid, "block2.xlsx", survey("25/1-F-12", "25/1-F-12", md0=6000))
    world.index()
    again = world.search(pid, "F-12 trajectory station")
    assert again["status"] == "ambiguous"
    assert {c["canonical"] for c in again["ambiguities"][0]["candidates"]} >= {
        "15/9-f-12",
        "25/1-f-12",
    }
