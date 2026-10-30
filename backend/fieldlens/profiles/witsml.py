"""WITSML 1.4.1.x native profiles: trajectory, tubular, BHA run and wellbore geometry.

Content decides the profile (root element ``trajectorys``/``tubulars``/``bhaRuns``/
``wbGeometrys`` in a WITSML namespace); filenames and upload categories are only hints.
Every attribute carries its own XML element path (with source uids), original text and unit.
Nothing is converted, defaulted or zero-filled; gaps become findings."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .common import event_time, quantity_attr, snake, text_attr, well_key, wellbore_suffix
from .safexml import Node, parse_tree
from .types import (
    ASSEMBLY_TYPE_MISMATCH,
    DIMENSION_CONFLICT,
    HISTORY_INCOMPLETE,
    IDENTITY_MISMATCH,
    INTERVAL_CONFLICT,
    MISSING_REFERENCE,
    MISSING_UNIT,
    SUSPICIOUS_VALUE,
    TEMPORAL_AMBIGUITY,
    UNKNOWN_CODE,
    UNSUPPORTED_FORMAT,
    Attr,
    CoverageOut,
    Finding,
    Locator,
    ParseContext,
    ProfileError,
    ProfileOutput,
    Rec,
)

WITSML_NS_MARK = "witsml.org/schemas/1series"
SUPPORTED_VERSION_PREFIXES = ("1.3.1", "1.4.1")

# Elements that are measurements: a missing ``uom`` is a unit gap, not "dimensionless".
MEASURED = frozenset(
    "md tvd incl azi dispNs dispEw vertSect dls mdMn mdMx mdTop mdBottom tvdTop tvdBottom "
    "idSection odSection id od len lenJointAv wtPerLen tensYield gapAir depthWaterMean "
    "idFishneck odFishneck magDeclUsed gridCorUsed aziVertSect".split()
)
_SKIP_GROUPS = frozenset({"rawData", "corUsed", "commonData", "customData"})

# Reviewed (seen-in-source or standard) code lists; anything else is flagged, never coerced.
TRAJ_STATION_TYPES = frozenset(
    {
        "tie in point",
        "magnetic MWD",
        "gyro MWD",
        "unknown",
        "interpolation",
        "extrapolation",
        "azimuth on plane",
        "MWD",
        "gyro",
        "target",
        "tool",
    }
)
TRAJ_STATUS = frozenset({"position", "unknown", "projected"})
TUBULAR_ASSY_TYPES = frozenset({"drilling", "completion", "production", "casing", "liner", "other"})
COMPLETION_COMPONENTS = frozenset(
    {"tubing", "packer", "casing", "liner", "completion string", "safety valve", "nipple", "gauge"}
)
DRILLING_COMPONENTS = frozenset(
    {
        "drill pipe",
        "drill collar",
        "heavy weight drill pipe",
        "bit",
        "stabilizer string",
        "stabilizer",
        "mill taper",
        "mill casing cutting",
        "running tool",
        "spear",
        "sub-crossover",
        "reamer",
        "motor",
        "mwd",
        "jar",
    }
)
TUBULAR_COMP_TYPES = DRILLING_COMPONENTS | COMPLETION_COMPONENTS | {"other"}
HOLE_TYPES = frozenset({"casing", "riser", "open hole", "liner", "tubing", "conductor", "other"})

ROOT_KIND = {
    "trajectorys": "trajectory",
    "tubulars": "tubular",
    "bhaRuns": "bha_run",
    "wbGeometrys": "wb_geometry",
}


def _locator(
    ctx_ns: str | None, path: str, uids: list[str], attribute: str | None = None
) -> Locator:
    loc: Locator = {"kind": "xml", "element_path": path, "source_uids": [u for u in uids if u]}
    if ctx_ns:
        loc["namespace_uri"] = ctx_ns
    if attribute:
        loc["attribute_name"] = attribute
    return loc


def sniff_root(path: Path) -> tuple[str, str | None, str | None] | None:
    """(root local name, namespace, version) from the first start tag, or None. Never a full
    parse: a bounded head is scanned, DOCTYPE is not interpreted."""
    from xml.parsers import expat

    with path.open("rb") as handle:
        head = handle.read(8192)
    parser = expat.ParserCreate(namespace_separator="}")
    found: list[tuple[str, str | None, str | None]] = []

    class _Stop(Exception):
        pass

    def start(name: str, attrs: dict[str, str]) -> None:
        ns, _, local = name.rpartition("}") if "}" in name else (None, "", name)
        found.append((local, ns or None, attrs.get("version")))
        raise _Stop

    parser.StartElementHandler = start
    parser.StartDoctypeDeclHandler = lambda *a: (_ for _ in ()).throw(_Stop())
    try:
        parser.Parse(head, False)
    except (_Stop, expat.ExpatError):
        pass
    return found[0] if found else None


class _Builder:
    def __init__(self, ctx: ParseContext, ns: str | None, root_tag: str) -> None:
        self.ctx = ctx
        self.ns = ns
        self.root_tag = root_tag
        self.records: list[Rec] = []
        self.findings: list[Finding] = []

    # -- helpers --------------------------------------------------------------------------
    def add(self, rec: Rec) -> Rec:
        rec.ordinal = len(self.records)
        self.records.append(rec)
        return rec

    def loc(self, path: str, uids: list[str], attribute: str | None = None) -> Locator:
        return _locator(self.ns, path, uids, attribute)

    def simple_attrs(
        self,
        node: Node,
        kind: str,
        path: str,
        uids: list[str],
        *,
        skip: frozenset[str] = frozenset(),
        sub_records: frozenset[str] = frozenset(),
    ) -> list[Attr]:
        out: list[Attr] = []
        for child in node.children:
            if child.tag in _SKIP_GROUPS or child.tag in sub_records or child.tag in skip:
                continue
            cpath = f"{path}/{child.tag}"
            if child.children:  # nested group: flatten one level, keep the path
                for grand in child.children:
                    if grand.children:
                        continue
                    out.append(
                        self._leaf(
                            grand, f"{kind}.{snake(child.tag)}", f"{cpath}/{grand.tag}", uids
                        )
                    )
                continue
            out.append(self._leaf(child, kind, cpath, uids))
        return out

    def _leaf(self, node: Node, kind: str, path: str, uids: list[str]) -> Attr:
        key = f"{kind}.{snake(node.tag)}"
        text = node.text
        loc = self.loc(path, uids)
        uom = node.attrs.get("uom")
        ref = node.attrs.get("datum")
        if node.tag in MEASURED or uom is not None:
            return quantity_attr(
                key, loc, text, uom, reference=ref, unit_required=node.tag in MEASURED
            )
        if node.attrs.get("uidRef") is not None:
            attr = text_attr(key, loc, text)
            attr.reference = f"uidRef={node.attrs['uidRef']}"
            return attr
        return text_attr(key, loc, text)

    def common(self, obj: Node, path: str, uids: list[str]) -> dict[str, Any]:
        cd = obj.find("commonData")
        info: dict[str, Any] = {}
        if cd is not None:
            created = cd.value("dTimCreation")
            changed = cd.value("dTimLastChange")
            info = {
                "report_time": event_time(created, "commonData/dTimCreation"),
                "last_change": changed,
                "source_name": cd.value("sourceName"),
                "item_state": cd.value("itemState"),
            }
        return info

    def subject(self, obj: Node, uids: list[str]) -> dict[str, Any]:
        name_well = obj.value("nameWell")
        name_bore = obj.value("nameWellbore")
        return {
            "well_name": name_well,
            "wellbore_name": name_bore,
            "well_uid": obj.attrs.get("uidWell"),
            "wellbore_uid": obj.attrs.get("uidWellbore"),
            "object_uid": obj.attrs.get("uid"),
            "well_key": well_key(name_well) or well_key(name_bore),
            "wellbore_suffix": wellbore_suffix(name_bore),
        }

    def identity_checks(self, subject: dict[str, Any], rec: Rec, label: str) -> None:
        wk, bk = well_key(subject["well_name"]), well_key(subject["wellbore_name"])
        if not subject["well_name"] or not subject["wellbore_name"]:
            self.findings.append(
                Finding(
                    IDENTITY_MISMATCH,
                    "warning",
                    f"{label}: well or wellbore name is missing; identity is not established.",
                    f"identity_missing:{rec.ordinal}",
                    ["subject.well_name"],
                    [rec.ordinal],
                    [rec.locator],
                    ["claim_acceptance"],
                )
            )
        elif wk and bk and wk != bk:
            self.findings.append(
                Finding(
                    IDENTITY_MISMATCH,
                    "error",
                    f"{label}: well name resolves to {wk} but wellbore name to {bk}.",
                    f"identity_mismatch:{rec.ordinal}",
                    ["subject.well_name", "subject.wellbore_name"],
                    [rec.ordinal],
                    [rec.locator],
                    ["claim_acceptance", "placement"],
                )
            )

    def finish(self, detail: dict[str, Any]) -> ProfileOutput:
        n = len(self.records)
        return ProfileOutput(
            self.records,
            self.findings,
            CoverageOut("record", n, n),
            "succeeded",
            detail,
        )


def _objects(root: Node, tag: str) -> list[Node]:
    return [c for c in root.children if c.tag == tag]


# --- trajectory ------------------------------------------------------------------------------


def _parse_trajectory(b: _Builder, root: Node) -> None:
    for obj in _objects(root, "trajectory"):
        uid = obj.attrs.get("uid", "")
        path = f"/{root.tag}/trajectory[@uid='{uid}']"
        uids = [obj.attrs.get("uidWell", ""), obj.attrs.get("uidWellbore", ""), uid]
        subject = b.subject(obj, uids)
        info = b.common(obj, path, uids)
        head = b.add(
            Rec(
                "trajectory",
                subject,
                b.loc(path, uids),
                b.simple_attrs(
                    obj, "trajectory", path, uids, sub_records=frozenset({"trajectoryStation"})
                ),
                event_time(obj.value("dTimTrajStart"), "dTimTrajStart"),
                info.get("report_time"),
            )
        )
        b.identity_checks(subject, head, "trajectory")
        stations = obj.findall("trajectoryStation")
        datum_seen = False
        md_vs_tvd_equal: list[int] = []
        bad_tvd: list[int] = []
        non_monotonic: list[int] = []
        prev_md: float | None = None
        types: Counter[str] = Counter()
        for st in stations:
            suid = st.attrs.get("uid", "")
            spath = f"{path}/trajectoryStation[@uid='{suid}']"
            rec = b.add(
                Rec(
                    "trajectory_station",
                    subject,
                    b.loc(spath, uids + [suid]),
                    b.simple_attrs(st, "trajectory_station", spath, uids + [suid]),
                    event_time(st.value("dTimStn"), "dTimStn"),
                    info.get("report_time"),
                )
            )
            md, tvd, inc = (rec.attr(f"trajectory_station.{k}") for k in ("md", "tvd", "incl"))
            for a in (md, tvd):
                if a is not None and a.reference:
                    datum_seen = True
            t = (st.value("typeTrajStation") or "").strip()
            types[t] += 1
            if md and md.number is not None:
                if prev_md is not None and md.number <= prev_md:
                    non_monotonic.append(rec.ordinal)
                prev_md = md.number
                if tvd and tvd.number is not None:
                    if tvd.number > md.number + 1e-6:
                        bad_tvd.append(rec.ordinal)
                    elif (
                        md.number > 0
                        and abs(md.number - tvd.number) < 1e-9
                        and inc
                        and inc.number is not None
                        and inc.number >= 1.0
                    ):
                        md_vs_tvd_equal.append(rec.ordinal)
        _station_findings(b, head, stations, datum_seen, md_vs_tvd_equal, bad_tvd, non_monotonic)
        for code in sorted(set(types) - TRAJ_STATION_TYPES - {""}):
            b.findings.append(
                Finding(
                    UNKNOWN_CODE,
                    "info",
                    f"typeTrajStation '{code}' is not in the profile's reviewed code list; "
                    "kept verbatim, not coerced.",
                    f"unknown_station_type:{head.ordinal}:{code}",
                    ["trajectory_station.type_traj_station"],
                    [head.ordinal],
                    [head.locator],
                )
            )
        if not head.effective_time:
            b.findings.append(
                Finding(
                    TEMPORAL_AMBIGUITY,
                    "warning",
                    "trajectory has no start time; its effective period is unknown.",
                    f"no_effective_time:{head.ordinal}",
                    ["trajectory.d_tim_traj_start"],
                    [head.ordinal],
                    [head.locator],
                    ["temporal_state"],
                )
            )


def _station_findings(
    b: _Builder,
    head: Rec,
    stations: list[Node],
    datum_seen: bool,
    equal: list[int],
    bad_tvd: list[int],
    non_monotonic: list[int],
) -> None:
    if stations and not datum_seen:
        b.findings.append(
            Finding(
                MISSING_REFERENCE,
                "warning",
                "MD/TVD carry no datum reference in this document, so their zero point "
                "(rotary table, mean sea level, ...) is not established.",
                f"missing_depth_reference:{head.ordinal}",
                ["trajectory_station.md", "trajectory_station.tvd"],
                [head.ordinal],
                [head.locator],
                ["placement", "calculation"],
            )
        )
    aziref = head.attr("trajectory.azi_ref")
    if aziref is None or aziref.text is None:
        b.findings.append(
            Finding(
                MISSING_REFERENCE,
                "warning",
                "azimuth reference (aziRef: true/grid north) is absent.",
                f"missing_azimuth_reference:{head.ordinal}",
                ["trajectory.azi_ref"],
                [head.ordinal],
                [head.locator],
                ["calculation", "placement"],
            )
        )
    b.findings.append(
        Finding(
            MISSING_REFERENCE,
            "warning",
            "no coordinate reference system or surface location in a WITSML trajectory object; "
            "no CRS is assumed.",
            f"missing_crs:{head.ordinal}",
            ["trajectory.crs"],
            [head.ordinal],
            [head.locator],
            ["placement"],
        )
    )
    if bad_tvd:
        b.findings.append(
            Finding(
                SUSPICIOUS_VALUE,
                "error",
                f"{len(bad_tvd)} station(s) have TVD greater than MD, which is geometrically "
                "impossible; affected stations are marked invalid.",
                f"tvd_gt_md:{head.ordinal}",
                ["trajectory_station.tvd", "trajectory_station.md"],
                bad_tvd[:50],
                [b.records[o].locator for o in bad_tvd[:5]],
                ["calculation", "placement"],
            )
        )
        for o in bad_tvd:
            _mark(b.records[o], ("trajectory_station.tvd",), "invalid")
    if equal:
        b.findings.append(
            Finding(
                SUSPICIOUS_VALUE,
                "warning",
                f"{len(equal)} inclined station(s) have TVD exactly equal to MD; TVD is "
                "suspect and not used as a valid claim.",
                f"md_equals_tvd:{head.ordinal}",
                ["trajectory_station.tvd", "trajectory_station.md"],
                equal[:50],
                [b.records[o].locator for o in equal[:5]],
                ["calculation", "placement"],
            )
        )
        for o in equal:
            _mark(b.records[o], ("trajectory_station.tvd",), "conflicting")
    if non_monotonic:
        b.findings.append(
            Finding(
                SUSPICIOUS_VALUE,
                "warning",
                f"MD is not strictly increasing at {len(non_monotonic)} station(s); document "
                "order is kept, nothing is re-sorted.",
                f"md_not_increasing:{head.ordinal}",
                ["trajectory_station.md"],
                non_monotonic[:50],
                [b.records[o].locator for o in non_monotonic[:5]],
                ["calculation"],
            )
        )


def _mark(rec: Rec, keys: tuple[str, ...], state: Any) -> None:
    for a in rec.attrs:
        if a.key in keys:
            a.validation_state = state


# --- tubular ---------------------------------------------------------------------------------


def _parse_tubular(b: _Builder, root: Node) -> None:
    for obj in _objects(root, "tubular"):
        uid = obj.attrs.get("uid", "")
        path = f"/{root.tag}/tubular[@uid='{uid}']"
        uids = [obj.attrs.get("uidWell", ""), obj.attrs.get("uidWellbore", ""), uid]
        subject = b.subject(obj, uids)
        info = b.common(obj, path, uids)
        head = b.add(
            Rec(
                "tubular_assembly",
                subject,
                b.loc(path, uids),
                b.simple_attrs(
                    obj, "tubular_assembly", path, uids, sub_records=frozenset({"tubularComponent"})
                ),
                None,
                info.get("report_time"),
            )
        )
        b.identity_checks(subject, head, "tubular")
        assy = (obj.value("typeTubularAssy") or "").strip()
        comps = obj.findall("tubularComponent")
        types: list[str] = []
        zero_placeholders: list[int] = []
        seq_seen: Counter[str] = Counter()
        dim_conflicts: list[int] = []
        for comp in comps:
            cuid = comp.attrs.get("uid", "")
            cpath = f"{path}/tubularComponent[@uid='{cuid}']"
            rec = b.add(
                Rec(
                    "tubular_component",
                    subject,
                    b.loc(cpath, uids + [cuid]),
                    b.simple_attrs(comp, "tubular_component", cpath, uids + [cuid]),
                    None,
                    info.get("report_time"),
                )
            )
            ctype = (comp.value("typeTubularComp") or "").strip()
            types.append(ctype)
            seq_seen[(comp.value("sequence") or "").strip()] += 1
            for key in ("tens_yield", "od", "id", "len"):
                a = rec.attr(f"tubular_component.{key}")
                if a is not None and a.number == 0.0:
                    a.validation_state = "invalid"
                    zero_placeholders.append(rec.ordinal)
            idv, odv = (rec.attr(f"tubular_component.{k}") for k in ("id", "od"))
            if idv and odv and idv.number is not None and odv.number is not None:
                if idv.number > odv.number:
                    dim_conflicts.append(rec.ordinal)
        _tubular_findings(b, head, assy, types, zero_placeholders, seq_seen, dim_conflicts)


def _tubular_findings(
    b: _Builder,
    head: Rec,
    assy: str,
    types: list[str],
    zero_placeholders: list[int],
    seq_seen: Counter[str],
    dim_conflicts: list[int],
) -> None:
    if not assy:
        b.findings.append(
            Finding(
                MISSING_REFERENCE,
                "warning",
                "tubular assembly type (drilling/completion) is absent; it is not inferred.",
                f"missing_assembly_type:{head.ordinal}",
                ["tubular_assembly.type_tubular_assy"],
                [head.ordinal],
                [head.locator],
                ["claim_acceptance"],
            )
        )
    elif assy not in TUBULAR_ASSY_TYPES:
        b.findings.append(
            Finding(
                UNKNOWN_CODE,
                "info",
                f"typeTubularAssy '{assy}' is not in the reviewed code list; kept verbatim.",
                f"unknown_assembly_type:{head.ordinal}",
                ["tubular_assembly.type_tubular_assy"],
                [head.ordinal],
                [head.locator],
            )
        )
    wrong = (
        [t for t in types if t in COMPLETION_COMPONENTS]
        if assy == "drilling"
        else [t for t in types if t in DRILLING_COMPONENTS]
        if assy == "completion"
        else []
    )
    if wrong:
        b.findings.append(
            Finding(
                ASSEMBLY_TYPE_MISMATCH,
                "warning",
                f"assembly is typed '{assy}' but contains {sorted(set(wrong))} components; "
                "drilling and completion equipment are not merged.",
                f"assembly_type_mismatch:{head.ordinal}",
                ["tubular_assembly.type_tubular_assy", "tubular_component.type_tubular_comp"],
                [head.ordinal],
                [head.locator],
                ["claim_acceptance", "physical_geometry"],
            )
        )
    for code in sorted(set(types) - TUBULAR_COMP_TYPES - {""}):
        b.findings.append(
            Finding(
                UNKNOWN_CODE,
                "info",
                f"typeTubularComp '{code}' is not in the profile's reviewed code list; kept "
                "verbatim, not coerced.",
                f"unknown_component_type:{head.ordinal}:{code}",
                ["tubular_component.type_tubular_comp"],
                [head.ordinal],
                [head.locator],
            )
        )
    if assy in ("drilling", "") and types:
        b.findings.append(
            Finding(
                HISTORY_INCOMPLETE,
                "info",
                "this assembly is a drilling/BHA string, not installed completion equipment; "
                "it supplies no completion evidence.",
                f"drilling_not_completion:{head.ordinal}",
                ["tubular_assembly.type_tubular_assy"],
                [head.ordinal],
                [head.locator],
                ["claim_acceptance"],
            )
        )
    if zero_placeholders:
        b.findings.append(
            Finding(
                SUSPICIOUS_VALUE,
                "warning",
                f"{len(set(zero_placeholders))} component(s) carry a literal 0 for a strength or "
                "dimension (e.g. tensYield 0 Pa); zero is a placeholder, not a measurement, and "
                "is marked invalid.",
                f"zero_placeholder:{head.ordinal}",
                ["tubular_component.tens_yield"],
                sorted(set(zero_placeholders))[:50],
                [b.records[o].locator for o in sorted(set(zero_placeholders))[:5]],
                ["physical_geometry", "calculation"],
            )
        )
    dup = sorted(s for s, n in seq_seen.items() if n > 1 and s)
    if dup:
        b.findings.append(
            Finding(
                INTERVAL_CONFLICT,
                "warning",
                f"component sequence number(s) {dup} occur more than once; string order is "
                "ambiguous.",
                f"duplicate_sequence:{head.ordinal}",
                ["tubular_component.sequence"],
                [head.ordinal],
                [head.locator],
                ["physical_geometry"],
            )
        )
    if dim_conflicts:
        b.findings.append(
            Finding(
                DIMENSION_CONFLICT,
                "warning",
                f"{len(dim_conflicts)} component(s) have an inner diameter larger than the "
                "outer diameter.",
                f"id_gt_od:{head.ordinal}",
                ["tubular_component.id", "tubular_component.od"],
                dim_conflicts[:50],
                [b.records[o].locator for o in dim_conflicts[:5]],
                ["physical_geometry"],
            )
        )


# --- BHA run ---------------------------------------------------------------------------------


def _parse_bha_run(b: _Builder, root: Node) -> None:
    for obj in _objects(root, "bhaRun"):
        uid = obj.attrs.get("uid", "")
        path = f"/{root.tag}/bhaRun[@uid='{uid}']"
        uids = [obj.attrs.get("uidWell", ""), obj.attrs.get("uidWellbore", ""), uid]
        subject = b.subject(obj, uids)
        info = b.common(obj, path, uids)
        attrs = b.simple_attrs(obj, "bha_run", path, uids)
        for a in attrs:
            if a.key == "bha_run.tubular" and a.reference is None:
                a.reference = None
        rec = b.add(
            Rec(
                "bha_run",
                subject,
                b.loc(path, uids),
                attrs,
                event_time(obj.value("dTimStart"), "dTimStart"),
                info.get("report_time"),
            )
        )
        b.identity_checks(subject, rec, "bhaRun")
        tub = rec.attr("bha_run.tubular")
        if tub is None or not (tub.reference or "").startswith("uidRef="):
            b.findings.append(
                Finding(
                    HISTORY_INCOMPLETE,
                    "warning",
                    "BHA run has no tubular reference; its string composition is unknown.",
                    f"bha_without_tubular:{rec.ordinal}",
                    ["bha_run.tubular"],
                    [rec.ordinal],
                    [rec.locator],
                    ["claim_acceptance"],
                )
            )
        if rec.effective_time is None:
            b.findings.append(
                Finding(
                    TEMPORAL_AMBIGUITY,
                    "warning",
                    "BHA run has no start time (dTimStart); its effective time is unknown.",
                    f"bha_no_start:{rec.ordinal}",
                    ["bha_run.d_tim_start"],
                    [rec.ordinal],
                    [rec.locator],
                    ["temporal_state"],
                )
            )
        elif rec.effective_time.precision == "instant" and not rec.effective_time.timezone_known:
            b.findings.append(
                Finding(
                    TEMPORAL_AMBIGUITY,
                    "info",
                    "BHA run start time has no timezone designator.",
                    f"bha_tz:{rec.ordinal}",
                    ["bha_run.d_tim_start"],
                    [rec.ordinal],
                    [rec.locator],
                )
            )


# --- wellbore geometry -----------------------------------------------------------------------


def _parse_wb_geometry(b: _Builder, root: Node) -> None:
    for obj in _objects(root, "wbGeometry"):
        uid = obj.attrs.get("uid", "")
        path = f"/{root.tag}/wbGeometry[@uid='{uid}']"
        uids = [obj.attrs.get("uidWell", ""), obj.attrs.get("uidWellbore", ""), uid]
        subject = b.subject(obj, uids)
        info = b.common(obj, path, uids)
        report = event_time(obj.value("dTimReport"), "dTimReport")
        head = b.add(
            Rec(
                "wb_geometry",
                subject,
                b.loc(path, uids),
                b.simple_attrs(
                    obj, "wb_geometry", path, uids, sub_records=frozenset({"wbGeometrySection"})
                ),
                None,  # dTimReport is a report time, never an effective/installation time
                report or info.get("report_time"),
            )
        )
        b.identity_checks(subject, head, "wbGeometry")
        sections: list[Rec] = []
        for sec in obj.findall("wbGeometrySection"):
            suid = sec.attrs.get("uid", "")
            spath = f"{path}/wbGeometrySection[@uid='{suid}']"
            sections.append(
                b.add(
                    Rec(
                        "wb_geometry_section",
                        subject,
                        b.loc(spath, uids + [suid]),
                        b.simple_attrs(sec, "wb_geometry_section", spath, uids + [suid]),
                        None,
                        report,
                    )
                )
            )
        _geometry_findings(b, head, sections)


def _num(rec: Rec, key: str) -> float | None:
    a = rec.attr(f"wb_geometry_section.{key}")
    return None if a is None else a.number


def _geometry_findings(b: _Builder, head: Rec, sections: list[Rec]) -> None:
    b.findings.append(
        Finding(
            TEMPORAL_AMBIGUITY,
            "info",
            "wbGeometry gives only a report time; when each section was installed is not "
            "stated, so no installed-state date is derived.",
            f"geometry_no_effective_time:{head.ordinal}",
            ["wb_geometry.d_tim_report"],
            [head.ordinal],
            [head.locator],
            ["temporal_state"],
        )
    )
    inverted: list[int] = []
    for s in sections:
        top, bot = _num(s, "md_top"), _num(s, "md_bottom")
        if top is not None and bot is not None and top >= bot:
            inverted.append(s.ordinal)
    if inverted:
        b.findings.append(
            Finding(
                INTERVAL_CONFLICT,
                "error",
                f"{len(inverted)} section(s) have mdTop >= mdBottom.",
                f"section_inverted:{head.ordinal}",
                ["wb_geometry_section.md_top", "wb_geometry_section.md_bottom"],
                inverted,
                [b.records[o].locator for o in inverted[:5]],
                ["physical_geometry", "placement"],
            )
        )
    spans = sorted(
        (s for s in sections if _num(s, "md_top") is not None and _num(s, "md_bottom") is not None),
        key=lambda s: (_num(s, "md_top") or 0.0, _num(s, "md_bottom") or 0.0),
    )
    overlaps = [
        (a, c)
        for a, c in zip(spans, spans[1:], strict=False)
        if (_num(c, "md_top") or 0.0) < (_num(a, "md_bottom") or 0.0) - 1e-6
        and (_num(a, "md_top") or 0.0) != (_num(c, "md_top") or 0.0)
    ]
    # Casing sits inside the previous hole/riser, so only same-type overlaps are conflicts.
    same_type = [
        (a, c)
        for a, c in overlaps
        if (a.attr("wb_geometry_section.type_hole_casing") or Attr("", {})).text
        == (c.attr("wb_geometry_section.type_hole_casing") or Attr("", {})).text
    ]
    if same_type:
        b.findings.append(
            Finding(
                INTERVAL_CONFLICT,
                "warning",
                f"{len(same_type)} pair(s) of same-type sections overlap in MD.",
                f"section_overlap:{head.ordinal}",
                ["wb_geometry_section.md_top", "wb_geometry_section.md_bottom"],
                [a.ordinal for a, _ in same_type][:50],
                [a.locator for a, _ in same_type[:5]],
                ["physical_geometry"],
            )
        )
    for s in sections:
        code = ((s.attr("wb_geometry_section.type_hole_casing") or Attr("", {})).text or "").strip()
        if code and code not in HOLE_TYPES:
            b.findings.append(
                Finding(
                    UNKNOWN_CODE,
                    "info",
                    f"typeHoleCasing '{code}' is not in the reviewed code list; kept verbatim.",
                    f"unknown_hole_type:{s.ordinal}:{code}",
                    ["wb_geometry_section.type_hole_casing"],
                    [s.ordinal],
                    [s.locator],
                )
            )
    deep = [s for s in sections if (_num(s, "md_bottom") or 0.0) >= 1000.0]
    equal = [
        s
        for s in sections
        if _num(s, "md_bottom") is not None
        and _num(s, "tvd_bottom") is not None
        and abs((_num(s, "md_bottom") or 0.0) - (_num(s, "tvd_bottom") or 0.0)) < 1e-9
        and (_num(s, "md_top") or 0.0) == (_num(s, "tvd_top") or 0.0)
    ]
    if deep and len(equal) == len(sections) and sections:
        b.findings.append(
            Finding(
                SUSPICIOUS_VALUE,
                "warning",
                f"all {len(sections)} sections report TVD exactly equal to MD down to "
                f"{max(_num(s, 'md_bottom') or 0.0 for s in sections):g} m; a deviated well "
                "cannot have identical MD and TVD, so these TVD values are not valid claims "
                "(MD values are unaffected).",
                f"geometry_md_equals_tvd:{head.ordinal}",
                ["wb_geometry_section.tvd_top", "wb_geometry_section.tvd_bottom"],
                [s.ordinal for s in sections][:50],
                [s.locator for s in sections[:5]],
                ["calculation", "placement"],
            )
        )
        for s in sections:
            _mark(
                s, ("wb_geometry_section.tvd_top", "wb_geometry_section.tvd_bottom"), "conflicting"
            )
    md_bottom = head.attr("wb_geometry.md_bottom")
    if md_bottom is not None and md_bottom.number is not None and spans:
        deepest = max(_num(s, "md_bottom") or 0.0 for s in spans)
        if abs(deepest - md_bottom.number) > 1e-6:
            b.findings.append(
                Finding(
                    DIMENSION_CONFLICT,
                    "warning",
                    f"header mdBottom {md_bottom.number:g} differs from the deepest section "
                    f"bottom {deepest:g}; both kept.",
                    f"geometry_bottom_mismatch:{head.ordinal}",
                    ["wb_geometry.md_bottom", "wb_geometry_section.md_bottom"],
                    [head.ordinal],
                    [head.locator],
                    ["physical_geometry"],
                )
            )
    b.findings.append(
        Finding(
            MISSING_REFERENCE,
            "info",
            "wbGeometry gives gapAir/depthWaterMean but no depth datum for md/tvd values.",
            f"geometry_no_datum:{head.ordinal}",
            ["wb_geometry_section.md_top", "wb_geometry_section.md_bottom"],
            [head.ordinal],
            [head.locator],
            ["placement"],
        )
    )


def _missing_unit_finding(b: _Builder) -> None:
    by_key: dict[str, list[int]] = {}
    for r in b.records:
        for a in r.attrs:
            if a.unit_status == "missing" and a.number is not None:
                by_key.setdefault(a.key, []).append(r.ordinal)
    for key, ords in sorted(by_key.items()):
        b.findings.append(
            Finding(
                MISSING_UNIT,
                "warning",
                f"{key} has a numeric value without a unit in {len(ords)} record(s); the unit is "
                "not assumed and the value is not normalized.",
                f"missing_unit:{key}",
                [key],
                ords[:50],
                [b.records[o].locator for o in ords[:5]],
                ["calculation"],
            )
        )


_PARSERS = {
    "trajectory": _parse_trajectory,
    "tubular": _parse_tubular,
    "bha_run": _parse_bha_run,
    "wb_geometry": _parse_wb_geometry,
}


class WitsmlProfile:
    """One profile instance per WITSML object kind (separate versions, shared code)."""

    families = ("xml",)
    method = "native_xml_expat"

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.name = f"witsml_{kind}"
        self.version = "1"

    def detect(self, path: Path, format_family: str, filename: str) -> bool:
        if format_family != "xml":
            return False
        root = sniff_root(path)
        return bool(
            root and root[1] and WITSML_NS_MARK in root[1] and ROOT_KIND.get(root[0]) == self.kind
        )

    def parse(self, path: Path, ctx: ParseContext) -> ProfileOutput:
        tree = parse_tree(path)
        version = tree.attrs.get("version") or ""
        if self.kind != ROOT_KIND.get(tree.tag) or not (tree.ns and WITSML_NS_MARK in tree.ns):
            raise ProfileError("profile_mismatch", "document root does not match the profile")
        b = _Builder(ctx, tree.ns, tree.tag)
        if not version.startswith(SUPPORTED_VERSION_PREFIXES):
            out = ProfileOutput(
                [],
                [
                    Finding(
                        UNSUPPORTED_FORMAT,
                        "error",
                        f"WITSML version '{version or 'absent'}' is not a reviewed version "
                        f"({', '.join(SUPPORTED_VERSION_PREFIXES)}); nothing was extracted.",
                        "unsupported_version",
                        locators=[b.loc(f"/{tree.tag}", [], "version")],
                        blocked=["claim_acceptance"],
                    )
                ],
                CoverageOut("record", 0, None, [], ["unsupported WITSML version"]),
                "failed",
                {"witsml_version": version},
            )
            return out
        _PARSERS[self.kind](b, tree)
        _missing_unit_finding(b)
        objects = _objects(
            tree, {"bha_run": "bhaRun", "wb_geometry": "wbGeometry"}.get(self.kind, self.kind)
        )
        out = b.finish({"witsml_version": version, "objects": len(objects)})
        if not objects:
            out.status = "partial"
            out.findings.append(
                Finding(
                    "EXTRACTION_PARTIAL",
                    "warning",
                    "document contains no objects of the expected type.",
                    "no_objects",
                    blocked=["claim_acceptance"],
                )
            )
            out.coverage = CoverageOut("record", 0, None, [], ["no objects found"])
        return out
