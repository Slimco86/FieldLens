"""WITSML + hostile-XML profile tests (IN-2, IN-6). Synthetic fixtures only (profile_support)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fieldlens.profiles import registry
from fieldlens.profiles.types import ProfileError
from fieldlens.profiles.witsml import WitsmlProfile
from tests.profile_support import CTX, codes, station, witsml, write


def _traj(tmp: Path, stations: str, head: str = "", name: str = "t.xml") -> Path:
    return write(tmp, name, witsml("trajectorys", "trajectory", head + stations))


def test_trajectory_preserves_units_references_and_locators(tmp_path: Path) -> None:
    head = (
        "<dTimTrajStart>2007-11-11T15:51:12.000Z</dTimTrajStart><aziRef>grid north</aziRef>"
        "<gridCorUsed uom='dega'>-0.95</gridCorUsed>"
    )
    path = _traj(
        tmp_path,
        station("S-0", "0", "0", "0", "0", "2007-11-11T15:51:12.000Z")
        + station("S-1", "100.5", "100.2", "5.5", "120", "2007-11-11T16:00:00.000Z"),
        head,
    )
    out = WitsmlProfile("trajectory").parse(path, CTX)
    assert out.status == "succeeded"
    stations = [r for r in out.records if r.kind == "trajectory_station"]
    assert [r.attr("trajectory_station.md").number for r in stations]  # type: ignore[union-attr] == [0.0, 100.5]
    md = stations[1].attr("trajectory_station.md")
    tvd = stations[1].attr("trajectory_station.tvd")
    assert md is not None and tvd is not None
    assert (md.unit, md.original_text) == ("m", "100.5")
    assert md.key != tvd.key, "MD and TVD stay distinct attributes"
    assert md.locator["kind"] == "xml"
    assert md.locator["element_path"].endswith("/trajectoryStation[@uid='S-1']/md")
    assert stations[1].subject["well_name"] == "15/9-F-99"
    assert stations[1].effective_time is not None
    assert stations[1].effective_time.precision == "instant"
    # No CRS / depth reference is stated: reported, never assumed.
    assert "MISSING_REFERENCE" in codes(out)
    blocked = {b for f in out.findings if f.code == "MISSING_REFERENCE" for b in f.blocked}
    assert {"placement"} <= blocked


def test_trajectory_conflicts_are_findings_not_corrections(tmp_path: Path) -> None:
    path = _traj(
        tmp_path,
        station("S-0", "0", "0", "0", "0") + station("S-1", "100", "120", "5", "10"),
    )
    out = WitsmlProfile("trajectory").parse(path, CTX)
    assert "SUSPICIOUS_VALUE" in codes(out)
    bad = next(f for f in out.findings if f.key.startswith("tvd_gt_md"))
    assert bad.severity == "error"
    tvd = out.records[-1].attr("trajectory_station.tvd")
    assert tvd is not None and tvd.number == 120.0, "the original TVD is kept"


def test_temporal_precision_is_preserved(tmp_path: Path) -> None:
    path = _traj(tmp_path, station("S-0", "0", "0", "0", "0", "2007-11-11"))
    out = WitsmlProfile("trajectory").parse(path, CTX)
    rec = out.records[-1]
    assert rec.effective_time is not None
    assert (rec.effective_time.literal, rec.effective_time.precision) == ("2007-11-11", "day")


def test_stations_without_time_report_temporal_ambiguity(tmp_path: Path) -> None:
    out = WitsmlProfile("trajectory").parse(
        _traj(tmp_path, station("S-0", "0", "0", "0", "0")), CTX
    )
    assert "TEMPORAL_AMBIGUITY" in codes(out)
    assert out.records[-1].effective_time is None


def test_tubular_zero_placeholders_and_drilling_assembly(tmp_path: Path) -> None:
    body = (
        "<typeTubularAssy>drilling</typeTubularAssy>"
        '<tubularComponent uid="C1"><typeTubularComp>tubing</typeTubularComp>'
        '<id uom="m">0.1</id><od uom="m">0.17</od><len uom="m">2054</len>'
        '<tensYield uom="Pa">0</tensYield></tubularComponent>'
    )
    out = WitsmlProfile("tubular").parse(
        write(tmp_path, "tub.xml", witsml("tubulars", "tubular", body)), CTX
    )
    got = codes(out)
    assert {"ASSEMBLY_TYPE_MISMATCH", "HISTORY_INCOMPLETE", "SUSPICIOUS_VALUE"} <= got
    comp = next(r for r in out.records if r.kind == "tubular_component")
    od = comp.attr("tubular_component.od")
    assert od is not None and (od.number, od.unit) == (0.17, "m")
    assert od.original_text == "0.17"


def test_wb_geometry_depth_reference_and_interval_conflict(tmp_path: Path) -> None:
    section = (
        '<wbGeometrySection uid="{u}"><typeHoleCasing>casing</typeHoleCasing>'
        '<mdTop uom="m">{a}</mdTop><mdBottom uom="m">{b}</mdBottom></wbGeometrySection>'
    )
    body = (
        "<mdBottom uom='m'>500</mdBottom>"
        + section.format(u="A", a=0, b=300)
        + section.format(u="B", a=250, b=500)
    )
    out = WitsmlProfile("wb_geometry").parse(
        write(tmp_path, "g.xml", witsml("wbGeometrys", "wbGeometry", body)), CTX
    )
    assert "INTERVAL_CONFLICT" in codes(out)
    assert "MISSING_REFERENCE" in codes(out)


def test_unreviewed_witsml_version_extracts_nothing(tmp_path: Path) -> None:
    xml = witsml("trajectorys", "trajectory", station("S-0", "0", "0", "0", "0")).replace(
        'version="1.4.1.1"', 'version="2.0"'
    )
    out = WitsmlProfile("trajectory").parse(write(tmp_path, "v.xml", xml), CTX)
    assert out.records == []
    assert "UNSUPPORTED_FORMAT" in codes(out)


def test_registry_selects_by_content_not_filename(tmp_path: Path) -> None:
    path = _traj(tmp_path, station("S-0", "0", "0", "0", "0"), name="production_report.csv")
    found = registry.detect(path, "xml", "production_report.csv")
    assert [p.name for p in found] == ["witsml_trajectory"]
    other = write(tmp_path, "survey.xml", "<root xmlns='urn:other'/>")
    assert registry.detect(other, "xml", "trajectory.xml") == []


# -- hostile input ---------------------------------------------------------------------------

XXE = (
    '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
    '<trajectorys xmlns="http://www.witsml.org/schemas/1series" version="1.4.1.1">'
    "<trajectory uid='1'><nameWell>&x;</nameWell></trajectory></trajectorys>"
)
LAUGHS = (
    '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
    '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
    '<trajectorys xmlns="http://www.witsml.org/schemas/1series" version="1.4.1.1">&lol3;'
    "</trajectorys>"
)


@pytest.mark.parametrize("payload", [XXE, LAUGHS], ids=["xxe", "billion_laughs"])
def test_dtd_and_entities_are_refused_without_expansion(tmp_path: Path, payload: str) -> None:
    path = write(tmp_path, "h.xml", payload)
    with pytest.raises(ProfileError) as err:
        WitsmlProfile("trajectory").parse(path, CTX)
    assert err.value.code == "xml_dtd_forbidden"
    assert "root:" not in err.value.message


def test_deep_nesting_and_malformed_xml_fail_cleanly(tmp_path: Path) -> None:
    deep = "<a>" * 5000 + "</a>" * 5000
    with pytest.raises(ProfileError) as err:
        WitsmlProfile("trajectory").parse(write(tmp_path, "d.xml", deep), CTX)
    assert err.value.code in {"xml_too_deep", "profile_mismatch"}
    with pytest.raises(ProfileError) as err2:
        WitsmlProfile("trajectory").parse(write(tmp_path, "m.xml", "<a><b></a>"), CTX)
    assert err2.value.code == "xml_malformed"
