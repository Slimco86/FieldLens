from __future__ import annotations

import random
import socket
from datetime import UTC, datetime
from typing import Any

import pytest
from fixture_t0_t6 import (
    DATUM,
    EXPECTED,
    JUST_BEFORE,
    TOL,
    WELLBORE,
    day_ev,
    depth,
    ev,
    fixture_records,
    t,
)

from fieldlens.engineering.perforation import PerforationHistory, derive_event_id


def build(records: list[dict[str, Any]]) -> PerforationHistory:
    return PerforationHistory.build(records, wellbore_id=WELLBORE, md_datum=DATUM)


def approx(a: float | None, b: float) -> bool:
    return a is not None and abs(a - b) <= TOL


# ----------------------------------------------------------------------------- PH-2
@pytest.mark.parametrize("day", range(7))
def test_replay_fixture_instants(day: int) -> None:
    total, open_, status = EXPECTED[day]
    state = build(fixture_records()).state_at(t(day), 1)
    assert state.status == "resolved"
    assert approx(state.total_length, total)
    assert approx(state.open_length, open_)
    assert state.wellbore_status == status
    assert state.unresolved == ()


@pytest.mark.parametrize("day", range(1, 7))
def test_boundary_just_before_event_returns_previous_state(day: int) -> None:
    history = build(fixture_records())
    before = history.state_at(t(day) - JUST_BEFORE, 1)
    total, open_, status = EXPECTED[day - 1]
    assert approx(before.total_length, total)
    assert approx(before.open_length, open_)
    assert before.wellbore_status == status
    # the event effect starts inclusively
    at = history.state_at(t(day), 1)
    assert (at.total_length, at.open_length) == (EXPECTED[day][0], EXPECTED[day][1])


def test_t1_envelope_is_30_but_unique_is_20_and_t4_t6_increments() -> None:
    history = build(fixture_records())
    assert approx(history.state_at(t(1), 1).total_length, 20.0)  # envelope 1000..1030 = 30
    assert approx(history.state_at(t(4), 1).total_length, 30.0)  # +10 unique from a 17 m op
    assert approx(history.state_at(t(6), 1).total_length, 30.0)  # 30 m op adds zero


def test_interval_flow_unknown_throughout_fixture() -> None:
    history = build(fixture_records())
    for day in range(7):
        assert {i.flow for i in history.state_at(t(day), 1).intervals} <= {"unknown"}


@pytest.mark.parametrize("seed", range(8))
def test_reordered_import_batches_give_identical_results(seed: int) -> None:
    records = fixture_records()
    reference = build(records)
    shuffled = records[:]
    random.Random(seed).shuffle(shuffled)  # noqa: S311
    other = build(shuffled)
    for day in range(7):
        assert other.state_at(t(day), 1) == reference.state_at(t(day), 1)


# ----------------------------------------------------------------------------- PH-3
def _single(records: list[dict[str, Any]], unit: str = "m") -> Any:
    base = [ev("b", "baseline", t(0), baseline_intervals=[]), *records]
    return build(base).state_at(t(5), 1, unit)


def test_union_overlap_reperforation_and_gaps() -> None:
    state = _single(
        [
            ev("p1", "perforate", t(1), lo=100, hi=110),
            ev("p2", "perforate", t(1), lo=105, hi=115),  # overlap
            ev("p3", "reperforate", t(2), lo=100, hi=115),  # reperforation adds nothing
            ev("p4", "perforate", t(1), lo=130, hi=140),  # gap 115..130 excluded
        ]
    )
    assert approx(state.total_length, 25.0)
    assert [(i.from_md, i.to_md) for i in state.intervals if i.perforated] == [
        (100.0, 115.0),
        (130.0, 140.0),
    ]


def test_ft_and_m_are_consistent() -> None:
    state_ft = _single([ev("p1", "perforate", t(1), lo=1000, hi=1100, unit="ft")], "ft")
    assert approx(state_ft.total_length, 100.0)
    state_m = _single([ev("p1", "perforate", t(1), lo=1000, hi=1100, unit="ft")], "m")
    assert approx(state_m.total_length, 30.48)


def test_exact_ft_m_boundary_does_not_leave_slivers() -> None:
    # 1000 ft == 304.8 m exactly, so adjacent ft/m intervals merge into one segment.
    state = _single(
        [
            ev("p1", "perforate", t(1), lo=1000, hi=1100, unit="ft"),
            ev("p2", "perforate", t(1), lo="335.28", hi="340", unit="m"),
        ]
    )
    assert approx(state.total_length, 30.48 + 4.72)
    assert len([i for i in state.intervals if i.perforated]) == 1


def test_tvd_span_never_substituted_for_md_length() -> None:
    rec = ev("p1", "perforate", t(1), lo=1000, hi=1010)
    rec["depth"]["tvd"] = {"from": 900, "to": 904, "unit": "m"}
    state = _single([rec])
    assert approx(state.total_length, 10.0)  # MD span, not the 4 m TVD span
    assert state.recorded_depths[0].recorded_tvd is not None
    assert state.recorded_depths[0].derived_tvd is None
    assert state.recorded_depths[0].from_value == "1000"


# ----------------------------------------------------------------------------- PH-5
def test_before_first_known_event_is_unknown_not_zero() -> None:
    history = build([ev("p1", "perforate", t(2), lo=100, hi=110)])
    state = history.state_at(t(1), 1)
    assert state.status == "unknown"
    assert state.total_length is None and state.open_length is None
    assert state.total_length_lower_bound is None


def test_no_baseline_gives_lower_bound_not_complete_total() -> None:
    state = build([ev("p1", "perforate", t(2), lo=100, hi=110)]).state_at(t(3), 1)
    assert state.status == "partial"
    assert state.total_length is None
    assert approx(state.total_length_lower_bound, 10.0)
    assert state.total_length_upper_bound is None
    assert "baseline_not_established" in state.limitations
    assert state.baseline_established is False


def test_complete_empty_baseline_is_verified_zero_only_from_its_instant() -> None:
    history = build([ev("b", "baseline", t(1), baseline_intervals=[])])
    assert history.state_at(t(0), 1).status == "unknown"
    state = history.state_at(t(1), 1)
    assert state.status == "resolved" and approx(state.total_length, 0.0)


def test_date_only_events_same_day_contradiction_not_ordered() -> None:
    records = [
        ev("b", "baseline", t(0), baseline_intervals=[]),
        ev("p", "perforate", t(1), lo=100, hi=120),
        ev("o", "open", t(1), lo=100, hi=120),
        day_ev("i", "isolate", "2000-01-03", lo=105, hi=110),
        day_ev("r", "reopen", "2000-01-03", lo=105, hi=110),
    ]
    history = build(records)
    state = history.state_at(t(4), 1)  # after the day: both happened, order unknown
    assert state.status == "conflicting"
    entries = [u for u in state.unresolved if u.axis == "access"]
    assert entries and entries[0].reason == "date_precision_order_unresolved"
    assert entries[0].md_intervals == ((105.0, 110.0),)
    assert entries[0].time_from == datetime(2000, 1, 3, tzinfo=UTC)
    assert entries[0].time_to == datetime(2000, 1, 4, tzinfo=UTC)
    assert set(entries[0].event_ids) == {"i", "r"}
    assert approx(state.total_length, 20.0)  # physical coverage is unaffected and exact
    assert state.open_length is None
    assert approx(state.open_length_lower_bound, 15.0)
    assert approx(state.open_length_upper_bound, 20.0)
    ambiguous = [i for i in state.intervals if "access" in i.unresolved_axes]
    assert [(i.from_md, i.to_md) for i in ambiguous] == [(105.0, 110.0)]
    # import order is irrelevant
    assert build(records[::-1]).state_at(t(4), 1) == state


def test_same_instant_contradiction_is_unresolved() -> None:
    records = [
        ev("b", "baseline", t(0), baseline_intervals=[]),
        ev("p", "perforate", t(1), lo=100, hi=120),
        ev("o", "open", t(2), lo=100, hi=120),
        ev("i", "isolate", t(2), lo=100, hi=120),
    ]
    state = build(records).state_at(t(2), 1)
    assert state.status == "conflicting"
    assert state.unresolved[0].reason == "same_time_order_unresolved"
    assert state.open_length is None
    assert state.total_length is not None and approx(state.total_length, 20.0)


def test_same_instant_non_conflicting_events_are_resolved() -> None:
    state = build(fixture_records()).state_at(t(1), 1)  # perforate+open at one instant
    assert state.status == "resolved"


def test_as_of_inside_date_only_window_is_unresolved() -> None:
    records = [
        ev("b", "baseline", t(0), baseline_intervals=[]),
        day_ev("p", "perforate", "2000-01-02", lo=100, hi=110),
    ]
    history = build(records)
    inside = history.state_at(datetime(2000, 1, 2, 12, tzinfo=UTC), 1)
    assert inside.status == "conflicting" and inside.total_length is None
    assert approx(inside.total_length_lower_bound, 0.0)
    assert approx(inside.total_length_upper_bound, 10.0)
    assert history.state_at(datetime(2000, 1, 1, 23, tzinfo=UTC), 1).total_length == 0.0
    assert approx(history.state_at(datetime(2000, 1, 3, tzinfo=UTC), 1).total_length, 10.0)


def test_day_window_honours_timezone() -> None:
    records = [
        ev("b", "baseline", t(0), baseline_intervals=[]),
        ev("o", "open", datetime(2000, 1, 1, 12, tzinfo=UTC), lo=100, hi=110),
        day_ev("p", "perforate", "2000-01-02", "America/New_York", lo=100, hi=110),
    ]
    history = build(records)
    # local day starts 05:00Z, ends 05:00Z next day
    assert history.state_at(datetime(2000, 1, 2, 4, 59, tzinfo=UTC), 1).status == "resolved"
    assert history.state_at(datetime(2000, 1, 2, 5, 0, tzinfo=UTC), 1).status == "conflicting"
    assert history.state_at(datetime(2000, 1, 3, 5, 0, tzinfo=UTC), 1).status == "resolved"


# ----------------------------------------------------------------------------- PH-7
def test_flow_state_is_not_assigned_to_every_interval() -> None:
    history = build(fixture_records())
    producing = history.state_at(t(1), 1)
    assert producing.wellbore_status == "producing"
    assert all(i.flow == "unknown" for i in producing.intervals)
    injecting = history.state_at(t(5), 1)
    assert all(i.flow == "unknown" for i in injecting.intervals)


def test_interval_flow_observation_is_scoped_to_its_interval() -> None:
    records = [
        *fixture_records(),
        ev("obs", "interval_flow", t(2), lo=1020, hi=1030, status="producing"),
    ]
    state = build(records).state_at(t(2), 1)
    flows = {(i.from_md, i.to_md): i.flow for i in state.intervals}
    assert flows[(1020.0, 1030.0)] == "producing"
    assert flows[(1000.0, 1005.0)] == "unknown"


def test_whole_well_shut_in_keeps_coverage_and_access() -> None:
    history = build(fixture_records())
    t2, t3 = history.state_at(t(2), 1), history.state_at(t(3), 1)
    assert t3.wellbore_status == "shut_in" and t2.wellbore_status == "producing"
    assert t3.total_length == t2.total_length
    assert t3.open_length == t2.open_length  # no interval silently closed
    assert [i.access for i in t3.intervals] == [i.access for i in t2.intervals]
    assert "isolated" in {i.access for i in t3.intervals}


def test_wellbore_status_with_interval_scope_is_rejected() -> None:
    rec = ev("s", "wellbore_status", t(1), lo=100, hi=110, status="shut_in")
    history = build([rec])
    assert [r.code for r in history.rejections] == ["scope_conflict"]


def test_interval_flow_without_interval_is_rejected() -> None:
    history = build([ev("f", "interval_flow", t(1), status="producing")])
    assert [r.code for r in history.rejections] == ["missing_depth"]


# ----------------------------------------------------------------------------- PH-9
@pytest.mark.parametrize(
    ("lo", "hi", "code"),
    [
        (-1, 10, "negative_depth"),
        (10, -1, "negative_depth"),
        (float("nan"), 10, "nonfinite_depth"),
        (10, float("inf"), "nonfinite_depth"),
        (20, 10, "reversed_depth"),
        (10, 10, "reversed_depth"),
        ("abc", 10, "malformed_depth"),
        (True, 10, "malformed_depth"),
        (None, 10, "malformed_depth"),
    ],
)
def test_invalid_md_bounds_fail_explicitly_without_corrupting_valid_history(
    lo: Any, hi: Any, code: str
) -> None:
    bad = ev("bad", "perforate", t(1), lo=1, hi=2)
    bad["depth"] = depth(lo, hi)
    history = build([ev("b", "baseline", t(0), baseline_intervals=[]), bad,
                     ev("good", "perforate", t(1), lo=100, hi=110),
                     ev("good-open", "open", t(1), lo=100, hi=110)])  # fmt: skip
    assert [(r.event_id, r.code) for r in history.rejections] == [("bad", code)]
    state = history.state_at(t(2), 1)
    assert state.status == "resolved" and approx(state.total_length, 10.0)
    assert state.rejected_events[0].event_id == "bad"


def test_conflicting_references_and_malformed_events_are_rejected() -> None:
    tvd = ev("tvd", "perforate", t(1), lo=1, hi=2)
    tvd["depth"]["reference"] = "TVD"
    datum = ev("datum", "perforate", t(1), lo=1, hi=2)
    datum["depth"]["datum"] = "MSL"
    nodatum = ev("nodatum", "perforate", t(1), lo=1, hi=2)
    del nodatum["depth"]["datum"]
    unit = ev("unit", "perforate", t(1), lo=1, hi=2, unit="fathom")
    other = ev("other", "perforate", t(1), lo=1, hi=2)
    other["wellbore_id"] = "wb-other"
    naive = ev("naive", "perforate", datetime(2000, 1, 2), lo=1, hi=2)
    daytz = day_ev("daytz", "perforate", "2000-01-02", lo=1, hi=2)
    del daytz["timezone"]
    badrev = ev("rev", "perforate", t(1), lo=1, hi=2, revision=0)
    junk: Any = "not a mapping"
    noid = ev("x", "perforate", t(1), lo=1, hi=2)
    del noid["event_id"]
    history = build(
        [
            tvd,
            datum,
            nodatum,
            unit,
            other,
            naive,
            daytz,
            badrev,
            junk,
            noid,
            ev("good", "perforate", t(1), lo=100, hi=110),
        ]
    )
    codes = {r.event_id: r.code for r in history.rejections}
    assert codes == {
        "tvd": "unsupported_depth_reference",
        "datum": "conflicting_depth_reference",
        "nodatum": "missing_depth_datum",
        "unit": "unsupported_unit",
        "other": "wrong_wellbore",
        "naive": "missing_timezone",
        "daytz": "missing_timezone",
        "rev": "malformed_event",
        None: "malformed_event",
    }
    assert len(history.rejections) == 10  # the non-mapping record and missing id both anonymous
    assert [e.event_id for e in history.events] == ["good"]


def test_unmapped_event_code_blocks_dependent_state_but_not_unrelated_records() -> None:
    records = [
        ev("b", "baseline", t(0), baseline_intervals=[]),
        ev("p", "perforate", t(1), lo=100, hi=110),
        ev("po", "open", t(1), lo=100, hi=110),
        ev("weird", "recompleted", t(2), lo=100, hi=110),
    ]
    history = build(records)
    assert history.rejections == ()
    before = history.state_at(t(1), 1)
    assert before.status == "resolved"
    state = history.state_at(t(2), 1)
    assert state.unmapped_event_ids == ("weird",)
    assert state.status == "partial" and state.total_length is None
    assert approx(state.total_length_lower_bound, 10.0)
    assert state.unresolved[0].reason == "unmapped_event_code"
    assert state.unresolved[0].md_intervals == ((100.0, 110.0),)


def test_squeeze_and_plug_codes_map_to_isolation() -> None:
    for code in ("squeeze", "plug"):
        records = [
            ev("b", "baseline", t(0), baseline_intervals=[]),
            ev("p", "perforate", t(1), lo=100, hi=110),
            ev("o", "open", t(1), lo=100, hi=110),
            ev("s", code, t(2), lo=100, hi=110),
        ]
        state = build(records).state_at(t(2), 1)
        assert approx(state.total_length, 10.0) and approx(state.open_length, 0.0)


def test_engine_makes_no_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: Any, **__: Any) -> None:
        raise AssertionError("network used")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    assert build(fixture_records()).state_at(t(6), 1).total_length is not None


def test_state_at_requires_explicit_aware_instant() -> None:
    history = build(fixture_records())
    with pytest.raises(ValueError):
        history.state_at(datetime(2000, 1, 2), 1)


# ----------------------------------------------------------------------------- PH-6 (engine)
def test_duplicate_imports_are_idempotent() -> None:
    records = fixture_records()
    once = build(records)
    twice = build([*records, *[dict(r) for r in records]])
    assert twice.events == once.events and twice.rejections == ()
    for day in range(7):
        assert twice.state_at(t(day), 1) == once.state_at(t(day), 1)


def test_distinct_reperforation_events_keep_distinct_ids() -> None:
    history = build(fixture_records())
    ids = [e.event_id for e in history.events if e.kind.value == "reperforate"]
    assert ids == ["e4-reperf", "e6-reperf-again"]
    a = derive_event_id("rec-1", WELLBORE, "reperforate", "1000", "1030")
    assert a == derive_event_id("rec-1", WELLBORE, "reperforate", "1000", "1030")
    assert a != derive_event_id("rec-2", WELLBORE, "reperforate", "1000", "1030")


def test_same_id_different_content_is_rejected_order_independently() -> None:
    a = ev("dup", "perforate", t(1), lo=100, hi=110)
    b = ev("dup", "perforate", t(1), lo=100, hi=120)
    r1 = build([a, b]).rejections
    r2 = build([b, a]).rejections
    assert r1 == r2 and r1[0].code == "duplicate_event_id_conflict"
    assert build([a, b]).events == ()


def test_superseding_correction_new_revision_old_revision_unchanged() -> None:
    records = [
        ev("b", "baseline", t(0), baseline_intervals=[]),
        ev("p", "perforate", t(1), lo=100, hi=110, revision=1),
        ev("p2", "perforate", t(1), lo=100, hi=125, revision=2, supersedes="p"),
    ]
    history = build(records)
    old = history.state_at(t(2), 1)
    new = history.state_at(t(2), 2)
    assert approx(old.total_length, 10.0) and old.correction_event_ids == ()
    assert approx(new.total_length, 25.0)
    assert new.correction_event_ids == ("p2",) and new.superseded_event_ids == ("p",)
    assert "p" not in new.evidence_event_ids and "p2" in new.evidence_event_ids
    # the correction keeps the original historical date; it changes knowledge, not time
    assert approx(history.state_at(t(1) - JUST_BEFORE, 2).total_length, 0.0)
    # retraction removes an event in a later revision only
    retracted = build([*records, ev("r", "retract", t(1), revision=3, supersedes="p2")])
    assert approx(retracted.state_at(t(2), 2).total_length, 25.0)
    assert approx(retracted.state_at(t(2), 3).total_length, 0.0)


def test_invalid_supersession_is_rejected() -> None:
    records = [
        ev("p", "perforate", t(1), lo=100, hi=110, revision=2),
        ev("same-rev", "perforate", t(1), lo=1, hi=2, revision=2, supersedes="p"),
        ev("ghost", "perforate", t(1), lo=1, hi=2, revision=3, supersedes="nope"),
        ev("noretarget", "retract", t(1), revision=3),
    ]
    history = build(records)
    assert {r.event_id: r.code for r in history.rejections} == {
        "same-rev": "invalid_supersession",
        "ghost": "invalid_supersession",
        "noretarget": "malformed_event",
    }
    assert [e.event_id for e in history.events] == ["p"]


def test_revision_before_any_event_is_unknown() -> None:
    state = build([ev("p", "perforate", t(1), lo=1, hi=2, revision=2)]).state_at(t(2), 1)
    assert state.status == "unknown"


def test_oversized_same_time_cluster_is_reported_unresolved_not_guessed() -> None:
    records = [ev("b", "baseline", t(0), baseline_intervals=[])]
    records += [ev(f"p{i}", "perforate", t(1), lo=100 + i, hi=101 + i) for i in range(8)]
    state = build(records).state_at(t(1), 1)
    assert state.status == "conflicting" and state.total_length is None
    assert state.unresolved[0].reason == "ambiguous_component_too_large"


def test_baseline_and_event_at_same_instant_is_unresolved() -> None:
    records = [
        ev("b", "baseline", t(1), baseline_intervals=[]),
        ev("p", "perforate", t(1), lo=100, hi=110),
    ]
    assert build(records).state_at(t(1), 1).status == "conflicting"
