"""TASK-085 (spec §16 F2b): the S5 equipment sweep over the wellbore's own documents.

Fake provider only (no Meta call). The sweep runs the existing candidates harness, so reading is
cached per page unit; these tests pin the S5 behaviour around it."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from fieldlens.assetspec.live_designer import NO_DATA, design_without_model
from fieldlens.assetspec.sweep import EquipmentSweeper, SweepLimits, build_sweeper
from fieldlens.assistant.errors import ProviderRefusal, ProviderUnavailable
from fieldlens.assistant.messages import ProviderRequest, TextPart
from fieldlens.assistant.provider import CancelToken
from fieldlens.assistant.stub import truncated_response
from fieldlens.config import Settings
from fieldlens.reconstruction.design_stage import DesignAssetExecutor
from tests.assetspec.test_live_designer import _current, _designer, _reply
from tests.assetspec.test_structured import A, T, f99, seed_records
from tests.candidates.conftest import World
from tests.candidates.eq_helpers import equip
from tests.candidates.support import FixtureProvider, json_response


def _text(req: ProviderRequest) -> str:
    return " ".join(p.text for m in req.messages for p in m.parts if isinstance(p, TextPart))


def _sweeper(
    world: World, provider: FixtureProvider, limits: SweepLimits | None = None
) -> EquipmentSweeper:
    def harness_for(effort: Any) -> Any:
        return world.harness(provider, **({"effort": effort} if effort else {}))

    return EquipmentSweeper(world.factory, harness_for, limits)


def _link(world: World, wb: UUID, *docs: UUID) -> None:
    for doc in docs:  # a native record linked to the wellbore makes the document wellbore-linked
        seed_records(world, doc, wb, [("bha_run", [T("bha_run.name", "BHA 1")], {})])


def _casing_reply(doc: UUID, od: str) -> FixtureProvider:
    item = equip(
        doc,
        1,
        category="casing",
        label_text="Production packer",
        od={"value_text": od, "unit": "in"},
        top_depth={"value_text": "0", "unit": "m", "reference_text": "MD"},
        bottom_depth={"value_text": "2500", "unit": "m", "reference_text": "MD"},
    )
    return FixtureProvider(lambda req, n: json_response([item]))


def test_sweep_reads_a_document_once_and_reuses_it_on_rerun(world: World) -> None:
    wb = f99(world)
    _link(world, wb, world.pdf_doc)
    fp = FixtureProvider(lambda req, n: json_response([equip(world.pdf_doc, 1)]))
    sweeper = _sweeper(world, fp)
    first = sweeper.sweep(world.project_id, wb)
    assert first.count("read") == 1 and first.count("failed") == 0, first.message()
    calls = len(fp.calls)
    assert calls >= 1
    assert world.scalar(
        "select count(*) from extraction_candidate where wellbore_id = :w "
        "and attributes->>'kind' = 'equipment'",
        w=wb,
    )
    second = sweeper.sweep(world.project_id, wb)
    assert second.count("reused") == 1 and second.count("read") == 0, second.message()
    assert len(fp.calls) == calls  # no repeat paid call for an unchanged document


def test_one_failed_document_does_not_block_the_others(world: World) -> None:
    wb = f99(world)
    _link(world, wb, world.pdf_doc, world.other_doc)

    def responder(req: ProviderRequest, n: int) -> Any:
        if "monobore" in _text(req):
            return ProviderRefusal("refused")  # completion.pdf pages
        return json_response([equip(world.other_doc, 2)])

    fp = FixtureProvider(responder)
    report = _sweeper(world, fp).sweep(world.project_id, wb)
    states = {d.name: d.state for d in report.docs}
    assert states["completion.pdf"] == "failed", report.message()
    assert states["other.pdf"] in {"read", "excluded"}, report.message()
    assert report.count("failed") == 1 and "failed" in report.message()


def test_structured_and_swept_dimensions_that_disagree_are_reported_not_chosen(
    world: World,
) -> None:
    wb = f99(world)
    seed_records(
        world,
        world.imageonly_doc,
        wb,
        [
            (
                "wb_geometry_section",
                [
                    T("wb_geometry_section.type_hole_casing", "casing"),
                    A("wb_geometry_section.od_section", 0.340),
                    A("wb_geometry_section.md_top", 0.0),
                    A("wb_geometry_section.md_bottom", 2500.0),
                ],
                {},
            )
        ],
    )
    _link(world, wb, world.pdf_doc)
    label = {
        "by": "Production packer",
        "kind": "casing",
        "label": "Production packer",
        "representation": "source_dimensioned",
    }
    d, _ = _designer(world, [_reply(label)])
    d.attach_sweeper(_sweeper(world, _casing_reply(world.pdf_doc, "9.625")))
    out = d.design(world.project_id, wb, "run-1")
    assert out.ok and out.record is not None, out.message
    assert out.counts["source_conflicts"] >= 1 and "source conflict" in out.message
    assert "Equipment sweep:" in out.message
    flagged = [
        c
        for c in _current(world, world.project_id, wb).spec.components
        if "Missing: agreed dimensions" in (c.confidence_note or "")
    ]
    assert len(flagged) >= 2  # both sources' parts are generic; none chosen or averaged
    assert all(c.representation == "generic_illustrative" and c.params is None for c in flagged)


def test_estimate_includes_the_sweep_as_information(world: World) -> None:
    wb = f99(world)
    _link(world, wb, world.pdf_doc)
    d, provider = _designer(world, [])
    d.attach_sweeper(_sweeper(world, FixtureProvider(lambda req, n: json_response([]))))
    ex = DesignAssetExecutor(d)
    with world.factory() as s:
        sweep = d.sweep_estimate(s, world.project_id, [wb])
        plan = ex.plan(s, world.project_id)
    assert sweep is not None and sweep.documents >= 1 and sweep.pages >= 1
    assert sweep.usd > Decimal(0) and plan.usd >= sweep.usd
    assert "Equipment sweep" in (plan.note or "") and not provider.calls


def test_cancel_stops_the_sweep(world: World) -> None:
    wb = f99(world)
    _link(world, wb, world.pdf_doc)
    fp = FixtureProvider(lambda req, n: json_response([]))
    token = CancelToken()
    token.cancel()
    report = _sweeper(world, fp).sweep(world.project_id, wb, token)
    assert report.cancelled and not fp.calls and not report.docs
    d, _ = _designer(world, [])
    d.attach_sweeper(_sweeper(world, fp))
    out = d.design(world.project_id, wb, "run-1", token)
    assert out.cancelled and not fp.calls


def test_without_a_model_the_sweep_is_not_available_and_structured_still_builds(
    world: World,
) -> None:
    wb = f99(world)
    seed_records(
        world,
        world.imageonly_doc,
        wb,
        [
            (
                "casing_point",
                [T("casing_point.name", '9 5/8" casing'), A("casing_point.md", 2921.0)],
                {},
            )
        ],
    )
    out = design_without_model(world.factory, world.project_id, wb, "run-1")
    assert out.ok and out.message != NO_DATA
    assert "Not available: no model configured" in out.message
    assert _current(world, world.project_id, wb).spec.components


def test_bounds_limit_documents(world: World) -> None:
    wb = f99(world)
    _link(world, wb, world.pdf_doc, world.other_doc)
    fp = FixtureProvider(lambda req, n: json_response([]))
    report = _sweeper(world, fp, SweepLimits(max_documents=1)).sweep(world.project_id, wb)
    assert len(report.docs) == 1 and report.not_swept >= 1
    assert "not swept" in report.message()


def _truncating(doc: UUID, truncate_first: int | None = None) -> FixtureProvider:
    def responder(req: ProviderRequest, n: int) -> Any:
        if truncate_first is None or n <= truncate_first:
            return truncated_response('{"candidates":[', usage(900, 8192))
        return json_response([equip(doc, 1)])

    return FixtureProvider(responder)


def usage(i: int, o: int) -> Any:
    from tests.candidates.support import usage as u

    return u(i, o)


def test_truncated_page_retries_at_minimal_effort_inside_the_output_cap(world: World) -> None:
    wb = f99(world)
    _link(world, wb, world.pdf_doc)
    fp = _truncating(world.pdf_doc, truncate_first=1)
    report = _sweeper(world, fp).sweep(world.project_id, wb)
    assert all(r.max_output_tokens <= 8192 for r in fp.calls)
    assert any(r.effort == "minimal" for r in fp.calls), report.message()
    assert "unit_error" not in report.message()
    assert report.docs[0].state in {"read", "failed"} and report.calls >= 2


def test_max_calls_counts_failed_and_truncated_attempts(world: World) -> None:
    wb = f99(world)
    _link(world, wb, world.pdf_doc, world.other_doc)
    fp = _truncating(world.pdf_doc)  # every call truncates
    report = _sweeper(world, fp, SweepLimits(max_calls=2)).sweep(world.project_id, wb)
    assert len(fp.calls) <= 2, report.message()
    assert report.calls == len(fp.calls) and report.input_tokens > 0 and report.output_tokens > 0
    assert report.usd > Decimal(0)  # failed attempts are billed and reported


def test_transient_failure_is_read_again_but_a_refusal_stays_cached(world: World) -> None:
    wb = f99(world)
    _link(world, wb, world.pdf_doc)
    down = FixtureProvider(lambda req, n: ProviderUnavailable("no balance"))
    first = _sweeper(world, down).sweep(world.project_id, wb)
    assert first.count("failed") == 1, first.message()
    ok = FixtureProvider(lambda req, n: json_response([equip(world.pdf_doc, 1)]))
    with world.factory() as s:
        est = _sweeper(world, ok).estimate(s, world.project_id, [wb])
    assert est.pages >= 1 and est.reused_pages == 0  # a failed unit is not "reused"
    second = _sweeper(world, ok).sweep(world.project_id, wb)
    assert ok.calls and second.count("read") == 1, second.message()
    # a deterministic failure (refusal) stays cached: nothing is called again
    wb2 = UUID(str(world.scalar("select wellbore_id from wellbore where name = '15/9-F-98'")))
    _link(world, wb2, world.other_doc)
    refuse = FixtureProvider(lambda req, n: ProviderRefusal("no"))
    _sweeper(world, refuse).sweep(world.project_id, wb2)
    again = FixtureProvider(lambda req, n: json_response([]))
    _sweeper(world, again).sweep(world.project_id, wb2)
    assert not again.calls


def test_a_page_about_another_well_is_not_attached_to_the_only_linked_wellbore(
    world: World,
) -> None:
    wb = f99(world)
    _link(world, wb, world.other_doc)
    fp = FixtureProvider(lambda req, n: json_response([equip(world.other_doc, 2)]))
    _sweeper(world, fp).sweep(world.project_id, wb)
    assert (
        world.scalar(
            "select count(*) from extraction_candidate where document_id = :d "
            "and wellbore_id = :w and attributes->>'kind' = 'equipment'",
            d=world.other_doc,
            w=wb,
        )
        == 0
    )


def test_survey_documents_are_skipped_and_not_estimated(world: World) -> None:
    wb = f99(world)
    seed_records(
        world,
        world.pdf_doc,
        wb,
        [("bha_run", [T("bha_run.name", "x")], {})],
        profile="pdf_compass_survey_report",
    )
    fp = FixtureProvider(lambda req, n: json_response([]))
    sweeper = _sweeper(world, fp)
    report = sweeper.sweep(world.project_id, wb)
    assert (
        report.docs[0].state == "skipped" and "not an equipment document" in report.docs[0].reason
    )
    assert not fp.calls
    with world.factory() as s:
        est = sweeper.estimate(s, world.project_id, [wb])
    assert est.pages == 0 and est.usd == Decimal(0) and est.skipped == 1


def test_build_sweeper_passes_the_provider_settings_and_no_usd_gate(world: World) -> None:
    ledger = world.ledger
    meta = SimpleNamespace(
        renderer=None,
        rates=__import__("tests.assistant_support", fromlist=["PRICING"]).PRICING,
        pricing_id=world.pricing_id,
        period_id=world.period,
        ledger=ledger,
        provider=FixtureProvider(lambda req, n: json_response([])),
    )
    settings = Settings(provider_deadline_s=33, provider_max_attempts=2)
    sweeper = build_sweeper(
        SimpleNamespace(meta=meta), world.factory, world.reader._store, settings
    )  # type: ignore[attr-defined]
    assert sweeper is not None
    cfg = sweeper._harness_for(None).config  # type: ignore[attr-defined]
    assert cfg.limits.deadline_s == 33 and cfg.limits.max_attempts == 2
    assert cfg.effort == "low"
    assert sweeper._harness_for("minimal").config.effort == "minimal"  # type: ignore[attr-defined]
