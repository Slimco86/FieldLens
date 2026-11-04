"""Formation layer read model (TASK-097, FL-024; EXPLORE_ENRICHMENT sections 3 FO-*, 4.1).

Stored ``formation_pick`` records are placed on their wellbore at the pick MD by the deterministic
double-precision minimum-curvature engine. Nothing is written and nothing is inferred beyond that:

* T1 pick marker: position from the trajectory at the pick MD. A single bore needs no datum.
* The engine TVD is compared with the pick's TVD; a disagreement beyond tolerance is a reported
  conflict (never silently resolved) and blocks the level plane of that surface. TVD and TVDSS of
  the same pick must imply one consistent datum offset across the bore, else the outliers conflict.
* Qualifiers ER/FP/FO/NL/NR, picks without a usable depth, TWT-only picks, MD outside the surveyed
  range and picks of a bore without a valid trajectory are listed with a reason and never drawn.
* T2 level plane at the scene elevation of the pick (up-positive, from the trajectory), bounded to
  the bore footprint plus a margin, labeled ``level plane - illustrative``. Several picks of one
  surface in one bore that disagree in elevation are never reduced to one (no crossing is chosen).
* Cross-wellbore sets: a surface seen in several bores is blocked (reason on screen) unless every
  bore states the same vertical reference. All positions are wellbore-local ENU offsets from each
  wellhead (the trajectory endpoint frame); no cross-bore geometry is produced here.
* T3 interpolated surfaces are NOT produced: they need picks of one surface in several bores
  expressed in one shared horizontal frame, which this bore-local read model does not define.

The core (:func:`build_layer_set`) is pure and unit-testable; the SQL loader is separate."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from fieldlens.contracts.context_layers import (
    LEVEL_PLANE_LABEL,
    MAX_PICKS_PER_SURFACE,
    MAX_SURFACES,
    TIER_STATUS,
    DatumStatus,
    DepthReference,
    DepthValue,
    FormationBlocked,
    FormationBlockReason,
    FormationConflict,
    FormationFrame,
    FormationLayerSet,
    FormationPick,
    FormationScope,
    FormationSurface,
    FormationTier,
    FormationUnsupportedPick,
    LevelPlane,
    PlaneFootprint,
)
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import EvidenceLink, Locator, ValidationState
from fieldlens.engineering.trajectory import Trajectory
from fieldlens.exposure import rules
from fieldlens.identity import service as identity_service
from fieldlens.wellpath import service as wellpath

ALGORITHM_VERSION = "formations-v1"
UNSUPPORTED_QUALIFIERS = frozenset({"ER", "FP", "FO", "NL", "NR"})
TVD_TOLERANCE_M = 1.0
TVD_TOLERANCE_RELATIVE = 0.002
PLANE_MARGIN_MIN_M = 100.0
PLANE_MARGIN_FRACTION = 0.25
_FT_M = 0.3048
_WS = re.compile(r"\s+")
_ASSUMED = "(unit not stated by source; metres assumed by profile default)"


@dataclass(frozen=True)
class PickRow:
    """One stored ``formation_pick`` record as read from the database."""

    record_id: UUID
    run_id: UUID
    document_id: UUID
    ordinal: int
    state: str
    locator: dict[str, Any]
    attrs: list[dict[str, Any]]
    wellbore_id: UUID | None
    revision_id: UUID | None = None
    method: str | None = None

    def attr(self, key: str) -> dict[str, Any] | None:
        full = f"pick.{key}"
        return next((a for a in self.attrs if a.get("key") == full), None)


@dataclass(frozen=True)
class Bore:
    """A wellbore with its validated trajectory, or the reason it has none."""

    wellbore_id: UUID
    trajectory: Trajectory | None
    vertical_reference: str | None = None
    no_trajectory_reason: str = "no valid survey is available for this wellbore"
    trajectory_run_id: UUID | None = None


@dataclass
class _Depth:
    """A pick depth: original value/unit and metres (``None`` when the unit is unusable)."""

    value: float | None
    unit: str | None
    metres: float | None
    text: str | None
    assumed_unit: bool
    state: str | None


def _qty(a: dict[str, Any] | None) -> _Depth | None:
    if a is None:
        return None
    number = a.get("number")
    norm = a.get("normalized_number")
    if number is None and norm is None:
        return None
    unit = a.get("unit")
    nunit = a.get("normalized_unit")
    original = a.get("original_text") or a.get("text")
    state = a.get("validation_state")
    if unit is None and nunit == "m" and norm is not None:
        # The Volve tables document no depth unit; the profile defaults to metres (owner decision).
        v = float(number if number is not None else norm)
        return _Depth(v, "m", float(norm), original, True, state)
    value = float(number) if number is not None else None
    u = str(unit).strip().lower() if unit else ""
    metres: float | None
    if nunit == "m" and norm is not None:
        metres = float(norm)
    elif value is not None and u in {"m", "meter", "metre", "meters", "metres"}:
        metres = value
    elif value is not None and u in {"ft", "feet", "foot"}:
        metres = value * _FT_M
    else:
        metres = None
    if value is None and metres is not None:
        value = metres
    return _Depth(value, str(unit) if unit else None, metres, original, False, state)


def _text(a: dict[str, Any] | None) -> str | None:
    if a is None:
        return None
    v = a.get("text") or a.get("original_text")
    s = str(v).strip() if v is not None else ""
    return s or None


def surface_key(name: str) -> str:
    return _WS.sub(" ", name.strip()).casefold()


def _norm_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    r = _WS.sub(" ", ref.strip()).casefold()
    return r or None


def _validation(state: str) -> ValidationState:
    try:
        return ValidationState(state)
    except ValueError:
        return ValidationState.UNREVIEWED


def _evidence(row: PickRow) -> list[EvidenceLink]:
    if row.revision_id is None:
        return []
    try:
        loc = Locator.model_validate(
            {**row.locator, "document_id": row.document_id, "source_revision_id": row.revision_id}
        )
        return [
            EvidenceLink(
                document_id=row.document_id,
                source_revision_id=row.revision_id,
                record_id=row.record_id,
                locator=loc,
            )
        ]
    except ValueError:
        return []


def _note(d: _Depth) -> str | None:
    if d.assumed_unit:
        return f"{d.text or d.value} {_ASSUMED}"
    return d.text


def _md_value(d: _Depth) -> DepthValue:
    return DepthValue(
        reference=DepthReference.MD,
        value=d.value,
        unit=d.unit,
        datum=None,
        datum_status=DatumStatus.NOT_APPLICABLE,
        original_text=_note(d),
    )


def _datum_depth(ref: DepthReference, d: _Depth) -> DepthValue:
    if d.value is None or d.unit is None:
        return DepthValue(
            reference=ref,
            datum_status=DatumStatus.UNKNOWN,
            original_text=_note(d),
            unknown_reason="unit not stated or not recognised",
        )
    return DepthValue(
        reference=ref,
        value=d.value,
        unit=d.unit,
        datum=None,
        datum_status=DatumStatus.UNKNOWN,
        original_text=_note(d),
    )


def _unsupported(
    row: PickRow,
    reason: FormationBlockReason,
    message: str,
    name: str | None,
    qualifier: str | None,
) -> FormationUnsupportedPick:
    return FormationUnsupportedPick(
        pick_id=row.record_id,
        wellbore_id=row.wellbore_id,
        surface_name=name,
        qualifier=qualifier,
        reason=reason,
        message=message,
        evidence=_evidence(row),
    )


@dataclass
class _Placed:
    pick: FormationPick
    md_m: float
    up_m: float
    tvd_engine_m: float
    tvd_source_m: float | None
    tvdss_source_m: float | None
    conflicted: bool = False


def _tolerance(tvd_m: float) -> float:
    return max(TVD_TOLERANCE_M, TVD_TOLERANCE_RELATIVE * abs(tvd_m))


def _usable(d: _Depth | None) -> float | None:
    if d is None or (d.state or "") in rules.BAD_STATES:
        return None
    return d.metres


def _screen(
    row: PickRow, bore: Bore, name: str | None, q: str | None
) -> tuple[FormationBlockReason, str] | None:
    """The reason a pick is listed instead of drawn, or ``None`` when it can be placed."""
    traj = bore.trajectory
    if not name:
        return FormationBlockReason.NO_USABLE_DEPTH, "Pick has no surface name."
    if q is not None and q in UNSUPPORTED_QUALIFIERS:
        return (
            FormationBlockReason.UNSUPPORTED_QUALIFIER,
            f"Qualifier {q} (eroded, faulted or not logged): not a formation top; not drawn.",
        )
    if q is not None:
        return FormationBlockReason.UNSUPPORTED_QUALIFIER, f"Unreviewed qualifier {q}: not drawn."
    if row.state in rules.BAD_STATES:
        return FormationBlockReason.UNVALIDATED_PICK, f"The pick record is {row.state}; not drawn."
    md = _qty(row.attr("md"))
    if md is None or (md.state or "") in rules.BAD_STATES:
        if _qty(row.attr("twt")) is not None:
            return (
                FormationBlockReason.TWT_ONLY,
                "The pick states only a two-way time; it is never converted to depth geometry.",
            )
        return FormationBlockReason.NO_USABLE_DEPTH, "The pick has no usable MD."
    if md.metres is None:
        return (
            FormationBlockReason.UNKNOWN_UNIT,
            "The MD unit is unknown or not recognised; the pick is not placed.",
        )
    if traj is None:
        return FormationBlockReason.NO_TRAJECTORY, bore.no_trajectory_reason
    lo, hi = float(traj.md_m[0]), float(traj.md_m[-1])
    if not (lo <= md.metres <= hi):
        return (
            FormationBlockReason.OUTSIDE_SUPPORT,
            f"MD {md.metres:.3f} m is outside the surveyed range {lo:.3f}-{hi:.3f} m; "
            "not extrapolated.",
        )
    return None


def _place_bore(
    bore: Bore, rows: list[PickRow], unsupported: list[FormationUnsupportedPick]
) -> tuple[list[_Placed], list[FormationConflict]]:
    placed: list[_Placed] = []
    conflicts: list[FormationConflict] = []
    traj = bore.trajectory
    for row in sorted(rows, key=lambda r: (str(r.run_id), r.ordinal)):
        name = _text(row.attr("surface_name"))
        qualifier = _text(row.attr("qualifier"))
        q = qualifier.upper() if qualifier else None
        verdict = _screen(row, bore, name, q)
        if verdict is not None:
            unsupported.append(_unsupported(row, verdict[0], verdict[1], name, q))
            continue
        assert name is not None and traj is not None
        md = _qty(row.attr("md"))
        assert md is not None and md.metres is not None
        p = traj.position_at_md(md.metres)
        east, north, up = float(p[0]), float(p[1]), float(p[2])
        tvd_engine = -up
        tvd, tvdss = _qty(row.attr("tvd")), _qty(row.attr("tvdss"))
        tvd_m, tvdss_m = _usable(tvd), _usable(tvdss)
        pick = FormationPick(
            pick_id=row.record_id,
            wellbore_id=bore.wellbore_id,
            surface_key=surface_key(name),
            surface_name=name,
            name=name,
            md=_md_value(md),
            tvd=_datum_depth(DepthReference.TVD, tvd) if tvd is not None else None,
            tvdss=_datum_depth(DepthReference.TVDSS, tvdss) if tvdss is not None else None,
            scene_elevation=DepthValue(
                reference=DepthReference.SCENE_ELEVATION,
                value=up,
                unit="m",
                datum=None,
                datum_status=DatumStatus.NOT_APPLICABLE,
            ),
            position_enu=[east, north, up],
            qualifier=q,
            validation_state=_validation(row.state),
            evidence=_evidence(row),
            extraction_method=row.method,
        )
        item = _Placed(pick, md.metres, up, tvd_engine, tvd_m, tvdss_m)
        if tvd_m is not None:
            diff = tvd_m - tvd_engine
            tol = _tolerance(tvd_engine)
            if abs(diff) > tol:
                item.conflicted = True
                conflicts.append(
                    FormationConflict(
                        pick_id=row.record_id,
                        wellbore_id=bore.wellbore_id,
                        reason=FormationBlockReason.TVD_CONFLICT,
                        message=(
                            f"Source TVD {tvd_m:.3f} m differs from the trajectory TVD "
                            f"{tvd_engine:.3f} m at MD {md.metres:.3f} m by {diff:.3f} m "
                            f"(tolerance {tol:.3f} m). The pick datum is not stated; neither "
                            "value is chosen."
                        ),
                        source_depth=pick.tvd,
                        trajectory_depth=DepthValue(
                            reference=DepthReference.TVD,
                            value=tvd_engine,
                            unit="m",
                            datum=bore.vertical_reference,
                            datum_status=(
                                DatumStatus.STATED
                                if bore.vertical_reference
                                else DatumStatus.UNKNOWN
                            ),
                        ),
                        difference=diff,
                        difference_unit="m",
                        tolerance=tol,
                    )
                )
        placed.append(item)
    _tvdss_consistency(bore, placed, conflicts)
    placed.sort(key=lambda x: (x.md_m, str(x.pick.pick_id)))
    return placed, conflicts


def _tvdss_consistency(
    bore: Bore, placed: list[_Placed], conflicts: list[FormationConflict]
) -> None:
    """TVD minus TVDSS is the datum elevation: it must agree across the picks of one bore."""
    offs = [
        (x, x.tvd_source_m - x.tvdss_source_m)
        for x in placed
        if x.tvd_source_m is not None and x.tvdss_source_m is not None
    ]
    if len(offs) < 2:
        return
    ordered = sorted(o for _, o in offs)
    median = ordered[len(ordered) // 2]
    for x, o in offs:
        tol = _tolerance(x.tvd_engine_m)
        if abs(o - median) <= tol or x.conflicted:
            continue
        x.conflicted = True
        conflicts.append(
            FormationConflict(
                pick_id=x.pick.pick_id,
                wellbore_id=bore.wellbore_id,
                reason=FormationBlockReason.TVD_CONFLICT,
                message=(
                    f"TVD - TVDSS = {o:.3f} m for this pick but {median:.3f} m for the bore's "
                    f"other picks (tolerance {tol:.3f} m); TVD and TVDSS imply different datums."
                ),
                source_depth=x.pick.tvdss,
                trajectory_depth=None,
                difference=o - median,
                difference_unit="m",
                tolerance=tol,
            )
        )


def _footprint(traj: Trajectory) -> PlaneFootprint:
    e, n = traj.positions[:, 0], traj.positions[:, 1]
    lo_e, hi_e = min(float(e.min()), 0.0), max(float(e.max()), 0.0)  # wellhead stays inside
    lo_n, hi_n = min(float(n.min()), 0.0), max(float(n.max()), 0.0)
    margin = max(PLANE_MARGIN_MIN_M, PLANE_MARGIN_FRACTION * max(hi_e - lo_e, hi_n - lo_n))
    return PlaneFootprint(
        min_east=lo_e - margin,
        max_east=hi_e + margin,
        min_north=lo_n - margin,
        max_north=hi_n + margin,
        margin_m=margin,
    )


def _surfaces_for_bore(bore: Bore, placed: list[_Placed]) -> list[FormationSurface]:
    by_key: dict[str, list[_Placed]] = defaultdict(list)
    for x in placed:
        by_key[x.pick.surface_key].append(x)
    out: list[FormationSurface] = []
    for key in sorted(by_key):
        group = by_key[key][:MAX_PICKS_PER_SURFACE]
        blocked: list[FormationBlocked] = []
        bad = [g for g in group if g.conflicted]
        plane: LevelPlane | None = None
        if bad:
            blocked.append(
                FormationBlocked(
                    reason=FormationBlockReason.TVD_CONFLICT,
                    message="Level plane blocked: a pick's TVD conflicts with the trajectory.",
                    pick_ids=[g.pick.pick_id for g in bad],
                )
            )
        else:
            lo = min(g.up_m for g in group)
            hi = max(g.up_m for g in group)
            if hi - lo > _tolerance(max(abs(lo), abs(hi))):
                blocked.append(
                    FormationBlocked(
                        reason=FormationBlockReason.TVD_CONFLICT,
                        message=(
                            f"Level plane blocked: {len(group)} picks of this surface in one "
                            f"wellbore differ by {hi - lo:.3f} m in elevation; no crossing is "
                            "chosen."
                        ),
                        pick_ids=[g.pick.pick_id for g in group],
                    )
                )
            elif bore.trajectory is not None:
                src = group[0]
                plane = LevelPlane(
                    elevation=DepthValue(
                        reference=DepthReference.SCENE_ELEVATION,
                        value=src.up_m,
                        unit="m",
                        datum=None,
                        datum_status=DatumStatus.NOT_APPLICABLE,
                    ),
                    footprint=_footprint(bore.trajectory),
                    source_pick_id=src.pick.pick_id,
                )
        tier = FormationTier.T2 if plane is not None else FormationTier.T1
        out.append(
            FormationSurface(
                surface_key=key,
                name=group[0].pick.surface_name,
                tier=tier,
                tier_label=(
                    LEVEL_PLANE_LABEL if plane is not None else "T1 pick marker - observed"
                ),
                status=TIER_STATUS[tier],
                scope=FormationScope.WELLBORE,
                wellbore_ids=[bore.wellbore_id],
                picks=[g.pick for g in group],
                plane=plane,
                blocked=blocked,
                evidence=[e for g in group[:5] for e in g.pick.evidence][:50],
            )
        )
    return out


def _cross_bore_blocks(
    bores: dict[UUID, Bore], placed: dict[UUID, list[_Placed]]
) -> list[FormationBlocked]:
    """A surface seen in several bores is only comparable with one shared stated reference."""
    seen: dict[str, dict[UUID, list[UUID]]] = defaultdict(lambda: defaultdict(list))
    for wb, items in placed.items():
        for x in items:
            seen[x.pick.surface_key][wb].append(x.pick.pick_id)
    out: list[FormationBlocked] = []
    unknown: list[UUID] = []
    differing: list[UUID] = []
    for _key, per_bore in sorted(seen.items()):
        if len(per_bore) < 2:
            continue
        refs = {wb: _norm_ref(bores[wb].vertical_reference) for wb in per_bore}
        ids = [i for wb in sorted(per_bore, key=str) for i in per_bore[wb]]
        if any(r is None for r in refs.values()):
            unknown.extend(ids)
        elif len(set(refs.values())) > 1:
            differing.extend(ids)
    if unknown:
        out.append(
            FormationBlocked(
                reason=FormationBlockReason.UNKNOWN_DATUM,
                message=(
                    "Cross-wellbore planes and surfaces are blocked: at least one wellbore states "
                    "no vertical reference, so no shared datum can be assumed."
                ),
                pick_ids=unknown,
            )
        )
    if differing:
        out.append(
            FormationBlocked(
                reason=FormationBlockReason.DATUM_MISMATCH,
                message=(
                    "Cross-wellbore planes and surfaces are blocked: the wellbores state different "
                    "vertical references."
                ),
                pick_ids=differing,
            )
        )
    return out


def _frame(bores: list[Bore]) -> FormationFrame:
    refs = {_norm_ref(b.vertical_reference) for b in bores if b.trajectory is not None}
    shared = next(iter(refs)) if len(refs) == 1 and None not in refs else None
    stated = next(
        (b.vertical_reference for b in bores if _norm_ref(b.vertical_reference) == shared), None
    )
    return FormationFrame(
        origin_enu=[0.0, 0.0, 0.0],
        horizontal_crs=None,
        length_unit="m",
        vertical_reference=stated if shared else None,
        vertical_reference_status=DatumStatus.STATED if shared else DatumStatus.UNKNOWN,
        exaggeration_neutral=True,
        tvd_tolerance_m=TVD_TOLERANCE_M,
    )


def revision_key(rows: list[PickRow], bores: list[Bore]) -> str:
    h = hashlib.sha256()
    h.update(f"{ALGORITHM_VERSION}|{TVD_TOLERANCE_M}|{TVD_TOLERANCE_RELATIVE}".encode())
    for r in sorted(rows, key=lambda r: (str(r.run_id), r.ordinal)):
        h.update(f"|p:{r.record_id}:{r.state}:{r.revision_id}:{r.wellbore_id}".encode())
    for b in sorted(bores, key=lambda b: str(b.wellbore_id)):
        h.update(f"|b:{b.wellbore_id}:{b.trajectory_run_id}:{b.vertical_reference}".encode())
    return f"{ALGORITHM_VERSION}:{h.hexdigest()[:32]}"


def build_layer_set(
    project_id: UUID,
    wellbore_id: UUID | None,
    rows: list[PickRow],
    bores: list[Bore],
) -> FormationLayerSet:
    """Pure composition of picks and trajectories into the frozen ``FormationLayerSet``."""
    by_id = {b.wellbore_id: b for b in bores}
    unsupported: list[FormationUnsupportedPick] = []
    conflicts: list[FormationConflict] = []
    surfaces: list[FormationSurface] = []
    placed_by_bore: dict[UUID, list[_Placed]] = {}
    grouped: dict[UUID, list[PickRow]] = defaultdict(list)
    for r in rows:
        if r.wellbore_id is None or r.wellbore_id not in by_id:
            unsupported.append(
                _unsupported(
                    r,
                    FormationBlockReason.NO_TRAJECTORY,
                    "The pick is not linked to a wellbore with a trajectory; not placed.",
                    _text(r.attr("surface_name")),
                    _text(r.attr("qualifier")),
                )
            )
            continue
        grouped[r.wellbore_id].append(r)
    for wb in sorted(grouped, key=str):
        placed, found = _place_bore(by_id[wb], grouped[wb], unsupported)
        placed_by_bore[wb] = placed
        conflicts.extend(found)
        surfaces.extend(_surfaces_for_bore(by_id[wb], placed))
    blocked: list[FormationBlocked] = []
    if wellbore_id is None and len(placed_by_bore) > 1:
        blocked = _cross_bore_blocks(by_id, placed_by_bore)
    surfaces.sort(key=lambda s: (s.name.casefold(), str(s.wellbore_ids[0])))
    if len(surfaces) > MAX_SURFACES:
        surfaces = surfaces[:MAX_SURFACES]
        blocked.append(
            FormationBlocked(
                reason=FormationBlockReason.OUTSIDE_SUPPORT,
                message=f"More than {MAX_SURFACES} surfaces; the response is truncated.",
            )
        )
    unsupported.sort(key=lambda u: (str(u.wellbore_id), str(u.pick_id)))
    empty: str | None = None
    if not rows:
        empty = (
            "no formation picks in this project"
            if wellbore_id is None
            else "no formation picks for this wellbore"
        )
    elif not surfaces:
        empty = "no formation pick can be drawn; see the listed reasons"
    return FormationLayerSet(
        project_id=project_id,
        wellbore_id=wellbore_id,
        frame=_frame([b for b in bores if b.wellbore_id in placed_by_bore] or bores),
        surfaces=surfaces,
        conflicts=conflicts,
        unsupported=unsupported,
        blocked=blocked,
        empty_reason=empty,
        generated_from_revision=revision_key(rows, bores),
    )


# --- database loader (needs a database; not unit-tested here) -----------------------------------

_PICKS = text(
    """
    SELECT er.record_id, er.run_id, er.document_id, er.ordinal, er.validation_state,
           er.locator, er.attributes, lk.wellbore_id, ru.source_revision_id,
           ru.profile_name, ru.profile_version
      FROM extracted_record er
      JOIN extraction_run ru ON ru.run_id = er.run_id AND ru.project_id = er.project_id
      LEFT JOIN record_wellbore_link lk
        ON lk.run_id = er.run_id AND lk.ordinal = er.ordinal AND lk.project_id = er.project_id
     WHERE er.project_id = :p AND er.kind = 'formation_pick'
       AND NOT ru.superseded AND ru.status IN ('succeeded', 'partial')
       AND (CAST(:w AS uuid) IS NULL OR lk.wellbore_id = CAST(:w AS uuid))
     ORDER BY er.run_id, er.ordinal
    """
)


def _pick_rows(session: Session, project_id: UUID, wellbore_id: UUID | None) -> list[PickRow]:
    out: list[PickRow] = []
    for r in session.execute(_PICKS, {"p": project_id, "w": wellbore_id}).all():
        method = None
        if r.profile_name:
            method = f"{r.profile_name} {r.profile_version or ''}".strip()
        out.append(
            PickRow(
                record_id=r.record_id,
                run_id=r.run_id,
                document_id=r.document_id,
                ordinal=r.ordinal,
                state=r.validation_state,
                locator=dict(r.locator) if isinstance(r.locator, dict) else {},
                attrs=list(r.attributes or []),
                wellbore_id=r.wellbore_id,
                revision_id=r.source_revision_id,
                method=method,
            )
        )
    return out


def _load_bore(session: Session, project_id: UUID, wellbore_id: UUID) -> Bore:
    """The survey set the trajectory endpoint draws, recomputed at full resolution."""
    try:
        shown = wellpath.wellbore_trajectory(session, project_id, wellbore_id)
    except ContractError as exc:
        if exc.status_code == 404:
            return Bore(wellbore_id, None)
        raise
    run_rows = [
        r
        for r in wellpath._load(session, project_id, wellbore_id)
        if r.run_id == shown.survey_set.run_id
    ]
    chosen = wellpath._Set(
        run_id=shown.survey_set.run_id,
        document_id=shown.survey_set.document_id,
        filename=shown.survey_set.filename,
        when=run_rows[0].when if run_rows else None,
        status=shown.survey_status,
        stations=[r for r in run_rows if r.kind == "trajectory_station"],
        head=next((r for r in run_rows if r.kind == "trajectory"), None),
        header=next((r for r in run_rows if r.kind == "survey_report_header"), None),
    )
    computed = wellpath.compute_set(chosen)
    if isinstance(computed, list):
        return Bore(wellbore_id, None, no_trajectory_reason=computed[0].message)
    ref = (computed.tvd_reference or "").strip() or None
    return Bore(wellbore_id, computed.trajectory, ref, trajectory_run_id=chosen.run_id)


def formation_layer_set(
    session: Session, project_id: UUID, wellbore_id: UUID | None = None
) -> FormationLayerSet:
    identity_service.require_project(session, project_id)
    if wellbore_id is not None:
        found = session.execute(
            text("SELECT 1 FROM wellbore WHERE project_id = :p AND wellbore_id = :w"),
            {"p": project_id, "w": wellbore_id},
        ).first()
        if found is None:
            raise ContractError(ErrorCode.NOT_FOUND, "wellbore not found", 404)
    rows = _pick_rows(session, project_id, wellbore_id)
    ids = sorted({r.wellbore_id for r in rows if r.wellbore_id is not None}, key=str)
    bores = [_load_bore(session, project_id, wb) for wb in ids]
    return build_layer_set(project_id, wellbore_id, rows, bores)


__all__ = [
    "ALGORITHM_VERSION",
    "Bore",
    "PickRow",
    "build_layer_set",
    "formation_layer_set",
    "surface_key",
]
