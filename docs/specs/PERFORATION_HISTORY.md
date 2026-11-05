# Specification: Historical perforation state and perforated length

> **Spec type:** Product/feature. **Backlog:** FL-008.
> **Load-bearing frameworks:** F1 outcome, F2 acceptance, F3 scope, F4 context.
> **Supporting:** F5 failure conditions, F6 ambiguity audit.
> **Date:** 2026-10-27. **Author:** Copilot-assisted synthesis.
> **Decision owner:** Project owner.
> **Status:** DRAFT; scope requested by owner, detailed contracts/fixtures await approval.
> **Zero-Question Score:** 0 unowned questions; three owned source/contract gates remain.

## How to Read This Spec

Owner: outcome, scope, open tensions. Implementer: acceptance criteria and
contracts. Tester: synthetic fixture, failure conditions and ambiguity gates.
This implements project S-9 and contributes to AC-1/4/6/7/8; it is not a completed
feature or authorization to begin coding.

## Notation Key

`[Validated]` means owner-confirmed requirement or cited terminology, not tested
implementation. `[Assumed: verify]` means a proposed contract requiring approval.
`[Unknown: TBD]` names a blocking decision and owner below. H/M/L mean high/medium/
low confidence, not measured probabilities. AC score 3 means explicit pass/fail;
an unapproved fixture or missing dependency still blocks execution.

## 1. Outcome Statement

For a selected wellbore, historical time and dataset revision, the user can inspect
evidenced perforation intervals and their state, see recorded/derived MD and TVD,
and obtain total/open perforated length with sources or explicit incompleteness.

**Verification:** PH-1 through PH-9, first with the synthetic fixture and then
with an approved real source sample. **Outcome score:** 3 conditional on the
source/time mapping gates; no field validation has been performed.

## 2. Scope

### IN Scope

- Historical perforation/reperforation events, opening, shut-off/isolation, reopening
  and wellbore production/injection/shut-in changes. `[Validated: owner, 2026-10-27]`
- Source-scoped state at a selected date/time, event provenance and revision.
  MD/TVD references and total perforated length/footage. `[Validated: owner]`
- Separate physical perforated coverage, interval access state and observed flow
  role/status; never infer interval flow from well-level production. `[Assumed: verify]`
- Deterministic interval aggregation and placement along a validated trajectory;
  temporal state shared by scene, inspector, chart overlays and agent tools.
  `[Assumed: verify]`

### OUT of Scope

- Perforating-tool operation/design, shot-level CAD, penetration prediction,
  stimulation simulation, productivity forecasting or live control.
- Inferring interval production/injection rates from commingled well totals.
- Treating hydraulic effectiveness, shot density or open-hole completion length
  as perforated MD coverage.
- General event-sourcing infrastructure or a manual adjudication application.
  Preserve an auditable event/claim history without imposing a new service stack.

### Scope Dependencies

FL-008-A implements the deterministic state engine and persistence against
FL-004-A's [shared contracts](SHARED_CONTRACTS.md), using the explicitly synthetic
fixture below. It does not depend on the renderer or completed pilot acquisition.
FL-008-B connects validated events from FL-016-A's published model, trajectory
placement, inspector and time controls after qualified FL-005 profiles and
FL-006-B. Full verification still requires PH-1 real history.
FL-010-C and FL-011 consume the canonical state result; their integration tests
remain those items' responsibility, avoiding circular dependencies.

### Open Scope Tensions

Complete date-specific reconstruction needs historical coverage that has not
been inspected. A partial record set must return unknown/partial state rather
than fabricate an initial empty or open completion. Resolve at PH-G1.

## 3. Acceptance Criteria

All detailed criteria are `[Assumed: verify with owner before FL-008 is ready]`.

| ID | Type | Pass condition | Score | Planned check |
|---|---|---|---|---|
| PH-1 | Dependency | Approved manifest maps actual event codes, target scope, dates/precision, source locators, interval units/depth references, initial coverage and expected states/lengths for a real wellbore history. | 3 | Real-source fixture review |
| PH-2 | Behavioral | At each effective instant in the fixture below, physical coverage, open length and wellbore status equal the expected values. Selecting just before an event returns the previous state. Reordered import batches do not change the result. | 3 | Deterministic replay/boundary tests |
| PH-3 | Behavioral | Disjoint/overlapping intervals and reperforation produce the stated unique MD lengths; ft/m conversion is consistent, gaps are excluded, and TVD/horizontal span is never substituted. | 3 | Union/units fixtures |
| PH-4 | Behavioral | Each interval exposes original recorded depth values/references and derived MD/TVD separately. Missing or ambiguous TVD-to-MD inversion blocks placement/length unless sufficient source mapping resolves it; no depth is silently filled. | 3 | Deviated/reversing-trajectory and missing-datum tests |
| PH-5 | Edge case | Without an established initial baseline, queries before the first known event return unknown, not verified zero. Date-only or same-time contradictory events do not acquire invented ordering; unresolved results expose affected interval/time coverage. | 3 | Incomplete-history/order fixtures |
| PH-6 | Behavioral | Stable IDs preserve distinct reperforation events; duplicate imports do not create duplicates. A superseding correction creates a new dataset revision; the old revision returns its prior result and the new one cites the correction. | 3 | Persistence/revision tests against PostgreSQL |
| PH-7 | Negative | A producing/injecting wellbore does not automatically assign that state to every interval. Whole-well shut-in changes the wellbore status but does not erase physical coverage or silently close each downhole interval. | 3 | Scope-specific state fixtures |
| PH-8 | Behavioral | State/geometry API and inspector share wellbore ID, as-of time and dataset revision; rapid time/asset changes cannot show an old response under new labels. Every displayed state, length and derived depth opens its evidence/derivation. | 3 | API and frontend interaction checks |
| PH-9 | Non-behavioral / negative | Default replay/geometry/API tests make zero paid calls. Invalid negative/nonfinite/reversed MD bounds, conflicting references and malformed events produce explicit failures without corrupting unrelated validated history. | 3 | Validation and failure tests |

**Definition of done:** approved source/contract gates, all checks passed, real
sample verified, consumer contracts documented and versioned integration recorded.
UI sketches or synthetic fixtures alone do not establish real perforation coverage.

### Synthetic numeric fixture (not Volve data)

Proposed reference fixture: metre MD along one validated, deviated trajectory;
exact UTC instants, complete empty baseline at t0. Relevant MD->TVD point pairs:
1000->900, 1005->902, 1008->903.2, 1010->904, 1020->908, 1025->910,
1030->912. This is only an unambiguous depth-reference fixture, not a field survey.
Check numeric results within `1e-6 m`; real-data tolerances come from PH-G1.

| Instant | Explicitly evidenced event(s) | Total perforated length | Open perforated length | Wellbore flow status |
|---|---|---|---|---|
| t0: 2000-01-01T00:00:00Z | Complete baseline: no perforations; well shut in | 0 m | 0 m | shut_in |
| t1: 2000-01-02T00:00:00Z | Perforate and open A=[1000,1010), B=[1020,1030); well begins producing | 20 m | 20 m | producing |
| t2: 2000-01-03T00:00:00Z | Isolate only [1005,1010) | 20 m | 15 m | producing |
| t3: 2000-01-04T00:00:00Z | Shut in the well; no downhole access change recorded | 20 m | 15 m | shut_in |
| t4: 2000-01-05T00:00:00Z | Reperforate [1008,1025); explicitly reopen [1005,1010) and open new coverage [1010,1020) | 30 m | 30 m | shut_in |
| t5: 2000-01-06T00:00:00Z | Well begins injecting; no new interval-flow attribution | 30 m | 30 m | injecting |
| t6: 2000-01-07T00:00:00Z | Reperforate [1000,1030) again; no access change | 30 m | 30 m | injecting |

At t1 the envelope is 30 m, but unique perforated coverage is only 20 m.
At t4 the 17 m operation adds only 10 m of unique coverage. At t6 the 30 m
operation adds zero length. Interval flow remains unknown throughout unless
separate interval-scoped observations are supplied.

## 4. Context and Decisions

### Terminology and assessment

SLB's [perforated interval](https://glossary.slb.com/en/terms/p/perforated_interval)
means a section of wellbore, potentially separated from other intervals by
unperforated gaps. [Measured depth](https://glossary.slb.com/en/terms/m/measured_depth)
follows the well path. [Perforation density](https://glossary.slb.com/en/terms/p/perforation_density)
is a count per unit length, not the interval's length. These terminology sources
were checked on 2026-10-27; no source dataset was verified.

Recommendation: label the user's "completion footage" as **total perforated
length (MD)**, or **perforated footage** in feet. Use **perforated interval length**
for one continuous interval. The exact unique-coverage aggregation below is a
FieldLens definition, not a claim of one universal industry definition for
"completion footage." Preserve that original source term and any reported value.

Horizontal displacement, lateral/open-hole completion length, vertical thickness,
shot density and perforation tunnel penetration are different quantities.
Never silently map a source's ambiguous "footage" field to our metric.

### Proposed data and tool contract

Executor: engineering implementer under main-agent orchestration; no existing
application schema is assumed. Owner approves the following at PH-G2.

- **Event claim:** stable event/source-record ID, wellbore ID, affected interval
  IDs or explicit MD bounds, original event code/meaning, operation versus observed
  status, source locator/method, effective time and precision, report/import time,
  validation state, source/dataset revision and any superseded claim ID.
- **Depth:** original endpoint values, units, MD/TVD basis, datum/depth origin;
  normalized MD endpoints when available; recorded versus trajectory-derived TVD
  at each endpoint and derivation/survey revision. Use `from_md`/`to_md`, not an
  assumption that the second point is vertically deeper. TVD need not be monotonic.
- **State axes:** physical perforated coverage; interval access (`open`, `isolated`
  or `unknown`); flow status (`producing`, `injecting`, `shut_in`, `unknown`) with
  explicit wellbore/interval scope and time validity. Retain unsupported source
  codes/conflicts instead of inventing transitions. Interval isolation and surface
  shut-in have different meanings.
- **As-of request:** wellbore ID, explicitly selected time/date with precision,
  dataset revision. No implicit "today" or latest-state answer to a dated question.
- **Result:** resolved/partial/unknown/conflicting status, selected time/revision,
  intervals and each state axis, original/derived depths, length values/units,
  known-subset bounds where justified, coverage limitations and evidence IDs.
  Missing data is not an empty successful list with zero totals.
- **Consumer contracts:** chart overlays and RAG tools consume this same result.
  Cache keys include wellbore, effective query/precision, dataset and trajectory/
  derivation revisions. Charts/logs preserve acquisition periods; an as-of view
  does not make an older log contemporaneous.

### State derivation and length

At time t within revision r, let P(t,r) be validated physical perforated coverage
in normalized MD, and O(t,r) the subset explicitly known open:

`total_perforated_length = measure(union(P))`

`open_perforated_length = measure(union(P intersect O))`

Use intervals rather than rendered points/meshes. Normalize units/references
before unions. Keep source interval IDs/provenance when splitting at overlapping
event boundaries. Shut-off removes open access over its target, not physical
perforation history. Reperforation alone does not prove reopening, production
or injection; it may change shot density without increasing unique length.

Unknown members make an exact total unavailable. Return a clearly labeled known
subset/lower bound only when justified, never a complete-looking total. Before
known coverage begins, unknown is mandatory unless a reliable initial baseline
establishes absence. Carry forward only states whose persistence is supported by
the approved event mapping; temporary observations do not apply indefinitely.

For exact instants, event effect starts inclusively; derived state validity is
half-open `[effective_from, effective_to)`. Preserve source date precision and
timezones. Date-only/same-time events that could yield different results require
source ordering or an explicit ambiguous result, not filename/import order.
Corrections change knowledge in a new revision, not the event's historical date.

## 5. Failure Conditions

| Condition | Deviation signal | Required action |
|---|---|---|
| Missing baseline/time semantics | State before/within a date cannot be determined | Return affected unknown/ambiguous history; escalate mapping at PH-G1 |
| Ambiguous depth/footage | Only TVD with multiple possible MD crossings, or undefined "footage" | Block affected length/placement; keep original claim for inspection |
| Conflicting status scopes | Well shut-in is used to label each interval isolated, or interval flow inferred from totals | Reject the inferred transition; add a scope-specific test |
| Unmapped operation | New source event code changes state in an unspecified way | Retain unsupported event; block dependent state until spec mapping is approved |

**Worst misinterpretation:** summing event footage overcounts reperforation;
using TVD span undercounts horizontal/deviated interval length; a well-level
production record does not identify the contributing perforations. PH-3/4/7
must reject these results.

## 6. Ambiguity Audit

| Gate | Unresolved question | Owner / due |
|---|---|---|
| PH-G1 | Actual event fields/codes, depth references, temporal precision, state validity and initial-history completeness; real-data tolerances | Owner + data implementer / G1 audit, before FL-008 readiness |
| PH-G2 | State/result layout and API are now specified in [shared contracts](SHARED_CONTRACTS.md); owner approval of those contracts/metric/fixture remains required | Owner + orchestrator / before FL-008 readiness |
| PH-G3 | Shared instant/day query semantics and selection are specified; [charts](LINKED_CHARTS.md) CH-5 and [assistant](RETRIEVAL_ASSISTANT.md) RG-3/4 define cross-feature tests | Orchestrator + consumer implementers / approve before affected consumer assignments |

## 7. Implementation Guidance

Prefer typed relational event/claim records and deterministic state projection
inside the existing Python/PostgreSQL stack. No LLM replay of history, model-written
SQL, new event bus or runtime multi-agent framework is required.
Follow [delivery workflow](../DEVELOPMENT_WORKFLOW.md); commit tests and evidence,
then let the orchestrator allocate version/changelog updates at integration.

FL-008-A owner: `fieldlens-geospatial`, planned paths
`backend/fieldlens/engineering/temporal.py` and `backend/tests/history/`.
It implements PH-2/3/5/6/7/9 with synthetic inputs and PostgreSQL persistence;
reported source values and derived depths remain separate.
FL-008-B owner: `fieldlens-frontend`, planned history feature, typed state endpoint
and integrated PH-1/4/8 checks. Shared migrations/types are serialized by the
orchestrator. No worker is assigned until approval, base, worktree and resources
are recorded under the execution plan (archived in git history).

Selection uses an explicit instant or calendar day/timezone. A day whose state
changes within the day returns changing/ambiguous ranges, not invented event
ordering. The numeric fixture's exact instants remain unchanged. Synthetic
replay tolerance is 1e-6 m; source mapping/tolerances remain PH-G1.
Planned checks: `uv run pytest backend/tests/history`, frontend history/overlay
interaction tests and type/build checks. These commands/tests are not yet created.

## Implementation Status (FL-008-A engine, implementation complete; pending independent acceptance)

Pure-Python engine: `backend/fieldlens/engineering/perforation/`; tests:
`backend/tests/engineering/perforation/` (`uv run pytest backend/tests/engineering/perforation`).
Synthetic inputs only; independent QA has not accepted it.

| Criterion | Status |
|---|---|
| PH-2, PH-3, PH-5, PH-7, PH-9 | Engine + unit tests (t0..t6 fixture, 1e-6 m). |
| PH-6 | Engine part only: stable-ID helper, duplicate-import idempotence, same-ID/different-content rejection, `supersedes`/`dataset_revision` selection citing the correction. PostgreSQL persistence/revision tests **deferred** (no migration/DTO added). |
| PH-1, PH-4, PH-8 | Not implemented (real sample; MD<->TVD inversion; API/UI). Recorded TVD is carried verbatim, derived TVD is never filled. |

Conventions: `PerforationHistory.build(records, wellbore_id=, md_datum=)` validates each raw
mapping into an event or an explicit `EventRejection`; `state_at(as_of_aware_datetime,
dataset_revision, unit)` returns `PerforationState`. Exact `Decimal` metre arithmetic; only MD
with the wellbore's declared datum is accepted, and any MD above 100,000 m after conversion is
rejected (`implausible_depth`; arithmetic/date overflow is a per-event rejection too). Event
codes: baseline, perforate, reperforate, open, reopen, isolate (aliases squeeze/plug/shut_off),
wellbore_status, interval_flow, retract; any other code is retained as unmapped and blocks
dependent state (`partial`). Perforate does not open; isolate/open change access only.

Ordering: instant events have a 1 µs window; day events need an explicit timezone and cover the
local day. Overlapping windows are *not* permuted wholesale. Events commute (need no ordering)
unless they assign different values to the same state variable (perforated / access / interval
flow / wellbore status) over overlapping MD ranges, or involve a different baseline. Only the
connected non-commuting sub-groups (plus partially elapsed day-precision events, which may or may
not have happened) are explored exactly (subset DP, at most 12 events and 32 candidate states).
Differing outcomes become `UnresolvedCoverage` (axis, MD ranges, time window, event IDs) and
lengths become bounds. Over budget: explicit `ambiguous_component_too_large`, a lowest/highest
coverage bracket for total length, open bounds withheld, every interval row touching a forced
group (all rows if it contains a baseline) reports no definite value (perforated None, access/flow
`unknown`, all axes unresolved) and the wellbore status is `unknown` when a forced group holds a
baseline or status event. Strict time order between non-overlapping windows inside a component is
respected when exploring (only overlapping windows are mutually unordered). 20 same-instant perforates resolve
exactly; 5,000 events in clusters of 5 answer `state_at` in about 0.1 s.

Assumption pending owner confirmation (D5): the spec does not define same-instant baseline
semantics; an instant baseline establishes the initial state at the START of its instant and
precedes same-instant events. Two different baselines at one instant, or a baseline overlapping a
date-only event window, remain unresolved.

Corrections: a correction (`supersedes`) needs a later dataset revision and must supersede the
latest correction in the chain (or the original); a second, later-revision correction of an
already-corrected event is rejected (`invalid_supersession`), chained corrections work, and
same-revision ties are rejected (`conflicting_supersession`).

Status: unknown / partial (no baseline, unknown access, unmapped code) / conflicting / resolved.
Open length is exact only when every perforated interval has known access. Day-range queries are
not implemented (instant as-of only).

## Open Tensions

The owner requests an as-of state at every date, but the source may not justify
one. Return explicit unknown/partial results where necessary; never disguise that
gap with a continuous invented history. No exact metric is promised before approval.

## Assumption Registry

| Assumption | Confidence | Invalidation signal |
|---|---|---|
| Records contain enough dated interval evidence | M | Missing initial baseline or event targets |
| MD/TVD mapping can be tied to a valid survey revision | M | Missing reference/datum or non-unique inverse mapping |
| Source event codes distinguish operation, interval access and wellbore flow | M | "Closed" or "recompleted" lacks scope/meaning |

## Adversarial Self-Critique

1. Catalog facts cannot repair absent historical event evidence; watch for web
   results being treated as dates/locations of installation.
2. A correct union can still be a false total if records are incomplete; watch
   for unknown intervals being discarded before aggregation.
3. Time controls can make old logs appear current; watch labels and caches during
   rapid wellbore/date changes and preserve acquisition dates explicitly.

## Revision Triggers

Revisit mapping/ACs if real records use different state codes or temporal precision;
revise geometry contracts if depth inversion is ambiguous; revise consumer contracts
if charts/RAG need date ranges rather than an instant. Record owner decisions.
