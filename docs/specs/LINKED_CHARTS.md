# Specification: Linked production and depth-log charts

> **Spec type:** Product/feature. **Backlog:** FL-010.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-27. **Decision owner:** project owner.
> **Status:** Design complete; real series associations and units await G1.
> **Zero-Question Score:** 0 unowned design questions.

## How to Read This Spec

Executor: series/time contracts. QA: CH tests. Owner: both families and provenance.
Implements project AC-6/8/9 and chart tools for AC-7.

## Notation Key

`[Validated]` = owner/project invariant. `[Assumed: verify]` = design/limit proposed.
H/M/L are confidence. AC score 3 = binary; display samples are never analytic inputs.

## 1. Outcome Statement

Selecting an asset and historical time exposes its correctly scoped production
and depth-log series with evidence-linked values, gaps and perforation overlays.
Verification: CH-1 through CH-7. Outcome score 3.

## 2. Scope

### IN Scope

ECharts production timeline, multi-track log/depth view, windowing, source
inspection, selected-time marker and canonical perforation overlays.

### OUT of Scope

Production forecasting, allocation of commingled flow to intervals, deriving rate
from unknown volume duration, editing measurements and replacing logs with charts
of invented values. CSV export is not required for the first increment.

### Scope Dependencies

FL-010-A production and FL-010-B logs depend on qualified FL-005-B source records
and the FL-021 shell (TASK-034). Owner decision, October 30: they no longer wait for
FL-016-A. Until a published model associates a series with an asset, views are scoped
by project and source well/wellbore identifiers and labeled "not reconciled to a model";
association with published assets is wired by FL-010-C (TASK-018) and the assistant
(TASK-031). They can run independently without a finished 3D viewer. FL-010-C overlays
additionally needs FL-008-B plus both chart slices and verifies the linked scene/inspector state.

### Open Scope Tensions

Selecting a historical date does not make an old log a measurement on that date.
Show acquisition date and overlay time separately.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| CH-1 | Behavioral | Production fixtures preserve timestamps/periods, units, volume/rate/cumulative meaning, zeros and gaps; well-level series remain labeled well-level. | 3 | [Validated] | `test_production_series`, production interactions |
| CH-2 | Behavioral | Log fixtures preserve mnemonic, value/unit, MD or TVD basis, null sentinel, acquisition date and depth reference; synchronized tracks use the same supported depth axis. | 3 | [Validated] | `test_log_series`, log interactions |
| CH-3 | Negative | Well totals cannot become interval flow and TVD cannot be relabeled MD; nonpositive log-scale values are flagged, not clipped into plausible positives. | 3 | [Validated] | `test_chart_semantics` |
| CH-4 | Edge case | Out-of-order responses during rapid well/date/revision changes cannot paint old data under new labels; missing series reports unavailable, not zero. | 3 | [Validated] | `chart-context-race.test.tsx` |
| CH-5 | Behavioral | PH fixture t1/t3/t4 overlays show the same intervals/state as the inspector and scene; recorded curve acquisition time remains unchanged. | 3 | [Validated] | `perforation-overlays.test.tsx` |
| CH-6 | Non-behavioral | A 100,000-point synthetic series returns <=5,000 display points preserving endpoints, gaps and per-bucket extrema; full-resolution tool statistics remain exact. Local reads satisfy AC-9. | 3 | [Assumed: verify workload] | `test_display_decimation`, chart benchmark |
| CH-7 | Dependency | Both real production and log families load for their manifest-associated assets and values match source cells/lines at all gold checkpoints. | 3 | [Validated] | `test_pilot_charts` |

Both chart families are mandatory even if one asset has no association. CH-7
cannot pass from a synthetic screenshot.

## 4. Context and Decisions

Executor: `fieldlens-frontend` per slice; owns the relevant isolated feature plus
its small typed series endpoint/repository under frozen contracts.
Paths: `frontend/src/features/{production,logs,history}/`,
`backend/fieldlens/series/` split by family, and tests.
One owner handles the shared series schemas/migrations per integration.

Series definition: ID, family, entity type/ID, acquisition/measurement period,
source revision, original/normalized units, null tokens, quantity meaning,
depth/time basis and evidence. Points reference records; chart tooltip opens
original evidence even for decimated display points.
Explicit well-to-wellbore associations expose ambiguity; no default "first bore".

Production X axis is source calendar/time with explicit precision/timezone;
do not coerce daily/monthly totals into instantaneous rates. Different units use
separate labeled axes/tracks, not silent overlays. Log depth increases downwards;
TVD tracks require validated mapping and preserve nonunique/unsupported ranges.
Missing segments break lines; do not interpolate through missing data.

Display decimation is deterministic min/max buckets plus endpoints and gap markers.
At most 5,000 output points includes those markers. If exact gap structure cannot
fit the window, request a narrower window and expose a limit result; never join gaps.
Server calculations use original points. Units/conversion/aggregation methods
remain visible. ECharts instances/listeners are disposed on unmount.

Keyboard controls select assets, chart windows and evidence; provide a bounded
accessible data table and labeled axes/tooltips. Shared QueryContext drives requests;
abort stale requests and check context again before applying results.

## 5. Failure Conditions

Missing series quantity/depth reference -> block affected normalization/axis,
retain source view. Stale response -> discard and keep a loading/error state
associated with the current context.
Worst misinterpretation: a smooth chart that fills missing values fails CH-1/2/6.

## 6. Ambiguity Audit

Production time, log acquisition date and selected overlay time are different.
Scope joins are explicit. Source unit/association decisions belong to G1 before CH-7.

## 7. Implementation Guidance

FL-010-A handles CH-1/3/4/6; FL-010-B CH-2/3/4/6; FL-010-C CH-5 and combined CH-7.
Planned checks: series pytest files, focused Vitest interaction tests, type/build,
and browser chart/evidence selection. No tests implemented/run yet.
Propose minor for accepted slices; main agent integrates release metadata.

## Open Tensions

Logs can be absent for a specific wellbore without justifying omission of the
required log capability or the pilot's log coverage requirement.

## Assumption Registry

Series assets are resolvable (M; G1). Units/period meaning exist (M; CH-1/2).
Extrema/gap-preserving display fits 5,000 points in useful windows (M; CH-6).

## Adversarial Self-Critique

A daily volume labeled rate can look plausible: test quantity kind.
Parent-well series can appear bore-specific: show scope.
Downsampling can erase spikes/gaps: compare buckets against full-resolution data.

## Revision Triggers

Reopen on unresolved series associations, nonunique depth conversion or display
windows that cannot preserve required gaps/extrema within the budget.
