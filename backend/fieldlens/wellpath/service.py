"""Read-only trajectory service (WELLBORE_ASSET_GENERATION section 16 F3).

One validated station set (one current document run, linked to the wellbore) is turned into local ENU
offsets from the wellhead with the deterministic double-precision minimum-curvature engine. Planned
and as-built are never mixed: planned sets are never drawn; the as-built, most recent validated set
wins and every other set is listed with why it was not drawn. A set that cannot be validated or
computed blocks only this wellbore's trajectory and says why. Nothing is assumed: a missing north
reference, an unstated CRS or a first station away from the wellhead without a stated TVD yields a
reason or a ``null``, never a default. The downsample is for display only; calculations use the full
double-precision station set."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import ARRAY, Text, bindparam, text
from sqlalchemy.orm import Session

from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.exposure import SurveyStatus
from fieldlens.contracts.trajectory import (
    NorthReferenceName,
    TrajectoryEvidence,
    TrajectoryPoint,
    TrajectoryReason,
    TrajectorySetRef,
    TrajectorySurfaceLocation,
    TrajectoryTieIn,
    WellboreTrajectory,
)
from fieldlens.engineering.trajectory import (
    NorthReference,
    Survey,
    SurveyBlockedError,
    SurveyReference,
    SurveyStation,
    Trajectory,
    compute_trajectory,
)
from fieldlens.exposure import rules
from fieldlens.identity import service as identity_service
from fieldlens.wellpath.tie_in import TieIn, TieInRejected, derive_tie_in

MAX_DISPLAY_POINTS = 400
NO_TRAJECTORY = "no_trajectory"
_FT_M = 0.3048
_TRAJECTORY_KINDS = ("trajectory", "trajectory_station", "survey_report_header")
_SURFACE_KINDS = ("well_surface_location", "survey_report_header")
_LOCAL_FRAME = "local-wellhead-offsets"

_RECORDS = text(
    """
    SELECT er.record_id, er.run_id, er.document_id, er.ordinal, er.kind, er.validation_state,
           er.locator, er.attributes, sd.original_filename AS filename, ru.finished_at,
           ru.queued_at
      FROM record_wellbore_link lk
      JOIN extracted_record er ON er.run_id = lk.run_id AND er.ordinal = lk.ordinal
      JOIN extraction_run ru ON ru.run_id = er.run_id AND ru.project_id = lk.project_id
      JOIN source_document sd ON sd.document_id = er.document_id
     WHERE lk.project_id = :p AND lk.wellbore_id = :w AND er.project_id = :p
       AND NOT ru.superseded AND ru.status IN ('succeeded', 'partial')
       AND er.kind = ANY(:kinds)
     ORDER BY er.run_id, er.ordinal
    """
).bindparams(bindparam("kinds", type_=ARRAY(Text())))

_ISSUES = text(
    """
    SELECT DISTINCT i.run_id
      FROM extraction_issue i
      JOIN extraction_run ru ON ru.run_id = i.run_id AND ru.project_id = i.project_id
     WHERE i.project_id = :p AND NOT ru.superseded AND ru.status IN ('succeeded', 'partial')
       AND i.severity = 'error' AND i.blocked_operations && :blocking
       AND EXISTS (SELECT 1 FROM record_wellbore_link lk
                    JOIN extracted_record er ON er.run_id = lk.run_id AND er.ordinal = lk.ordinal
                   WHERE lk.project_id = :p AND lk.wellbore_id = :w AND lk.run_id = i.run_id
                     AND er.kind IN ('trajectory', 'trajectory_station')
                     AND er.ordinal = ANY(i.record_ordinals))
    """
).bindparams(bindparam("blocking", type_=ARRAY(Text())))


@dataclass
class _Row:
    record_id: UUID
    run_id: UUID
    document_id: UUID
    ordinal: int
    kind: str
    state: str
    locator: dict[str, Any]
    attrs: list[dict[str, Any]]
    filename: str
    when: datetime | None

    def attr(self, key: str) -> dict[str, Any] | None:
        full = f"{self.kind}.{key}"
        return next((a for a in self.attrs if a.get("key") == full), None)

    def evidence(self) -> TrajectoryEvidence:
        loc = dict(self.locator or {})
        loc["document_id"] = str(self.document_id)
        return TrajectoryEvidence(
            document_id=self.document_id,
            filename=self.filename,
            record_id=self.record_id,
            kind=self.kind,
            ordinal=self.ordinal,
            locator=loc,
        )


@dataclass
class _Set:
    run_id: UUID
    document_id: UUID
    filename: str
    when: datetime | None
    status: SurveyStatus
    stations: list[_Row] = field(default_factory=list)
    head: _Row | None = None
    header: _Row | None = None
    blocked_by_issue: bool = False

    @property
    def page(self) -> int | None:
        """Page of the first station when the source is paged (reference only)."""
        for row in self.stations[:1]:
            page = (row.locator or {}).get("page")
            if isinstance(page, int) and not isinstance(page, bool) and page >= 1:
                return page
        return None


def _number(a: dict[str, Any] | None) -> float | None:
    if a is None:
        return None
    n = a.get("normalized_number")
    if n is None:
        n = a.get("number")
    return None if n is None else float(n)


def _state(a: dict[str, Any] | None) -> str | None:
    return None if a is None else a.get("validation_state")


def _station_value(a: dict[str, Any] | None) -> tuple[float, str | None] | None:
    """(value in metres for depths / degrees for angles, source unit) or ``None``."""
    if a is None:
        return None
    unit = a.get("unit")
    nu, norm = a.get("normalized_unit"), a.get("normalized_number")
    if norm is not None and nu in ("m", "deg"):
        return float(norm), unit
    num = a.get("number")
    if num is None:
        return None
    u = (unit or "").strip().lower()
    if u in ("m", "deg", "°", "dega"):
        return float(num), unit
    if u == "ft":
        return float(num) * _FT_M, unit
    return None


def _text_of(a: dict[str, Any] | None) -> str | None:
    if a is None:
        return None
    value = a.get("text") or a.get("original_text")
    value = str(value).strip() if value is not None else ""
    return value or None


def _north(label: str | None) -> NorthReferenceName | None:
    low = (label or "").lower()
    if "true" in low:
        return "true"
    if "grid" in low:
        return "grid"
    if "magnet" in low:
        return "magnetic"
    return None


def _rule_station(row: _Row) -> rules.Station:
    md, incl, azi = row.attr("md"), row.attr("incl"), row.attr("azi")
    return rules.Station(
        ordinal=row.ordinal,
        state=row.state,
        md=_number(md),
        md_state=_state(md),
        incl=_number(incl),
        incl_state=_state(incl),
        azi=_number(azi),
        azi_state=_state(azi),
    )


def _reason(code: str, message: str) -> TrajectoryReason:
    return TrajectoryReason(code=code, message=message)


@dataclass
class _Computed:
    trajectory: Trajectory
    north: NorthReferenceName
    azimuth_reference: str
    md_reference: str | None
    tvd_reference: str | None
    md_unit: str | None
    tvd_diff_m: float | None
    rows: list[_Row]
    first_tvd_m: float | None = None  # stated first-station TVD (tie-in input only)


def _first_ref(rows: list[_Row], key: str) -> str | None:
    for r in rows:
        a = r.attr(key)
        if a is not None and a.get("reference"):
            return str(a["reference"]).strip() or None
    return None


def compute_set(s: _Set) -> _Computed | list[TrajectoryReason]:
    """Minimum-curvature offsets for one validated set, or the reasons it cannot be computed."""
    rows = sorted(s.stations, key=lambda r: r.ordinal)
    azi_ref = _first_ref(rows, "azi")
    if azi_ref is None and s.head is not None:
        azi_ref = _text_of(s.head.attr("azi_ref"))
    if azi_ref is None and s.header is not None:
        azi_ref = _text_of(s.header.attr("north_reference"))
    north = _north(azi_ref)
    if azi_ref is None or north is None:
        return [
            _reason(
                "AZIMUTH_REFERENCE_NOT_STATED",
                "The azimuth reference (true, grid or magnetic north) is not stated; "
                "offsets are not computed and no north is assumed.",
            )
        ]
    stations: list[SurveyStation] = []
    tvds: list[float | None] = []
    md_unit: str | None = None
    for r in rows:
        md, incl, azi = (_station_value(r.attr(k)) for k in ("md", "incl", "azi"))
        if md is None or incl is None or azi is None:
            return [_reason("TRAJECTORY_INVALID_STATIONS", "A station lacks a usable MD or angle.")]
        md_unit = md_unit or md[1]
        stations.append(SurveyStation(md[0], incl[0], azi[0]))
        tvd_attr = r.attr("tvd")
        tv = _station_value(tvd_attr)
        tvds.append(tv[0] if tv is not None and _state(tvd_attr) not in rules.BAD_STATES else None)
    z0 = 0.0
    if stations[0].md != 0.0:
        if tvds[0] is None:
            return [
                _reason(
                    "WELLHEAD_START_UNKNOWN",
                    "The first station is not at MD 0 and states no valid TVD; the start depth "
                    "relative to the wellhead is not assumed.",
                )
            ]
        z0 = -tvds[0]
    survey = Survey(
        stations=tuple(stations),
        reference=SurveyReference(
            crs=_LOCAL_FRAME,
            vertical_datum=_LOCAL_FRAME,
            depth_reference=_LOCAL_FRAME,
            north_reference=NorthReference.GRID,  # offsets stay in the stated north; no conversion
        ),
        md_unit="m",
        start_east_m=0.0,
        start_north_m=0.0,
        start_z_m=z0,
    )
    try:
        trajectory = compute_trajectory(survey)
    except SurveyBlockedError as exc:
        return [_reason(f"SURVEY_{i.code.value.upper()}", i.message) for i in exc.issues[:5]]
    diffs = [
        abs(-float(trajectory.positions[k, 2]) - tvds[src])  # type: ignore[operator]
        for k, src in enumerate(trajectory.source_indices)
        if tvds[src] is not None
    ]
    header = s.header
    return _Computed(
        trajectory=trajectory,
        north=north,
        azimuth_reference=azi_ref,
        md_reference=_first_ref(rows, "md")
        or (_text_of(header.attr("md_reference")) if header else None),
        tvd_reference=_first_ref(rows, "tvd")
        or (_text_of(header.attr("tvd_reference")) if header else None),
        md_unit=md_unit,
        tvd_diff_m=max(diffs) if diffs else None,
        rows=rows,
        first_tvd_m=tvds[0],
    )


def display_points(
    trajectory: Trajectory, max_points: int = MAX_DISPLAY_POINTS
) -> list[TrajectoryPoint]:
    """Display-only points: every derived station when few, else uniform-MD samples on the arcs
    (end points exact). Never an input to any calculation."""
    n = len(trajectory.md_m)
    if n <= max_points:
        idx = range(n)
        return [
            TrajectoryPoint(
                md_m=float(trajectory.md_m[i]),
                tvd_m=-float(trajectory.positions[i, 2]),
                east_m=float(trajectory.positions[i, 0]),
                north_m=float(trajectory.positions[i, 1]),
            )
            for i in idx
        ]
    out: list[TrajectoryPoint] = []
    for md in np.linspace(float(trajectory.md_m[0]), float(trajectory.md_m[-1]), max_points):
        p = trajectory.position_at_md(float(md))
        out.append(
            TrajectoryPoint(
                md_m=float(md), tvd_m=-float(p[2]), east_m=float(p[0]), north_m=float(p[1])
            )
        )
    return out


def _surface(rows: list[_Row], prefer_run: UUID | None) -> TrajectorySurfaceLocation | None:
    """Usable sourced surface location; CRS/datum text only as stated (never an EPSG guess)."""
    found: list[tuple[int, datetime, TrajectorySurfaceLocation]] = []
    for r in rows:
        if r.state in rules.BAD_STATES:
            continue
        if r.kind == "well_surface_location":
            ek, nk, latk, lonk = "easting", "northing", "latitude", "longitude"
        else:
            ek, nk, latk, lonk = "well_easting", "well_northing", "", ""
        ea, na = r.attr(ek), r.attr(nk)
        la, lo = (r.attr(latk) if latk else None), (r.attr(lonk) if lonk else None)

        def good(a: dict[str, Any] | None) -> float | None:
            return None if a is None or _state(a) in rules.BAD_STATES else _number(a)

        e, n, lat, lon = good(ea), good(na), good(la), good(lo)
        unit = None
        if e is not None and n is not None and ea is not None:
            unit = ea.get("normalized_unit") or ea.get("unit")
            if not unit:
                e = n = None
        if (e is None or n is None) and (lat is None or lon is None):
            continue
        if e is None or n is None:
            e = n = None
        if lat is None or lon is None:
            lat = lon = None
        crs = (ea.get("reference") if ea else None) or _text_of(r.attr("map_zone"))
        crs = str(crs).strip() if crs else None
        datum = _text_of(r.attr("geo_datum"))
        if e is None:
            unit = None
        loc = TrajectorySurfaceLocation(
            easting=e,
            northing=n,
            unit=unit,
            latitude=lat,
            longitude=lon,
            crs=crs or None,
            geodetic_datum=datum,
            evidence=r.evidence(),
        )
        rank = 0 if prefer_run is not None and r.run_id == prefer_run else 1
        found.append((rank, r.when or datetime.min, loc))
    if not found:
        return None
    found.sort(key=lambda t: (t[0], -t[1].timestamp() if t[1] != datetime.min else 0.0))
    return found[0][2]


def _load(session: Session, project_id: UUID, wellbore_id: UUID) -> list[_Row]:
    kinds = sorted(set(_TRAJECTORY_KINDS) | set(_SURFACE_KINDS))
    rows = session.execute(_RECORDS, {"p": project_id, "w": wellbore_id, "kinds": kinds}).all()
    return [
        _Row(
            record_id=r.record_id,
            run_id=r.run_id,
            document_id=r.document_id,
            ordinal=r.ordinal,
            kind=r.kind,
            state=r.validation_state,
            locator=dict(r.locator) if isinstance(r.locator, dict) else {},
            attrs=list(r.attributes or []),
            filename=r.filename,
            when=r.finished_at or r.queued_at,
        )
        for r in rows
    ]


def _status_of(rows: list[_Row]) -> SurveyStatus:
    headers = [r for r in rows if r.kind == "survey_report_header"]
    texts = [_text_of(r.attr("survey_status")) for r in headers]
    return rules.normalize_survey_status(bool(headers), texts)


def _set_ref(
    s: _Set, validated: bool, used: bool, reasons: list[TrajectoryReason]
) -> TrajectorySetRef:
    return TrajectorySetRef(
        document_id=s.document_id,
        run_id=s.run_id,
        filename=s.filename,
        page=s.page,
        survey_status=s.status,
        station_count=len(s.stations),
        validated=validated,
        used=used,
        reasons=reasons,
    )


def wellbore_trajectory(
    session: Session, project_id: UUID, wellbore_id: UUID
) -> WellboreTrajectory:
    identity_service.require_project(session, project_id)
    exists = session.execute(
        text("SELECT 1 FROM wellbore WHERE project_id = :p AND wellbore_id = :w"),
        {"p": project_id, "w": wellbore_id},
    ).first()
    if exists is None:
        raise ContractError(ErrorCode.NOT_FOUND, "wellbore not found", 404)

    rows = _load(session, project_id, wellbore_id)
    by_run: dict[UUID, list[_Row]] = defaultdict(list)
    for r in rows:
        by_run[r.run_id].append(r)
    blocked_runs = {
        r.run_id
        for r in session.execute(
            _ISSUES,
            {"p": project_id, "w": wellbore_id, "blocking": sorted(rules.BLOCKING_OPERATIONS)},
        )
    }
    sets: list[_Set] = []
    for run_id, run_rows in by_run.items():
        stations = [r for r in run_rows if r.kind == "trajectory_station"]
        if not stations:
            continue
        sets.append(
            _Set(
                run_id=run_id,
                document_id=run_rows[0].document_id,
                filename=run_rows[0].filename,
                when=run_rows[0].when,
                status=_status_of(run_rows),
                stations=stations,
                head=next((r for r in run_rows if r.kind == "trajectory"), None),
                header=next((r for r in run_rows if r.kind == "survey_report_header"), None),
                blocked_by_issue=run_id in blocked_runs,
            )
        )

    def priority(s: _Set) -> tuple[int, float, str]:
        stamp = s.when.timestamp() if s.when else 0.0
        return (0 if s.status == "as_built" else 1, -stamp, str(s.run_id))

    sets.sort(key=priority)
    refs: list[TrajectorySetRef] = []
    chosen: tuple[_Set, _Computed] | None = None
    for s in sets:
        verdict = rules.judge_station_set(
            [_rule_station(r) for r in s.stations], s.status, s.blocked_by_issue
        )
        reasons = [_reason(x.code, x.message) for x in verdict.reasons]
        if not verdict.validated:
            refs.append(_set_ref(s, False, False, reasons))
            continue
        if chosen is not None:
            reasons.append(
                _reason(
                    "NOT_SELECTED",
                    "Another validated set (as-built, most recent) is drawn; sets are never mixed.",
                )
            )
            refs.append(_set_ref(s, True, False, reasons))
            continue
        computed = compute_set(s)
        if isinstance(computed, list):
            refs.append(_set_ref(s, True, False, computed))
            continue
        chosen = (s, computed)
        refs.append(_set_ref(s, True, True, []))

    if chosen is None:
        raise ContractError(
            ErrorCode.NOT_FOUND,
            "no valid survey is available for this wellbore",
            404,
            details={
                "code": NO_TRAJECTORY,
                "sets": [
                    {
                        "filename": r.filename,
                        "survey_status": r.survey_status,
                        "reasons": [x.code for x in r.reasons],
                    }
                    for r in refs[:10]
                ],
            },
        )

    s, c = chosen
    traj = c.trajectory
    used_ref = next(r for r in refs if r.used)
    points = display_points(traj)
    surface_rows = [r for r in rows if r.kind in _SURFACE_KINDS]
    sfound = _surface(surface_rows, s.run_id)
    surface = sfound
    warnings: list[TrajectoryReason] = []
    if s.status == "unstated":
        warnings.append(
            _reason("SURVEY_STATUS_UNSTATED", "The source does not state planned or as-built.")
        )
    if surface is None:
        warnings.append(_reason("SURFACE_LOCATION_NOT_VALIDATED", "No usable surface location."))
    elif surface.crs is None:
        warnings.append(_reason("CRS_NOT_STATED", "The surface location states no CRS."))
    if c.north != "grid":
        warnings.append(
            _reason(
                "OFFSETS_NOT_GRID_NORTH",
                f"Offsets are relative to {c.north} north; no grid conversion is applied.",
            )
        )
    tie_in: TrajectoryTieIn | None = None
    first = traj.survey.stations[0]
    if c.first_tvd_m is not None:
        tie = derive_tie_in(first.md, c.first_tvd_m, first.inclination_deg, first.azimuth_deg)
        if isinstance(tie, TieIn):
            tie_in = TrajectoryTieIn(
                kind="vertical" if tie.kind == "vertical" else "arc",
                max_dls_deg_per_30m=tie.max_dls_deg_per_30m,
                points=tie.points,
            )
            warnings.append(
                _reason(
                    "TIE_IN_DERIVED",
                    "The survey starts below the wellhead; a derived display-only tie-in joins "
                    "the wellhead to the first station. Depth records are unchanged.",
                )
            )
        elif isinstance(tie, TieInRejected):
            warnings.append(_reason(tie.code, tie.message))
    evidence: list[TrajectoryEvidence] = []
    ordered = c.rows
    if s.header is not None:
        evidence.append(s.header.evidence())
    evidence.extend([ordered[0].evidence(), ordered[-1].evidence()])
    if surface is not None:
        evidence.append(surface.evidence)
    return WellboreTrajectory(
        project_id=project_id,
        wellbore_id=wellbore_id,
        survey_set=used_ref,
        survey_status=s.status,
        md_unit=c.md_unit,
        md_reference=c.md_reference,
        tvd_reference=c.tvd_reference,
        azimuth_reference=c.azimuth_reference,
        north_reference=c.north,
        crs=surface.crs if surface else None,
        geodetic_datum=surface.geodetic_datum if surface else None,
        surface_location=surface,
        points=points,
        tie_in=tie_in,
        displayed_count=len(points),
        source_count=len(s.stations),
        md_min_m=float(traj.md_m[0]),
        md_max_m=float(traj.md_m[-1]),
        max_tvd_m=float(-np.min(traj.positions[:, 2])),
        source_tvd_max_abs_diff_m=c.tvd_diff_m
        if c.tvd_diff_m is None or math.isfinite(c.tvd_diff_m)
        else None,
        evidence=evidence,
        other_sets=[r for r in refs if not r.used],
        warnings=warnings,
    )
