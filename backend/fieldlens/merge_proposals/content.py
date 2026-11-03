"""Deterministic, zero-cost content evidence for merge candidates (TASK-086).

Names alone rarely prove that a short label (``F-5``) and a block-qualified wellbore
(``15/9-F-5``) are one bore: real sources seldom spell both in one passage. The structured records
usually do carry proof, e.g. the same survey (station count, MD range, md/incl/azi hash) parsed
from two different files. This module summarizes that content per party once per project, compares
pairs, and renders the comparison as a compact candidate table for the model and as the
``survey_match`` evidence the validator accepts. It never calls a model and never changes identity.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldlens.identity.resolver import SubjectGroup
from fieldlens.persistence import models as m

from .guards import Party

CONTENT_VERSION = "merge-content-1"
STATION_KIND = "trajectory_station"
SURFACE_KIND = "well_surface_location"
MAX_ROWS_PER_GROUP = 20_000
MIN_STATIONS = 10
SAME_SURFACE_M = 5.0
CONTRADICTORY_SURFACE_M = 50.0

SURVEY_EXACT = "exact"
SURVEY_STATIONS_MD = "stations_md"
SURVEY_DIFFERENT = "different"
SURVEY_NO_DATA = "no_data"
SURFACE_SAME = "same"
SURFACE_CONTRADICTORY = "contradictory"
SURFACE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class SurveyPrint:
    document_id: UUID
    stations: int
    md_min: float
    md_max: float
    hash_full: str
    hash_md: str

    def describe(self) -> str:
        return (
            f"{self.stations} stations, MD {self.md_min:g}-{self.md_max:g}, "
            f"md/incl/azi hash {self.hash_full[:10]}"
        )


@dataclass
class PartyContent:
    surveys: list[SurveyPrint] = field(default_factory=list)
    surface: list[tuple[float, float, str]] = field(default_factory=list)
    """(first, second, system): easting/northing metres (``grid``) or latitude/longitude (``geo``)."""
    families: set[str] = field(default_factory=set)
    fields: set[str] = field(default_factory=set)
    documents: set[UUID] = field(default_factory=set)


@dataclass(frozen=True)
class PairEvidence:
    name_similarity: float
    same_slot: bool
    same_suffix: bool
    shared_families: tuple[str, ...]
    survey: str
    survey_target: SurveyPrint | None
    survey_member: SurveyPrint | None
    surface: str
    surface_detail: str
    fields: tuple[str, ...]

    @property
    def survey_match(self) -> bool:
        return self.survey in (SURVEY_EXACT, SURVEY_STATIONS_MD)

    @property
    def surface_contradictory(self) -> bool:
        return self.surface == SURFACE_CONTRADICTORY

    def table_row(self) -> dict[str, Any]:
        """Compact, bounded row for the model prompt (no document text)."""
        row: dict[str, Any] = {
            "name_similarity": self.name_similarity,
            "same_slot": self.same_slot,
            "same_suffix": self.same_suffix,
            "shared_source_family": list(self.shared_families),
            "survey": self.survey,
            "surface_location": self.surface,
        }
        if self.survey_target and self.survey_member:
            row["survey_target"] = self.survey_target.describe()
            row["survey_candidate"] = self.survey_member.describe()
        if self.surface_detail:
            row["surface_detail"] = self.surface_detail
        if self.fields:
            row["field_context"] = list(self.fields)
        return row

    def signature(self) -> list[Any]:
        """Stable summary folded into the run fingerprint (any change re-plans the stage)."""
        return [
            CONTENT_VERSION,
            self.name_similarity,
            self.same_slot,
            self.same_suffix,
            list(self.shared_families),
            self.survey,
            self.survey_target.hash_full if self.survey_target else None,
            self.survey_member.hash_full if self.survey_member else None,
            self.surface,
        ]

    def survey_statement(self, target_name: str, member_name: str) -> str:
        assert self.survey_target is not None and self.survey_member is not None
        kind = (
            "identical md/incl/azi values"
            if self.survey == SURVEY_EXACT
            else "identical station count and MD values"
        )
        return (
            f"Survey of {member_name} ({self.survey_member.describe()}) has {kind} to the "
            f"survey of {target_name} ({self.survey_target.describe()})."
        )


# ---- extraction of per-party content --------------------------------------------------------


def _num(attrs: Iterable[dict[str, Any]], suffix: str) -> float | None:
    for a in attrs:
        key = str(a.get("key", ""))
        if key.endswith("." + suffix):
            value = a.get("normalized_number")
            if value is None:
                value = a.get("number")
            try:
                f = None if value is None else float(value)
            except (TypeError, ValueError):
                return None
            return f if f is not None and math.isfinite(f) else None
    return None


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def survey_print(document_id: UUID, rows: list[list[dict[str, Any]]]) -> SurveyPrint | None:
    """Fingerprint of one document's stations; ``None`` below ``MIN_STATIONS`` usable stations."""
    stations = sorted(
        (
            (md, _num(attrs, "incl"), _num(attrs, "azi"))
            for attrs in rows
            if (md := _num(attrs, "md")) is not None
        ),
        key=lambda s: (s[0], -1.0 if s[1] is None else s[1], -1.0 if s[2] is None else s[2]),
    )
    if len(stations) < MIN_STATIONS:
        return None
    full = "\n".join(f"{_fmt(a)},{_fmt(b)},{_fmt(c)}" for a, b, c in stations)
    md_only = "\n".join(_fmt(a) for a, _, _ in stations)
    return SurveyPrint(
        document_id,
        len(stations),
        stations[0][0],
        stations[-1][0],
        hashlib.sha256(full.encode()).hexdigest(),
        hashlib.sha256(md_only.encode()).hexdigest(),
    )


def _surface(attrs: list[dict[str, Any]]) -> tuple[float, float, str] | None:
    e, n = _num(attrs, "easting"), _num(attrs, "northing")
    if e is not None and n is not None:
        return e, n, "grid"
    lat, lon = _num(attrs, "latitude"), _num(attrs, "longitude")
    if lat is not None and lon is not None:
        return lat, lon, "geo"
    return None


def party_content(session: Session, group: SubjectGroup) -> PartyContent:
    """Survey fingerprints, surface locations, source families and field context of one subject
    group (its current successful runs)."""
    er = m.extracted_record
    out = PartyContent(documents=set(group.documents))
    out.families.update(group.kinds)  # record kinds: survey, equipment, production, ...
    field_name = group.subject.get("field")
    if isinstance(field_name, str) and field_name.strip():
        out.fields.add(field_name.strip())
    if not group.runs:
        return out
    rows = session.execute(
        select(er.c.document_id, er.c.kind, er.c.attributes)
        .where(
            er.c.run_id.in_(list(group.runs)),
            er.c.subject == group.subject,
            er.c.kind.in_((STATION_KIND, SURFACE_KIND)),
        )
        .order_by(er.c.document_id, er.c.ordinal)
        .limit(MAX_ROWS_PER_GROUP)
    ).all()
    by_doc: dict[UUID, list[list[dict[str, Any]]]] = {}
    for row in rows:
        attrs = list(row.attributes) if isinstance(row.attributes, list) else []
        if row.kind == STATION_KIND:
            by_doc.setdefault(row.document_id, []).append(attrs)
        else:
            loc = _surface(attrs)
            if loc is not None:
                out.surface.append(loc)
    for doc, station_rows in sorted(by_doc.items(), key=lambda kv: str(kv[0])):
        sp = survey_print(doc, station_rows)
        if sp is not None:
            out.surveys.append(sp)
    return out


def merge_content(into: PartyContent, other: PartyContent) -> None:
    into.surveys.extend(s for s in other.surveys if s not in into.surveys)
    into.surface.extend(s for s in other.surface if s not in into.surface)
    into.families |= other.families
    into.fields |= other.fields
    into.documents |= other.documents


# ---- pair comparison ---------------------------------------------------------------------


def _distance_m(a: tuple[float, float, str], b: tuple[float, float, str]) -> float | None:
    if a[2] != b[2]:
        return None
    if a[2] == "grid":
        return math.hypot(a[0] - b[0], a[1] - b[1])
    lat = math.radians((a[0] + b[0]) / 2)
    return 111_320.0 * math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(lat))


def compare_surface(target: PartyContent, member: PartyContent) -> tuple[str, str]:
    dists = [
        d for a in target.surface for b in member.surface if (d := _distance_m(a, b)) is not None
    ]
    if not dists:
        return SURFACE_UNKNOWN, ""
    nearest = min(dists)
    if nearest <= SAME_SURFACE_M:
        return SURFACE_SAME, f"{nearest:.1f} m apart"
    if nearest >= CONTRADICTORY_SURFACE_M:
        return SURFACE_CONTRADICTORY, f"{nearest:.0f} m apart"
    return SURFACE_UNKNOWN, f"{nearest:.0f} m apart"


def compare_survey(
    target: PartyContent, member: PartyContent
) -> tuple[str, SurveyPrint | None, SurveyPrint | None]:
    if not target.surveys or not member.surveys:
        return SURVEY_NO_DATA, None, None
    best: tuple[str, SurveyPrint, SurveyPrint] | None = None
    for t in target.surveys:
        for c in member.surveys:
            if t.document_id == c.document_id:
                continue  # one document cannot corroborate itself
            if t.hash_full == c.hash_full:
                return SURVEY_EXACT, t, c
            if t.stations == c.stations and t.hash_md == c.hash_md and best is None:
                best = (SURVEY_STATIONS_MD, t, c)
    if best is not None:
        return best
    return SURVEY_DIFFERENT, None, None


def name_similarity(a: str, b: str) -> float:
    return round(SequenceMatcher(None, a.casefold(), b.casefold()).ratio(), 2)


def pair_evidence(
    target: Party, target_content: PartyContent, member: Party, member_content: PartyContent
) -> PairEvidence:
    td, md = target.designator, member.designator
    survey, st, sm = compare_survey(target_content, member_content)
    surface, detail = compare_surface(target_content, member_content)
    return PairEvidence(
        name_similarity=name_similarity(target.name, member.name),
        same_slot=bool(td and md and td.slot == md.slot),
        same_suffix=bool(td and md and td.suffix == md.suffix),
        shared_families=tuple(sorted(target_content.families & member_content.families)),
        survey=survey,
        survey_target=st,
        survey_member=sm,
        surface=surface,
        surface_detail=detail,
        fields=tuple(sorted(target_content.fields | member_content.fields))[:3],
    )
