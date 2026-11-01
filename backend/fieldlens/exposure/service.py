"""Read-only exposure service: stored records -> per-wellbore, per-category view and the start gate.

Everything is scoped by ``project_id`` and by the wellbore's identity links (``record_wellbore_link``);
only the *current* (non-superseded) succeeded/partial extraction runs count. The identity rows
stay the authority: this module reads them and never writes."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, bindparam, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session

from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.exposure import (
    CategoryExposure,
    ExposureAttribute,
    ExposureFinding,
    ExposureGroup,
    ExposureProposal,
    ExposureRecord,
    GateCondition,
    GateReason,
    ProjectExposure,
    StartGate,
    SurveyStatus,
    TrajectorySetCheck,
    WellboreExposure,
    WellboreGate,
    WellExposure,
)
from fieldlens.identity import service as identity_service
from fieldlens.identity.resolver import RESOLVER_VERSION

from . import rules

SAMPLE_RECORDS = 3
MAX_ATTRIBUTES = 40
MAX_PROPOSALS_PER_CATEGORY = 25
MAX_FINDINGS_PER_CATEGORY = 100
MAX_CANDIDATES_READ = 5000

_LINKED = """
    FROM record_wellbore_link lk
    JOIN extracted_record er ON er.run_id = lk.run_id AND er.ordinal = lk.ordinal
    JOIN extraction_run ru ON ru.run_id = er.run_id AND ru.project_id = lk.project_id
    JOIN source_document sd ON sd.document_id = er.document_id
    WHERE lk.project_id = :p AND lk.wellbore_id = :w
      AND NOT ru.superseded AND ru.status IN ('succeeded', 'partial')
"""
_GROUPS = (
    "SELECT er.run_id, er.document_id, er.kind, er.validation_state, count(*) AS n, "
    "min(sd.original_filename) AS filename, min(ru.profile_name) AS profile_name "
    + _LINKED
    + " GROUP BY er.run_id, er.document_id, er.kind, er.validation_state"
)
_SAMPLES = (
    "SELECT * FROM (SELECT er.record_id, er.run_id, er.document_id, er.ordinal, er.kind, "  # noqa: S608
    "er.validation_state, er.locator, er.attributes, "
    "row_number() OVER (PARTITION BY er.run_id, er.kind ORDER BY er.ordinal) AS rn "
    + _LINKED
    + ") s WHERE rn <= :k ORDER BY run_id, kind, ordinal"
)


def _station_sql() -> str:
    def lateral(alias: str, key: str) -> str:
        return (
            "LEFT JOIN LATERAL (SELECT COALESCE((a->>'normalized_number')::float8, "  # noqa: S608
            f"(a->>'number')::float8) AS n, a->>'validation_state' AS s "
            f"FROM jsonb_array_elements(er.attributes) a "
            f"WHERE a->>'key' = 'trajectory_station.{key}' LIMIT 1) {alias} ON true "
        )

    head, tail = _LINKED.split("WHERE", 1)
    return (
        "SELECT er.run_id, er.ordinal, er.validation_state, "
        "md.n AS md, md.s AS md_s, incl.n AS incl, incl.s AS incl_s, azi.n AS azi, azi.s AS azi_s "
        + head
        + lateral("md", "md")
        + lateral("incl", "incl")
        + lateral("azi", "azi")
        + "WHERE"
        + tail
        + " AND er.kind = 'trajectory_station' ORDER BY er.run_id, er.ordinal"
    )


_STATUS = text(
    "SELECT er.run_id, a->>'text' AS status FROM extracted_record er, "
    "jsonb_array_elements(er.attributes) a "
    "WHERE er.project_id = :p AND er.run_id = ANY(:runs) AND er.kind = 'survey_report_header' "
    "AND a->>'key' = 'survey_report_header.survey_status'"
).bindparams(bindparam("runs", type_=ARRAY(PG_UUID(as_uuid=True))))

_ISSUES = text(
    """
    SELECT i.issue_id, i.run_id, ru.document_id, i.code, i.severity, i.message,
           i.attribute_keys, i.record_ordinals, i.blocked_operations, i.locators,
           (SELECT array_agg(DISTINCT er.kind)
              FROM record_wellbore_link lk
              JOIN extracted_record er ON er.run_id = lk.run_id AND er.ordinal = lk.ordinal
             WHERE lk.project_id = :p AND lk.wellbore_id = :w AND lk.run_id = i.run_id
               AND lk.ordinal = ANY(i.record_ordinals)) AS kinds
      FROM extraction_issue i
      JOIN extraction_run ru ON ru.run_id = i.run_id AND ru.project_id = i.project_id
     WHERE i.project_id = :p AND NOT ru.superseded AND ru.status IN ('succeeded', 'partial')
       AND i.run_id IN (SELECT DISTINCT lk.run_id FROM record_wellbore_link lk
                         WHERE lk.project_id = :p AND lk.wellbore_id = :w)
     ORDER BY i.created_at, i.issue_id
    """
)

_CANDIDATES = text(
    """
    SELECT candidate_id, document_id, state, validation_state, evidence_class, label,
           attributes->>'kind' AS akind, attributes->>'attribute_key' AS akey,
           attributes->>'category' AS acategory, locator
      FROM extraction_candidate
     WHERE project_id = :p AND wellbore_id = :w
     ORDER BY created_at DESC, candidate_id
     LIMIT :lim
    """
)
_CANDIDATE_COUNTS = text(
    """
    SELECT attributes->>'kind' AS akind, attributes->>'attribute_key' AS akey,
           attributes->>'category' AS acategory, state, validation_state, count(*) AS n
      FROM extraction_candidate
     WHERE project_id = :p AND wellbore_id = :w
     GROUP BY 1, 2, 3, 4, 5
    """
)

_SURFACE = text(
    "SELECT er.record_id, er.validation_state, er.attributes "
    + _LINKED
    + " AND er.kind = 'well_surface_location' ORDER BY er.run_id, er.ordinal"
)


def _locator(raw: Any, document_id: UUID) -> dict[str, Any]:
    loc = dict(raw) if isinstance(raw, dict) else {}
    loc["document_id"] = str(document_id)
    return loc


def _attribute(raw: dict[str, Any], document_id: UUID) -> ExposureAttribute:
    number = raw.get("normalized_number")
    if number is None:
        number = raw.get("number")
    return ExposureAttribute(
        key=str(raw.get("key", "")),
        original_text=raw.get("original_text"),
        number=number,
        unit=raw.get("normalized_unit") or raw.get("unit"),
        reference=raw.get("reference"),
        unknown_reason=raw.get("unknown_reason"),
        validation_state=str(raw.get("validation_state", "unreviewed")),
        locator=_locator(raw.get("locator"), document_id),
    )


def _record(row: Any) -> ExposureRecord:
    attrs = list(row.attributes or [])
    return ExposureRecord(
        record_id=row.record_id,
        ordinal=row.ordinal,
        kind=row.kind,
        validation_state=row.validation_state,
        locator=_locator(row.locator, row.document_id),
        attributes=[_attribute(a, row.document_id) for a in attrs[:MAX_ATTRIBUTES]],
        attributes_truncated=len(attrs) > MAX_ATTRIBUTES,
    )


def _candidate_category(akind: str | None, akey: str | None, acategory: str | None) -> str:
    if akind == "equipment":
        return "equipment_completion"
    if akind == "measurement" and akey:
        return rules.category_of_key(akey) or "other"
    return "other"


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def wellbore_exposure(
    session: Session, project_id: UUID, well_id: UUID, wellbore_id: UUID, name: str
) -> WellboreExposure:
    """Exposure + gate for one wellbore (the caller has verified project and wellbore scope)."""
    params = {"p": project_id, "w": wellbore_id}
    group_rows = session.execute(text(_GROUPS), params).all()
    sample_rows = session.execute(text(_SAMPLES), {**params, "k": SAMPLE_RECORDS}).all()
    runs = sorted({r.run_id for r in group_rows}, key=str)
    statuses: dict[UUID, SurveyStatus] = {}
    if runs:
        texts: dict[UUID, list[str | None]] = defaultdict(list)
        for r in session.execute(_STATUS, {"p": project_id, "runs": runs}):
            texts[r.run_id].append(r.status)
        for run in runs:
            statuses[run] = rules.normalize_survey_status(run in texts, texts.get(run, []))

    # --- groups per category ---
    grouped: dict[tuple[Any, Any, str], dict[str, Any]] = {}
    for r in group_rows:
        g = grouped.setdefault(
            (r.run_id, r.document_id, r.kind),
            {"n": 0, "states": defaultdict(int), "filename": r.filename, "profile": r.profile_name},
        )
        g["n"] += r.n
        g["states"][r.validation_state] += r.n
    samples: dict[tuple[Any, str], list[ExposureRecord]] = defaultdict(list)
    for s in sample_rows:
        samples[(s.run_id, s.kind)].append(_record(s))
    by_cat_groups: dict[str, list[ExposureGroup]] = defaultdict(list)
    for (run_id, document_id, kind), g in sorted(
        grouped.items(), key=lambda kv: (str(kv[0][1]), kv[0][2], str(kv[0][0]))
    ):
        category = rules.category_of_kind(kind)
        by_cat_groups[category].append(
            ExposureGroup(
                document_id=document_id,
                run_id=run_id,
                filename=g["filename"],
                profile_name=g["profile"],
                kind=kind,
                record_count=g["n"],
                validation_counts=dict(sorted(g["states"].items())),
                survey_status=statuses.get(run_id) if category == "trajectory" else None,
                sample=samples.get((run_id, kind), []),
                sample_truncated=g["n"] > len(samples.get((run_id, kind), [])),
            )
        )

    # --- findings (conflicts and gaps) ---
    findings_by_cat: dict[str, list[ExposureFinding]] = defaultdict(list)
    blocking_runs: set[UUID] = set()
    for i in session.execute(_ISSUES, params).all():
        ordinals = list(i.record_ordinals or [])
        kinds = list(i.kinds or [])
        if ordinals and not kinds:
            continue  # the issue concerns records of another wellbore in the same document
        scope = "record" if kinds else "document"
        cats = {rules.category_of_kind(k) for k in kinds}
        if not cats:
            cats = {rules.category_of_key(k) or "other" for k in i.attribute_keys or []} or {
                "other"
            }
        blocked = list(i.blocked_operations or [])
        if (
            i.severity == "error"
            and rules.BLOCKING_OPERATIONS & set(blocked)
            and "trajectory" in cats
        ):
            blocking_runs.add(i.run_id)
        finding = ExposureFinding(
            issue_id=i.issue_id,
            code=i.code,
            severity=i.severity,
            kind=rules.finding_kind(i.code),
            message=i.message,
            run_id=i.run_id,
            document_id=i.document_id,
            scope=scope,
            attribute_keys=list(i.attribute_keys or []),
            blocked_operations=blocked,
            locators=[_locator(loc, i.document_id) for loc in (i.locators or [])[:5]],
        )
        for c in sorted(cats):
            findings_by_cat[c].append(finding)

    # --- candidates (proposals; never source records) ---
    proposals: dict[str, list[ExposureProposal]] = defaultdict(list)
    proposal_total: dict[str, int] = defaultdict(int)
    accepted_count: dict[str, int] = defaultdict(int)
    # Exact counts come from an aggregate; the bounded read below only supplies the sample.
    for row in session.execute(_CANDIDATE_COUNTS, params).all():
        category = _candidate_category(row.akind, row.akey, row.acategory)
        proposal_total[category] += row.n
        if row.state == "accepted" and row.validation_state == "valid":
            accepted_count[category] += row.n
    for cand in session.execute(_CANDIDATES, {**params, "lim": MAX_CANDIDATES_READ}).all():
        category = _candidate_category(cand.akind, cand.akey, cand.acategory)
        accepted = cand.state == "accepted" and cand.validation_state == "valid"
        if len(proposals[category]) < MAX_PROPOSALS_PER_CATEGORY:
            proposals[category].append(
                ExposureProposal(
                    candidate_id=cand.candidate_id,
                    document_id=cand.document_id,
                    state=cand.state,
                    validation_state=cand.validation_state,
                    evidence_class=cand.evidence_class,
                    label=cand.label,
                    attribute_kind=cand.akind,
                    locator=_locator(cand.locator, cand.document_id),
                    is_accepted_fact=accepted,
                )
            )

    # --- trajectory gate ---
    station_rows: dict[UUID, list[rules.Station]] = defaultdict(list)
    for st in session.execute(text(_station_sql()), params).all():
        station_rows[st.run_id].append(
            rules.Station(
                ordinal=st.ordinal,
                state=st.validation_state,
                md=_num(st.md),
                md_state=st.md_s,
                incl=_num(st.incl),
                incl_state=st.incl_s,
                azi=_num(st.azi),
                azi_state=st.azi_s,
            )
        )
    sets: list[TrajectorySetCheck] = []
    names = {g.run_id: (g.document_id, g.filename) for g in by_cat_groups["trajectory"]}
    for run_id in sorted(station_rows, key=str):
        status = statuses.get(run_id, "not_applicable")
        verdict = rules.judge_station_set(station_rows[run_id], status, run_id in blocking_runs)
        document_id, filename = names[run_id]
        sets.append(
            TrajectorySetCheck(
                document_id=document_id,
                run_id=run_id,
                filename=filename,
                survey_status=status,
                station_count=verdict.station_count,
                usable_station_count=verdict.usable,
                validated=verdict.validated,
                reasons=verdict.reasons,
            )
        )
    validated = any(x.validated for x in sets)

    unmet: list[GateReason] = []
    if not validated:
        if not sets:
            unmet.append(
                GateReason(
                    code="NO_TRAJECTORY_RECORDS",
                    message=f"No trajectory stations are linked to wellbore {name}.",
                    wellbore_id=wellbore_id,
                )
            )
        for chk in sets:
            for reason in chk.reasons:
                unmet.append(reason.model_copy(update={"wellbore_id": wellbore_id}))

    located = False
    surface_present = False
    for r in session.execute(_SURFACE, params).all():
        surface_present = True
        attrs = [
            (
                str(a.get("key", "")).split(".", 1)[-1],
                a.get("normalized_number")
                if a.get("normalized_number") is not None
                else a.get("number"),
                a.get("validation_state"),
            )
            for a in (r.attributes or [])
        ]
        if r.validation_state not in rules.BAD_STATES and rules.surface_location_usable(attrs):
            located = True
    warnings: list[GateReason] = []
    if not located:
        warnings.append(
            GateReason(
                code="SURFACE_LOCATION_INCOMPLETE"
                if surface_present
                else "SURFACE_LOCATION_MISSING",
                message="No usable sourced surface location (easting/northing or latitude/"
                "longitude); the wellbore is unlocated. Not a blocker; it is excluded from "
                "georeferenced calculations.",
                wellbore_id=wellbore_id,
            )
        )
    if any(x.validated and x.survey_status == "unstated" for x in sets):
        warnings.append(
            GateReason(
                code="SURVEY_STATUS_UNSTATED",
                message="The source does not state whether the survey is planned or as-built; "
                "it is used as stated-unknown, never inferred from the file name.",
                wellbore_id=wellbore_id,
            )
        )
    if {x.survey_status for x in sets} >= {"planned", "as_built"}:
        warnings.append(
            GateReason(
                code="TRAJECTORY_PLANNED_AND_AS_BUILT_SEPARATE",
                message="Planned and as-built surveys both exist; they are kept separate.",
                wellbore_id=wellbore_id,
            )
        )
    gate = WellboreGate(
        well_id=well_id,
        wellbore_id=wellbore_id,
        wellbore_name=name,
        trajectory_validated=validated,
        trajectory_sets=sets,
        unmet=unmet,
        location_state="located" if located else "unlocated",
        unlocated=not located,
        warnings=warnings,
    )

    categories: list[CategoryExposure] = []
    for category in rules.CATEGORIES:
        groups = by_cat_groups.get(category, [])
        count = sum(g.record_count for g in groups)
        conflicting = sum(g.validation_counts.get("conflicting", 0) for g in groups)
        fs = findings_by_cat.get(category, [])
        reasons: list[str] = []
        if not groups and not proposal_total.get(category):
            reasons.append("NO_RECORDS")
        if category == "trajectory" and not validated:
            reasons.append("NO_VALIDATED_TRAJECTORY")
        if category == "surface_location" and not located:
            reasons.append("UNLOCATED")
        capped = fs[:MAX_FINDINGS_PER_CATEGORY]
        categories.append(
            CategoryExposure(
                category=category,
                present=bool(groups) or bool(proposal_total.get(category)),
                record_count=count,
                conflicting_record_count=conflicting,
                groups=groups,
                proposals=proposals.get(category, []),
                proposal_total=proposal_total.get(category, 0),
                accepted_proposal_count=accepted_count.get(category, 0),
                conflicts=[f for f in capped if f.kind == "conflict"],
                gaps=[f for f in capped if f.kind == "gap"],
                findings=[f for f in capped if f.kind == "finding"],
                findings_total=len(fs),
                findings_truncated=len(fs) > len(capped),
                proposals_truncated=proposal_total.get(category, 0)
                > len(proposals.get(category, [])),
                gap_reasons=reasons,
            )
        )
    return WellboreExposure(
        project_id=project_id,
        well_id=well_id,
        wellbore_id=wellbore_id,
        wellbore_name=name,
        categories=categories,
        gate=gate,
    )


def build_gate(
    project_id: UUID, wellbores: list[WellboreGate], resolved_current: bool
) -> StartGate:
    qualifying = [w.wellbore_id for w in wellbores if w.trajectory_validated]
    conditions = [
        GateCondition(
            code="WELLBORE_IDENTIFIED",
            met=bool(wellbores),
            message="At least one well and wellbore is identified."
            if wellbores
            else "No well and wellbore has been identified yet.",
        ),
        GateCondition(
            code="VALIDATED_TRAJECTORY",
            met=bool(qualifying),
            message="At least one wellbore has a validated trajectory."
            if qualifying
            else "No wellbore has a validated trajectory.",
        ),
    ]
    unmet: list[GateReason] = []
    if not wellbores:
        unmet.append(
            GateReason(
                code="NO_WELLBORE_IDENTIFIED",
                message="No well and wellbore has been identified yet.",
            )
        )
    elif not qualifying:
        unmet.append(
            GateReason(
                code="NO_VALIDATED_TRAJECTORY",
                message="No wellbore has a validated trajectory; see the per-wellbore reasons.",
            )
        )
    warnings = [w for gate in wellbores for w in gate.warnings if gate.trajectory_validated]
    if not resolved_current:
        warnings.append(
            GateReason(
                code="IDENTITY_NOT_CURRENT",
                message="Stored identities do not match the current extraction output; "
                "re-run identity resolution.",
            )
        )
    return StartGate(
        project_id=project_id,
        gate_version=rules.GATE_VERSION,
        can_start=all(c.met for c in conditions),
        conditions=conditions,
        unmet=unmet,
        warnings=warnings,
        qualifying_wellbore_ids=qualifying,
        wellbores=wellbores,
    )


def project_exposure(session: Session, project_id: UUID) -> ProjectExposure:
    listing = identity_service.listing(session, project_id)  # verifies the project
    wells: list[WellExposure] = []
    gates: list[WellboreGate] = []
    for w in listing.wells:
        bores = []
        for b in w.wellbores:
            e = wellbore_exposure(session, project_id, w.well_id, b.wellbore_id, b.name)
            bores.append(e)
            gates.append(e.gate)
        wells.append(WellExposure(well_id=w.well_id, name=w.name, wellbores=bores))
    return ProjectExposure(
        project_id=project_id,
        resolver_version=RESOLVER_VERSION,
        resolved_current=listing.resolved_current,
        unresolved_record_count=listing.unresolved_record_count,
        wells=wells,
        gate=build_gate(project_id, gates, listing.resolved_current),
    )


def start_gate(session: Session, project_id: UUID) -> StartGate:
    return project_exposure(session, project_id).gate


def one_wellbore(session: Session, project_id: UUID, wellbore_id: UUID) -> WellboreExposure:
    identity_service.require_project(session, project_id)
    row = session.execute(
        text("SELECT well_id, name FROM wellbore WHERE project_id = :p AND wellbore_id = :w"),
        {"p": project_id, "w": wellbore_id},
    ).first()
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "wellbore not found", 404)
    return wellbore_exposure(session, project_id, row.well_id, wellbore_id, row.name)
