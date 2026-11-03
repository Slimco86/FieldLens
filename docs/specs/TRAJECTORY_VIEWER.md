# Specification: Deterministic trajectories and linked scene inspection

> **Spec type:** Product/feature. **Backlog:** FL-006.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-27. **Decision owner:** project owner.
> **Status:** Design complete; approved source references required for real acceptance.
> **Zero-Question Score:** 0 unowned design questions.

## How to Read This Spec

Engineering executor: physical contracts and fixtures. Scene executor: selection
and display. QA: TR tests. Covers project AC-3/8/9 and navigation in AC-7.

## Notation Key

`[Validated]` = project requirement; `[Assumed: verify]` = proposed design/threshold.
H/M/L are confidence. AC score 3 is binary. Source tolerances require G1 evidence.

## 1. Outcome Statement

Users inspect imported wellbores and their evidence, and obtain deterministic
closest-approach results independent of visible tessellation or exaggeration.
Verification: TR-1 through TR-7. Outcome score 3.

## 2. Scope

### IN Scope

Survey/reference validation, minimum curvature, MD sampling, bounded closest
approach, selectable R3F scene and keyboard asset tree. `[Validated: project]`

### OUT of Scope

Anti-collision certification, reservoir connectivity, magnetic-field estimation
without dated inputs, planned/as-built substitution, equipment modeling, charts.

### Scope Dependencies

FL-006-A numeric engine depends on FL-004-A only. FL-006-B integrated scene depends
on FL-006-A and FL-016-A's published model, sourced through qualified FL-005
profiles. Early checks use an approved survey subset; full pilot acceptance still
requires G1. The source/draft workspace is not an authoritative geometry endpoint.

### Open Scope Tensions

Visual simplification helps performance but cannot change computed distance.
Store physical and render sampling as separate projections.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| TR-1 | Behavioral | Analytic vertical, horizontal and curved fixtures below match each physical coordinate within 1e-6 m, including zero dogleg. | 3 | [Assumed: verify fixture] | `test_minimum_curvature` |
| TR-2 | Negative | Missing CRS/datum/north reference, nonfinite angles, decreasing/duplicate conflicting MD and unresolved magnetic conversion block affected survey geometry. | 3 | [Validated] | `test_survey_validation` |
| TR-3 | Behavioral | Closest distance for fixture segments is 5 m within 1e-6 m; curved results report <=0.02 m geometric error bound; changing display LOD/exaggeration changes no analytic result. | 3 | [Assumed: verify bound] | `test_closest_approach` |
| TR-4 | Behavioral | For imports of 1, 3 and 6 bores, tree/scene counts match accepted records and selection identifies the same bore/source in QueryContext; every object is keyboard-reachable and stale responses are discarded. | 3 | [Validated] | `trajectory-selection.test.tsx`, browser selection |
| TR-5 | Edge case | Missing or failed WebGL2 displays an accessible asset/evidence view and an explicit scene failure, not a fabricated successful 3D render. | 3 | [Validated] | `webgl-unavailable.test.tsx` |
| TR-6 | Non-behavioral | Five fixture bores at 1,000 render samples each meet p95 frame <=33.3 ms over a 30-second 1080p orbit after 5-second warmup; after 20 dataset replacements and final scene cleanup, owned geometry/texture counts return to the pre-load baseline. Record browser/GPU and heap/resource counts. | 3 | [Assumed: verify workload] | browser performance/resource check |
| TR-7 | Dependency | Real survey coordinates match independently approved source checkpoints/tolerances, and scene exposes CRS/datum, scale/origin, revision and source evidence. | 3 | [Validated] | `test_pilot_trajectories` |

TR-6's fixture does not cap application bore count. All tests, including TR-7,
are required for full feature verification.

## 4. Context and Decisions

FL-006-A owner: `fieldlens-geospatial`, paths `backend/fieldlens/engineering/`
survey/reference/proximity modules and tests. FL-006-B owner:
`fieldlens-3d-motion`, scene feature, asset tree integration, render manifest
endpoint/artifacts and scene tests. Shared contract changes remain serialized.

Inputs: project/published model context, typed survey station claims, reference
metadata, approved transform and survey revision. Survey claims from a deterministic parser always
win; when no deterministic source exists, an agent-extracted fallback claim (AGENTIC_EXTRACTION AX-11,
explicit CRS/datum/reference required) may be used and every output derived from it carries an
"agent-extracted fallback" label. Outputs: physical trajectory/provenance, render manifest with
local origin/axes, closest result with both MDs/points/error bounds.
Use [shared contracts](SHARED_CONTRACTS.md) and
[architecture physical frame](../ARCHITECTURE.md).

Analytic fixture: start at `(E,N,z)=(0,0,0)` with MD 0.
Vertical 100 m -> `(0,0,-100)`; constant east azimuth 90 degrees/inclination
90 degrees over 100 m -> `(100,0,0)`. A 100 m segment building from inclination
0 to 90 degrees at east azimuth has endpoint
`(200/pi,0,-200/pi)` = approximately `(63.6619772367581,0,-63.6619772367581)`.
The expected values must not be generated by welleng.
Closest fixture: vertical segment `(0,0,0)` to `(0,0,-100)` and
`(3,4,-10)` to `(3,4,-90)`. Distance is 5 m; nonunique closest MD pairs are
permitted only when both returned points actually lie on their paths.

Bound curve-to-chord deviation at <=0.01 m per path for proximity; combined
distance approximation bound <=0.02 m. Use a spatial broad phase only to prune
with conservative bounds; never skip a potentially closest segment. Bound jobs
by 10,000 analytic segments per bore and the job deadline; exhaustion returns an
explicit unresolved computation, not the best-so-far result labeled exact.
Do not extrapolate beyond surveyed MD or pick one of several TVD->MD crossings.

Uncached proximity API requests return an HTTP 202 job reference and run in the
same bounded CPU worker as other engineering work. Completed/cached results use
the typed distance envelope. A pending or timed-out tool never claims a finished
calculation; verify the queue path as part of the integrated scene/API slice.

Render local Float32 positions only after double-precision origin subtraction.
Reuse geometries/materials; dispose owned resources on replacement/unmount.
Camera fit/focus respects reduced motion and cancels previous transitions.

## 5. Failure Conditions

Source transform unavailable -> block affected geometry with reference issue.
Tolerance/workload bound fails -> return explicit failure and a measured
optimization/profile amendment to orchestrator; do not loosen tests silently.
Worst misinterpretation: nearest survey station pairs are not closest curves.

## 6. Ambiguity Audit

MD is path distance, positive TVD is down from its datum, and render Y is up.
Source checkpoints/tolerances are owned by G1/engineering before TR-7.
No source geometry is inferred from the conceptual design images.

## 7. Implementation Guidance

Planned checks: `uv run pytest backend/tests/engineering`, scene interaction tests,
frontend type/build and browser TR-6/7. Record welleng/pyproj versions and transform
operation/accuracy. Propose minor;
integration and resource cleanup follow the execution plan.

### FL-006-A implementation status (not yet independently accepted)

Package `backend/fieldlens/engineering/trajectory/` (NumPy only; no welleng/pyproj).
Implemented, awaiting QA: TR-1 (`test_minimum_curvature`), TR-2
(`test_survey_validation`), TR-3 (`test_closest_approach`). Not covered: TR-4..TR-7,
pyproj CRS transforms and real-survey checkpoints (TR-7), API/job queue, the
cross-bore real-data workload. Conventions: coordinates `(E, N, z-up)` in metres in the
CRS grid; MD/inclination/azimuth in `Survey.md_unit` (m or ft) and degrees, originals kept;
north reference true/grid/magnetic, with explicit `grid_convergence_deg`
(grid = true - convergence) and `magnetic_declination_deg` (true = magnetic + declination),
otherwise blocked. Explicit start position is required; a ~180 degree dogleg is blocked.
Proximity: arcs are split until chord sagitta <= 0.01 m, exact polyline minimum with
conservative AABB pruning, reported `error_bound_m` = sum of per-path sagitta bounds
(<= 0.02 m); budget/deadline exhaustion returns `UNRESOLVED`. A distance is not proof of
connectivity or safe clearance.

### Wellhead tie-in (TASK-091, EXPLORE_POLISH F)

When the first validated station has MD > 0 (stated TVD, inclination and azimuth), the response adds
`tie_in` (`TrajectoryTieIn`): `derived: true`, `label: "tie_in"`, `reason_code: "TIE_IN_DERIVED"`,
`kind: "vertical" | "arc"`, `max_dls_deg_per_30m` and `points` (`TrajectoryPoint`, MD 0 to first-station
MD inclusive; offsets/TVD of the last point equal the first station's). A `TIE_IN_DERIVED` warning is
added. It is display only: real stations, `points`, MD/TVD records, formation overlays, closest
approach and perforated length never see it; the trace is not translated. Components with MD below
the first station are placed by linear interpolation of `md_m` over `tie_in.points`.

- `vertical`: |MD - TVD| <= 0.05 m and inclination <= 0.1 deg.
- `arc`: cubic Hermite, vertical tangent at the wellhead, first-station tangent at the end; the
  tangent magnitude is solved so the curve length equals the first-station MD (MD along the tie-in is
  curve length). Emitted only when max dogleg severity <= 10 deg/30 m (ordinary build/turn rates are
  1-5 deg/30 m; a larger implied curvature means the first station is not a plausible continuation of
  a vertical hole). The first station sits at the same horizontal location as the wellhead, so an
  inclined first station yields a gentle S-shaped curve and only a narrow MD/TVD window is feasible.
- Otherwise (`MD < TVD`, no matching smooth curve, dogleg too high): `tie_in` is null and the warning
  `TIE_IN_NOT_DERIVED` is returned; nothing is invented or zero-filled. First station at MD 0: no
  tie-in and no warning. Missing first-station TVD at MD > 0 keeps the existing
  `WELLHEAD_START_UNKNOWN` block.

### Wellbore view: tie-in, default wellhead, unlocated components (TASK-090, EXPLORE_POLISH E)

- **Tie-in.** `TrajectoryInput.tieIn` (mapped from the API `tie_in` by `tieInInput`) is prepended to the drawn
  path by `WellPath.fromTrajectory`: the points from MD 0 to just before the first station (the last tie-in
  point *is* the first station, so it is not duplicated). The trace is one tube from the well hole (origin) to
  the end; it is labelled "Derived tie-in, display only (not surveyed)" in the label layer and in the model
  notes. A tie-in is used only when the first station MD > 0 and it validates (>= 2 finite points, strictly
  increasing MD, starts at the origin, ends on the first station within 1 mm); otherwise it is ignored
  (`tieInIgnored`), never repaired.
- **Placement.** Components/casing/tubing/hole sections with MD between 0 and the first station are placed by
  linear interpolation of `md_m` over the tie-in (`WellPath.at`/`slice`); absolute MD/TVD are unchanged, so
  the formation-top overlay stays valid. Tie-in points are not survey stations: `stationCount`, the Survey info
  counts and every calculation use the real stations only.
- **No tie-in** (`tie_in` null and first station MD > 0): the trace starts at the first station, components above
  it stay unlocated, and the model note plus the backend `TIE_IN_NOT_DERIVED` warning (shown with the other
  survey warnings) explain it. Nothing is invented.
- **Default wellhead.** A wellhead is always drawn at the well hole. When no `wellhead` component is placed
  there (absent, or unlocated/outside the MD range) `SceneModel.defaultWellhead` supplies the generic default
  wellhead (`wellheadBody`, default dimensions, labelled "Wellhead (default, generic: not from the sources)");
  it is not a component (not in the list, counts or inspector). A christmas tree stands on it.
- **Unlocated components** are no longer drawn (no tray): they stay in the component list ("listed only, not
  drawn in the 3D view") and inspector, selectable, with no invented depth. The `Unlocated` view button
  and `fitUnlocated` command were removed.
- `toTrajectoryState` passes `tie_in` through `tieInInput` into `TrajectoryInput.tieIn` (tested end to end).

### Field view: reconstructed-only set, layout and thickness (TASK-089, EXPLORE_POLISH D)

- **Which wellbores.** Only wellbores with a current asset spec are listed in the field-view tree,
  drawn in the field scene and offered in the single-view dropdown (the one currently shown is always
  kept). No list endpoint or exposure field carries this, so the signal is the per-wellbore
  `GET .../asset-spec` (200 reconstructed, 404 not yet), read once per wellbore (concurrency 4) by
  `ExploreScene` and shared by the field view and dropdown; generating a stub refreshes that wellbore.
  Failed reads stay listed with Retry. Surveys (`/trajectory`) are requested only for reconstructed
  wellbores, incrementally as specs resolve. The summary keeps total / reconstructed / not
  reconstructed / failed / loading counts.
- **Layout.** The survey route's `surface_location` (easting/northing; lat/lon-only counts as not
  located) is the only coordinate source. When every drawn wellbore has one, with a stated CRS, a metre
  unit (`m`/`metre(s)`/`meter(s)`) and identical CRS and datum (case/whitespace-insensitive; an unstated
  datum only matches another unstated one), wellheads sit at E/N offsets (x = east, z = -north) from the
  centroid of the placed set, computed in double precision and subtracted before float32. The label is
  "Surface-location layout (E/N offsets from the field centroid, <CRS>)". Otherwise (mixed/unstated
  CRS, datum or unit, feet, no locations) the schematic grid is used with the label "Schematic layout,
  not map positions" and the reason in its tooltip. No reprojection, unit conversion or CRS guess. In a
  located set, wellbores without a location (and failed loads) are *not* guessed: they wait in a labelled
  "unlocated" row south of the field, spaced by `max(10 % of spread, 60 m)` at `max(25 % of spread, 100 m)`
  from it, tagged "unlocated" in the label/inspector. Their locations are excluded from the centroid. CRS,
  datum and unit per well stay in the inspector ("Location").
- **Platform scale.** Pad half-width = min(global cap, 0.4 x nearest-neighbour distance) (floor 0.5 m for
  coincident heads); glyph/marker sizes scale with it, so same-platform wells a few metres apart do not
  overlap. Camera framing uses a sphere around the wellhead spread, the horizontal reach of the traces
  and the deepest trace. Layout waits until all reconstructed surveys settled (no re-layout flicker).
- **Thickness.** The default tube radius of every field trace equals the selected-state rule
  `max(0.05, defaultExaggeration(depth) * 0.035)` m (0.175 m at >= 2500 m, 0.35 m, 0.7 m for shallower
  holes) instead of an extent-derived width. Selection stays distinct: the selected well gets a bright
  emissive trace, a halo and its full primitives. Tube widths remain exaggerated display values; at a
  whole-field zoom of several km the world-space tubes can be sub-pixel.
- **Screen-space minimum width (TASK-093).** To keep traces legible at overview zoom, every far trace
  also gets a companion line of `FIELD_TRAJECTORY_MIN_PX` = 3 CSS px (`LineSegments2`, `worldUnits=false`,
  one merged object for all wells, `scene/tubeLine.ts`). It uses the same reconstructed vertices and
  colours, is display only (no MD/TVD, proximity or length input), is also a pick target for its well, and
  is owned/disposed with the far set. Its resolution is set on canvas resize/rebuild, never per frame or
  via React state. Thick world-space tubes still cover it when zoomed in; the selected well is drawn by
  the focused primitives as before. Cost: +1 draw call for the whole field.

## Open Tensions

No certified clearance or connectivity follows from a valid distance measurement.

## Assumption Registry

Survey references can be resolved (M; G1). welleng reproduces analytic conventions
(M; TR-1). Browser WebGL2 meets workload budget (M; TR-6).

## Adversarial Self-Critique

Wrong north reference can produce plausible curves: test rotated control fixtures.
Origin subtraction after Float32 loses precision: test large eastings.
Display LOD can leak into analytics: run TR-3 with different scene settings.

## Revision Triggers

Reopen on new survey reference conventions, failed independent coordinates or
measured scene/proximity budgets outside the defined workload.
