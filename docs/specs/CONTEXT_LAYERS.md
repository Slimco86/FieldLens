# Specification: Aligned seabed and formation context

> **Spec type:** Product/feature. **Backlog:** FL-009.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-27. **Decision owner:** project owner.
> **Status:** Design complete; real layer sources/reference compatibility await G1.
> **Zero-Question Score:** 0 unowned design questions.

## How to Read This Spec

Executor: physical layers and ownership. QA: CX checks. Owner: minimum truthful
representation. Implements mandatory project AC-5 and contributes AC-8/9.

## Notation Key

`[Validated]` = required scope/invariant; `[Assumed: verify]` = proposed representation.
H/M/L are confidence; all AC scores are 3. Missing notices do not satisfy AC-5.

## 1. Outcome Statement

Users inspect source-backed seabed and reservoir/formation context aligned with
wellbores, with provenance, coverage and interpretation status visible.
Verification: CX-1 through CX-6. Outcome score 3.

## 2. Scope

### IN Scope

Offshore seabed surface, depth-domain formation horizons and well formation picks,
visibility/transparency controls and layer evidence. `[Validated: full context]`

### OUT of Scope

Reservoir simulation, seismic processing, automatic velocity/TWT conversion,
invented reservoir volume and global land terrain acquisition for offshore Volve.

### Scope Dependencies

FL-005-B approved source profiles, FL-016-A published model associations and
FL-006-B scene/reference contracts.
FL-009-A seabed and FL-009-B formations are independent slices after those inputs.
G1 validates real coverage for both; neither can be silently dropped.

### Open Scope Tensions

Formation picks alone do not establish a measured continuous horizon or reservoir
volume. Label interpolation and stop at source support limits; require G1 approval
of the proposed depth-horizon representation before calling it the demo context.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| CX-1 | Behavioral | Seabed control points transform into the shared physical frame within the fixture's 1e-6 m synthetic tolerance and G1's real-source tolerance. | 3 | [Validated] | `test_seabed_alignment` |
| CX-2 | Behavioral | Named depth horizons/picks retain original units/datum and show source versus interpolated classification, coverage bounds and evidence on selection. | 3 | [Validated] | `test_formation_layers` |
| CX-3 | Negative | TWT milliseconds, unknown vertical references and missing extents cannot become depth meshes; no extrapolation outside the approved supported area. | 3 | [Validated] | `test_layer_reference_failures` |
| CX-4 | Edge case | Duplicate/conflicting points and holes remain explicit; missing formation data does not hide valid seabed/wells; invalid cells are not zero-filled. | 3 | [Validated] | `test_context_gaps` |
| CX-5 | Non-behavioral | A combined field-view context budget <=200,000 triangles meets project AC-9; display LOD/toggles do not change physical picks/intersections. | 3 | [Assumed: verify budget] | context browser benchmark |
| CX-6 | Dependency | Approved real seabed plus reservoir/formation representation are both displayed with the pilot bores and source locators; notices or flat invented planes do not pass. | 3 | [Validated] | `test_pilot_context`, browser context |

Definition of done includes both source-backed layer families and CX-6.

## 4. Context and Decisions

Executor: `fieldlens-geospatial` owns each vertical layer slice, including typed
backend projection and its isolated frontend layer component; renderer-specific
performance gaps return to the orchestrator/3D owner.
Paths: `backend/fieldlens/context/{seabed,formations}.py`,
`frontend/src/features/context/{seabed,formations}/`, matching tests.
Shared scene registration is serialized at integration.

Input layer metadata: UUID/name, source claims, horizontal CRS, vertical datum,
depth sign/unit, extent, no-data convention, interpretation/acquisition dates and
coverage. Canonical points are `(E,N,z_up)` in the dataset frame. Source horizon
interpretation date is not an equipment effective date.

Supported first profile: numeric XYZ point/grid exports plus formation picks
with wellbore/depth references. Use validated triangulation inside source-supported
polygons; if only point support is known, stay inside the convex hull and preserve
explicit no-data holes. Do not connect across declared discontinuities/faults.
Display interpolation method/resolution and retain original points for checks.
No default geological dip, thickness, fault displacement or vertical multiplier.

Proposed reservoir context is named source-interpreted depth horizons and picks,
not a closed reservoir body. If G1 cannot support these, the requirement remains
blocked; substituting a simulator volume requires a separate source/profile decision.

The scene manifest carries physical bounds, render LOD, evidence and labels.
Layer visibility/transparency changes are presentation only. No endpoint silently
transforms a source's TWT depth basis. Field-level water depth is not a
well-specific seabed control point.

## 5. Failure Conditions

Unresolvable vertical datum/TWT -> retain source but block the layer mesh.
Triangulation bridges unsupported holes -> reject affected triangles and revise
the source mask/profile before integration.
Worst misinterpretation: two artistic planes cannot pass CX-6.

## 6. Ambiguity Audit

Seabed replaces land terrain for offshore Volve, not geological context.
The reservoir representation is a labeled horizon/pick context, pending source
acceptance by owner/G1. No physical reservoir-volume inference is authorized.

## 7. Implementation Guidance

FL-009-A: CX-1/3/4/5 for seabed. FL-009-B: CX-2/3/4/5 for formations.
CX-6 is their combined real acceptance. Planned checks:
`uv run pytest backend/tests/context`, layer interaction tests, type/build and
combined scene benchmark. No tests/layers exist yet. Propose minor per accepted
slice, with global metadata owned by orchestrator.

## Open Tensions

Mandatory context remains a feasibility risk if depth-domain data cannot be read.

## Assumption Registry

Candidate horizons are actually depth-domain (M; G1).
Their vertical datum matches an available transform (M; CX-1/3).
Source-supported triangulation fits rendering budget (M; CX-5).

## Adversarial Self-Critique

Depth/TWT can share numeric-looking files: require basis metadata.
Convex hull can hide internal missing regions: preserve source masks.
Well and field water depths differ in scope: do not substitute one for the other.

## Revision Triggers

Reopen on TWT-only sources, incompatible datum/coverage or failed combined
render performance at the accepted scene size.
