"""Formation layer read model: pure unit tests with synthetic picks and engine trajectories
(no database). Covers FO-1 placement, FO-2 unsupported picks, FO-3 tiers (T1/T2), FO-5 datum block
and FO-6 isolation of failures."""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID, uuid4

import pytest

from fieldlens.context.formations import Bore, PickRow, build_layer_set
from fieldlens.contracts.context_layers import (
    LEVEL_PLANE_LABEL,
    DatumStatus,
    DepthReference,
    FormationBlockReason,
    FormationTier,
    InterpretationStatus,
)
from fieldlens.engineering.trajectory import (
    NorthReference,
    Survey,
    SurveyReference,
    SurveyStation,
    compute_trajectory,
)

PROJECT = uuid4()
REVISION = uuid4()


def _traj(stations: list[tuple[float, float, float]], z0: float = 0.0):  # type: ignore[no-untyped-def]
    ref = SurveyReference(
        crs="local",
        vertical_datum="local",
        depth_reference="local",
        north_reference=NorthReference.GRID,
    )
    return compute_trajectory(
        Survey(
            stations=tuple(SurveyStation(*s) for s in stations),
            reference=ref,
            md_unit="m",
            start_east_m=0.0,
            start_north_m=0.0,
            start_z_m=z0,
        )
    )


def vertical() -> Bore:
    return Bore(uuid4(), _traj([(0, 0, 0), (2000, 0, 0)]), "RKB")


def deviated(ref: str | None = "RKB") -> Bore:
    # constant 30 deg inclination towards east: E = md sin30, TVD = md cos30
    return Bore(uuid4(), _traj([(0, 30, 90), (2000, 30, 90)]), ref)


def _a(key: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"key": f"pick.{key}", "validation_state": "unreviewed"}
    base.update(kw)
    return base


def depth(key: str, v: float, unit: str | None = "m", **kw: Any) -> dict[str, Any]:
    return _a(key, number=v, unit=unit, original_text=str(v), **kw)


def pick(
    wb: UUID | None,
    name: str,
    md: float | None = None,
    *,
    tvd: float | None = None,
    tvdss: float | None = None,
    twt: float | None = None,
    qlf: str | None = None,
    state: str = "unreviewed",
    unit: str | None = "m",
    revision: UUID | None = REVISION,
    md_attr: dict[str, Any] | None = None,
) -> PickRow:
    attrs = [_a("surface_name", text=name)]
    if qlf:
        attrs.append(_a("qualifier", text=qlf))
    if md_attr is not None:
        attrs.append(md_attr)
    elif md is not None:
        attrs.append(depth("md", md, unit))
    if tvd is not None:
        attrs.append(depth("tvd", tvd, unit))
    if tvdss is not None:
        attrs.append(depth("tvdss", tvdss, unit))
    if twt is not None:
        attrs.append(_a("twt", number=twt, unit="ms", original_text=str(twt)))
    return PickRow(
        record_id=uuid4(),
        run_id=uuid4(),
        document_id=uuid4(),
        ordinal=0,
        state=state,
        locator={"kind": "text", "line_start": 7, "line_end": 7},
        attrs=attrs,
        wellbore_id=wb,
        revision_id=revision,
        method="dat_formation_picks 1",
    )


def test_formation_placement_md_on_deviated_bore() -> None:
    bore = deviated()
    md = 1500.0
    row = pick(bore.wellbore_id, "Hugin Fm.", md, tvd=md * math.cos(math.radians(30)))
    out = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    (surface,) = out.surfaces
    p = surface.picks[0]
    assert p.position_enu is not None
    assert p.position_enu[0] == pytest.approx(md * 0.5, abs=1e-9)
    assert p.position_enu[1] == pytest.approx(0.0, abs=1e-9)
    assert p.position_enu[2] == pytest.approx(-md * math.cos(math.radians(30)), abs=1e-9)
    # MD is not TVD: the pick keeps MD separately and its scene elevation is the engine's
    assert p.md is not None and p.md.value == 1500.0
    assert p.md.datum is None and p.md.datum_status is DatumStatus.NOT_APPLICABLE
    assert p.scene_elevation is not None
    assert p.scene_elevation.value == pytest.approx(p.position_enu[2])
    assert out.conflicts == [] and out.unsupported == []


def test_placement_never_equates_md_and_tvd() -> None:
    bore = deviated()
    out = build_layer_set(PROJECT, bore.wellbore_id, [pick(bore.wellbore_id, "X", 1000.0)], [bore])
    p = out.surfaces[0].picks[0]
    assert p.position_enu is not None
    assert abs(p.position_enu[2] + 1000.0) > 100.0  # elevation -866 m, not -1000 m


def test_formation_placement_ft_converted_and_original_kept() -> None:
    bore = vertical()
    out = build_layer_set(
        PROJECT, bore.wellbore_id, [pick(bore.wellbore_id, "A", 3000.0, unit="ft")], [bore]
    )
    p = out.surfaces[0].picks[0]
    assert p.md is not None and p.md.value == 3000.0 and p.md.unit == "ft"
    assert p.position_enu is not None
    assert p.position_enu[2] == pytest.approx(-914.4, abs=1e-9)


def test_tvd_conflict_reported_pick_kept_plane_blocked() -> None:
    bore = vertical()
    row = pick(bore.wellbore_id, "Hugin Fm.", 1000.0, tvd=1025.0)  # KB-like 25 m offset
    out = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    (c,) = out.conflicts
    assert c.reason is FormationBlockReason.TVD_CONFLICT
    assert c.difference == pytest.approx(25.0)
    assert c.difference_unit == "m" and c.tolerance == pytest.approx(2.0)
    assert c.source_depth is not None and c.source_depth.value == 1025.0
    assert c.trajectory_depth is not None and c.trajectory_depth.value == pytest.approx(1000.0)
    assert c.trajectory_depth.datum == "RKB"
    (s,) = out.surfaces
    assert s.plane is None and s.tier is FormationTier.T1
    assert [b.reason for b in s.blocked] == [FormationBlockReason.TVD_CONFLICT]
    assert s.picks[0].position_enu is not None  # placed by MD, neither depth chosen


def test_tvd_within_tolerance_no_conflict() -> None:
    bore = vertical()
    row = pick(bore.wellbore_id, "A", 1000.0, tvd=1001.5)
    out = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    assert out.conflicts == []
    assert out.surfaces[0].tier is FormationTier.T2


def test_tvdss_tvd_datum_offsets_must_agree() -> None:
    bore = vertical()
    wb = bore.wellbore_id
    rows = [
        pick(wb, "A", 500.0, tvd=500.0, tvdss=475.0),
        pick(wb, "B", 800.0, tvd=800.0, tvdss=775.0),
        pick(wb, "C", 1200.0, tvd=1200.0, tvdss=1100.0),  # implies 100 m datum, others 25 m
    ]
    out = build_layer_set(PROJECT, wb, rows, [bore])
    assert [c.pick_id for c in out.conflicts] == [rows[2].record_id]
    by_name = {s.name: s for s in out.surfaces}
    assert by_name["A"].tier is FormationTier.T2 and by_name["C"].tier is FormationTier.T1


def test_tvdss_only_is_not_compared_without_datum() -> None:
    bore = vertical()
    row = pick(bore.wellbore_id, "A", 1000.0, tvdss=975.0)
    out = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    assert out.conflicts == []
    p = out.surfaces[0].picks[0]
    assert p.tvdss is not None
    assert p.tvdss.datum is None and p.tvdss.datum_status is DatumStatus.UNKNOWN
    assert p.tvdss.reference is DepthReference.TVDSS


@pytest.mark.parametrize("qlf", ["ER", "FP", "FO", "NL", "NR"])
def test_formation_unsupported_qualifiers_listed_not_drawn(qlf: str) -> None:
    bore = vertical()
    row = pick(bore.wellbore_id, "Skagerrak", 900.0, qlf=qlf)
    out = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    assert out.surfaces == []
    (u,) = out.unsupported
    assert u.reason is FormationBlockReason.UNSUPPORTED_QUALIFIER
    assert u.qualifier == qlf and u.pick_id == row.record_id
    assert qlf in u.message
    assert out.empty_reason is not None


def test_formation_unsupported_twt_only_never_becomes_depth() -> None:
    bore = vertical()
    row = pick(bore.wellbore_id, "A", None, twt=2450.0)
    out = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    assert out.surfaces == []
    assert out.unsupported[0].reason is FormationBlockReason.TWT_ONLY


def test_formation_unsupported_no_depth_bad_state_unknown_unit_outside_range() -> None:
    bore = vertical()
    wb = bore.wellbore_id
    rows = [
        pick(wb, "NoDepth", None),
        pick(wb, "Bad", 500.0, state="invalid"),
        pick(wb, "Unit", 500.0, unit="fathom"),
        pick(wb, "Deep", 2500.0),
        pick(wb, "Ok", 500.0),
    ]
    out = build_layer_set(PROJECT, wb, rows, [bore])
    reasons = {u.surface_name: u.reason for u in out.unsupported}
    assert reasons == {
        "NoDepth": FormationBlockReason.NO_USABLE_DEPTH,
        "Bad": FormationBlockReason.UNVALIDATED_PICK,
        "Unit": FormationBlockReason.UNKNOWN_UNIT,
        "Deep": FormationBlockReason.OUTSIDE_SUPPORT,
    }
    assert [s.name for s in out.surfaces] == ["Ok"]


def test_assumed_default_unit_is_disclosed() -> None:
    bore = vertical()
    md_attr = _a(
        "md",
        number=700.0,
        unit=None,
        normalized_number=700.0,
        normalized_unit="m",
        original_text="700.0",
    )
    out = build_layer_set(
        PROJECT, bore.wellbore_id, [pick(bore.wellbore_id, "A", md_attr=md_attr)], [bore]
    )
    md = out.surfaces[0].picks[0].md
    assert md is not None and md.unit == "m"
    assert md.original_text is not None and "assumed" in md.original_text


def test_formation_tiers_t2_plane_labeled_illustrative_and_bounded() -> None:
    bore = deviated()
    row = pick(bore.wellbore_id, "Hugin Fm.", 1500.0)
    out = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    (s,) = out.surfaces
    assert s.tier is FormationTier.T2 and s.status is InterpretationStatus.ILLUSTRATIVE
    assert LEVEL_PLANE_LABEL in s.tier_label and "illustrative" in s.tier_label
    assert s.plane is not None and "illustrative" in s.plane.label
    assert s.plane.note == "not an interpreted horizon"
    assert s.plane.elevation.reference is DepthReference.SCENE_ELEVATION
    assert s.plane.elevation.datum_status is DatumStatus.NOT_APPLICABLE
    assert s.plane.elevation.value == pytest.approx(-1500.0 * math.cos(math.radians(30)))
    assert s.plane.source_pick_id == row.record_id
    f = s.plane.footprint
    # bore reaches E = 1000 m at TD: footprint covers wellhead and TD plus margin
    assert f.min_east < 0.0 < 1000.0 < f.max_east
    assert f.margin_m >= 100.0 and f.min_north < 0.0 < f.max_north
    assert out.frame.vertical_reference == "RKB"


def test_t3_not_produced_and_no_mesh() -> None:
    bore = vertical()
    rows = [pick(bore.wellbore_id, "A", md) for md in (300.0, 600.0, 900.0)]
    out = build_layer_set(PROJECT, bore.wellbore_id, rows, [bore])
    assert all(s.mesh is None and s.tier is not FormationTier.T3 for s in out.surfaces)


def test_same_surface_different_elevations_no_crossing_chosen() -> None:
    bore = vertical()
    wb = bore.wellbore_id
    rows = [pick(wb, "Hugin Fm.", 800.0), pick(wb, "hugin  fm.", 1200.0)]
    out = build_layer_set(PROJECT, wb, rows, [bore])
    (s,) = out.surfaces
    assert len(s.picks) == 2 and s.plane is None
    assert s.blocked and "no crossing is chosen" in s.blocked[0].message


def test_same_surface_same_elevation_on_reversing_bore_gives_plane() -> None:
    # goes down to 60 deg, returns up past the horizontal to 120 deg: the same level is crossed twice
    traj = _traj([(0, 0, 0), (1000, 60, 90), (2000, 120, 90)])
    bore = Bore(uuid4(), traj, "RKB")
    up_mid = float(traj.position_at_md(1000.0)[2])
    # find a second MD with the same elevation by bisection on the rising leg
    lo, hi = 1500.0, 2000.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if float(traj.position_at_md(mid)[2]) < up_mid:
            lo = mid
        else:
            hi = mid
    rows = [pick(bore.wellbore_id, "Reversal", 1000.0), pick(bore.wellbore_id, "Reversal", hi)]
    out = build_layer_set(PROJECT, bore.wellbore_id, rows, [bore])
    (s,) = out.surfaces
    assert s.plane is not None and len(s.picks) == 2


def test_evidence_links_record_locator_revision() -> None:
    bore = vertical()
    row = pick(bore.wellbore_id, "A", 500.0)
    out = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    (ev,) = out.surfaces[0].picks[0].evidence
    assert ev.record_id == row.record_id
    assert ev.document_id == row.document_id and ev.source_revision_id == REVISION
    assert ev.locator.root.kind == "text" and ev.locator.root.line_start == 7  # type: ignore[union-attr]
    assert out.surfaces[0].picks[0].extraction_method == "dat_formation_picks 1"
    none = build_layer_set(
        PROJECT, bore.wellbore_id, [pick(bore.wellbore_id, "A", 500.0, revision=None)], [bore]
    )
    assert none.surfaces[0].picks[0].evidence == []


def test_formation_datum_block_differing_references() -> None:
    a, b = deviated("RKB"), deviated("MSL")
    rows = [pick(a.wellbore_id, "Hugin Fm.", 1000.0), pick(b.wellbore_id, "Hugin Fm.", 1000.0)]
    out = build_layer_set(PROJECT, None, rows, [a, b])
    assert [x.reason for x in out.blocked] == [FormationBlockReason.DATUM_MISMATCH]
    assert set(out.blocked[0].pick_ids) == {r.record_id for r in rows}
    assert out.frame.vertical_reference is None
    assert out.frame.vertical_reference_status is DatumStatus.UNKNOWN
    # per-wellbore output is intact; nothing is project scoped
    assert len(out.surfaces) == 2
    assert all(s.scope.value == "wellbore" for s in out.surfaces)


def test_formation_datum_block_unknown_reference() -> None:
    a, b = deviated("RKB"), deviated(None)
    rows = [pick(a.wellbore_id, "Hugin Fm.", 1000.0), pick(b.wellbore_id, "Hugin Fm.", 1000.0)]
    out = build_layer_set(PROJECT, None, rows, [a, b])
    assert [x.reason for x in out.blocked] == [FormationBlockReason.UNKNOWN_DATUM]
    assert out.frame.vertical_reference_status is DatumStatus.UNKNOWN


def test_shared_reference_not_blocked_and_single_bore_needs_no_datum() -> None:
    a, b = deviated("rkb"), deviated(" RKB ")
    rows = [pick(a.wellbore_id, "Hugin Fm.", 1000.0), pick(b.wellbore_id, "Hugin Fm.", 1000.0)]
    shared = build_layer_set(PROJECT, None, rows, [a, b])
    assert shared.blocked == []
    assert shared.frame.vertical_reference_status is DatumStatus.STATED
    unknown = deviated(None)
    solo = build_layer_set(
        PROJECT, unknown.wellbore_id, [pick(unknown.wellbore_id, "A", 700.0)], [unknown]
    )
    assert solo.blocked == [] and solo.surfaces[0].tier is FormationTier.T2


def test_datum_block_only_for_surfaces_in_several_bores() -> None:
    a, b = deviated("RKB"), deviated("MSL")
    rows = [pick(a.wellbore_id, "A", 1000.0), pick(b.wellbore_id, "B", 1000.0)]
    out = build_layer_set(PROJECT, None, rows, [a, b])
    assert out.blocked == []


def test_context_gaps_missing_trajectory_blocks_only_that_bore() -> None:
    good = vertical()
    bad = Bore(uuid4(), None, None, "no valid survey is available for this wellbore")
    rows = [pick(good.wellbore_id, "A", 500.0), pick(bad.wellbore_id, "A", 500.0)]
    orphan = pick(None, "Z", 100.0)
    out = build_layer_set(PROJECT, None, [*rows, orphan], [good, bad])
    assert [s.wellbore_ids[0] for s in out.surfaces] == [good.wellbore_id]
    assert {u.reason for u in out.unsupported} == {FormationBlockReason.NO_TRAJECTORY}
    assert len(out.unsupported) == 2


def test_empty_project_reason() -> None:
    out = build_layer_set(PROJECT, None, [], [])
    assert out.empty_reason == "no formation picks in this project"
    assert out.surfaces == [] and out.generated_from_revision
    solo = build_layer_set(PROJECT, uuid4(), [], [])
    assert solo.empty_reason == "no formation picks for this wellbore"


def test_revision_key_changes_with_inputs_and_is_stable() -> None:
    bore = vertical()
    row = pick(bore.wellbore_id, "A", 500.0)
    one = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    again = build_layer_set(PROJECT, bore.wellbore_id, [row], [bore])
    other = build_layer_set(
        PROJECT, bore.wellbore_id, [row, pick(bore.wellbore_id, "B", 600.0)], [bore]
    )
    assert one.generated_from_revision == again.generated_from_revision
    assert one.generated_from_revision != other.generated_from_revision


def test_contract_validators_hardening_expectations() -> None:
    """Data shape required by the 094b validator tightening."""
    a, b = deviated("RKB"), deviated("RKB")
    rows = [pick(a.wellbore_id, "A", 700.0, tvd=606.2), pick(b.wellbore_id, "A", 700.0)]
    out = build_layer_set(PROJECT, None, rows, [a, b])
    for s in out.surfaces:
        assert (
            s.status
            is {
                FormationTier.T1: InterpretationStatus.OBSERVED,
                FormationTier.T2: InterpretationStatus.ILLUSTRATIVE,
            }[s.tier]
        )
        if s.plane is not None:
            assert "illustrative" in s.plane.label
        for p in s.picks:
            assert p.md is not None and p.md.datum is None
            assert p.tier is FormationTier.T1 and p.status is InterpretationStatus.OBSERVED
