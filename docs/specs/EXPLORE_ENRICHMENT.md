# Specification: Explore enrichment — formations in 3D, wellbore/field charts, camera fly-over, project assistant

> **Spec type:** Product/feature (four bounded increments). **Backlog:** FL-024, FL-025, FL-026, FL-027.
> **Load-bearing frameworks:** outcome, acceptance, scope, context. **Supporting:** failure conditions, ambiguity audit.
> **Date:** 2026-11-03. **Author:** orchestrator. **Decision owner:** project owner.
> **Status:** Approved by the owner 2026-11-03 18:47 EST (decisions D1-D7, section 8).
> **Delivery state:** wave 0 dispatching. **Integration version:** pending (serial minors from 0.53.0).
> **Zero-Question Score:** 0 open decisions.

Refines FL-009 (context layers, formation slice), FL-010 (linked charts) and FL-011 (assistant) for the
current Explore tab; those specs keep their acceptance IDs (CX-*, CH-*, RG-*) and this spec adds the
representation, placement and UX decisions requested November 3. Execution plan with lanes:
plan/feature-explore-enrichment-1.md (archived in git history).

## 1. Outcomes

1. **FL-024 Formations in 3D.** Formation tops/levels are drawn underground with the wellbore, each with a
   name, interpretation status and source link; with no surface geometry they degrade to labeled level planes.
2. **FL-025 Explore charts.** The Explore tab gains charts: a wellbore view shows only that wellbore's
   production/injection, pressure, perforation/completion events (and lab/pressure tests when records exist);
   the field view shows global charts.
3. **FL-026 Camera.** Single-wellbore **Fly over** button (wellhead to TD, visiting every located element);
   every focus change (element, wellbore, formation) flies smoothly and ends facing the trajectory.
4. **FL-027 Assistant.** An expandable project chat (persona avatar) answers from extracted data with
   citations, generated charts and deep links to the exact source/scene/chart location.

## 2. Scope

**IN:** items above; deterministic read APIs under frozen contracts; UI states for loading/empty/error/stale.

**OUT:** reservoir simulation or volumes; velocity/TWT conversion; dip/fault modelling; operational-twin claims;
voice/TTS/lip-sync; model-written code/SQL/scene scripts; assistant writes to reconstruction or publication;
interval-level flow from well-level production; horizon grid import (FO-7, deferred by D5).

**Truth rules carried unchanged:** original units/datum preserved; MD is not TVD; gaps are gaps (never zero-filled or
joined); well-level series stay labeled well-level; generic/illustrative shapes never enter calculations; every drawn
or charted assertion links to evidence; assistant output is grounded in tool results, never model-supplied numbers.

## 3. Acceptance criteria

### FL-024 Formations in 3D (FO)

| ID | Pass condition | Test |
|---|---|---|
| FO-1 | Each valid pick is placed on its wellbore at its MD by the deterministic trajectory engine; the engine's TVD is compared with the pick's TVD/TVDSS and a disagreement beyond tolerance is a reported conflict, never silently chosen. | `test_formation_placement` |
| FO-2 | Picks flagged ER/FP/FO/NL/NR or lacking a usable depth are listed with their qualifier but not drawn; TWT-only picks never become depth geometry. | `test_formation_unsupported` |
| FO-3 | Representation tiers, always labeled on screen and in the inspector: **T1** pick marker (observed); **T2** level plane at the pick's scene elevation (illustrative, bounded to the scene footprint plus margin, "not an interpreted horizon"); **T3** interpolated surface (>=3 non-collinear picks of one surface, inside the convex hull, no extrapolation, method shown); **T4** source horizon grid (stretch, FO-7). Highest tier is drawn; T2 is the fallback only. | `test_formation_tiers`, `formation-layer.test.tsx` |
| FO-4 | Selecting a formation (3D, list or label) shows name, MD/TVD/TVDSS with original units and datum, qualifier, tier, evidence (document + locator opening the source viewer) and extraction method. | `formation-inspector.test.tsx` |
| FO-5 | Planes/markers follow the vertical-exaggeration, cutaway and label options; toggles (all, per surface), opacity and label mode are presentation only; picks and intersections are unchanged. Cross-wellbore planes/surfaces are blocked, with an on-screen reason, when bores' vertical references differ or are unknown. | `formation-options.test.tsx`, `test_formation_datum_block` |
| FO-6 | Missing/failed formation data leaves wellbores, equipment and other layers intact and shows an unavailable state; combined field context <=200,000 triangles (CX-5); layer resources are disposed. | `test_context_gaps`, scene probe |
| FO-7 (stretch) | Depth-domain horizon XYZ files (Volve Hugin top/base, seabed) import with CRS/datum/no-data metadata and render as T4; TWT or unknown datum blocks the mesh. | `test_horizon_import` |

### FL-025 Explore charts (XC)

| ID | Pass condition | Test |
|---|---|---|
| XC-1 | Wellbore chart set for the selected wellbore only: production/injection rates (oil, gas, water, water injection) and cumulative volumes, downhole pressure/temperature (+ tubing/annulus when present), on-stream hours, perforation/completion event timeline with perforated-length step chart, and log tracks vs MD with formation tops as reference lines. A chart whose records do not exist says so; it is not drawn empty or zero. | `test_wellbore_charts`, `wellbore-charts.test.tsx` |
| XC-2 | Records never leak between wellbores: well-level series are labeled well-level and not attributed to a wellbore; ambiguous association is surfaced, never "first bore". | `test_chart_scope` |
| XC-3 | Field chart set: field rate by wellbore (stacked) and totals, cumulative by wellbore, producer vs injector volumes (only same-unit, same-meaning series are summed; excluded series are listed), downhole-pressure comparison, on-stream/uptime strip, perforated length by wellbore at the as-of date, and a stratigraphic correlation chart (top depth per surface per wellbore, TVDSS only when datum is known). | `test_field_charts`, `field-charts.test.tsx` |
| XC-4 | Different units use separate labeled axes; gaps break lines; <=5,000 display points per series with endpoints, extrema and gap markers; aggregates are exact server-side values on full-resolution data (CH-6). | `test_chart_semantics`, `test_display_decimation` |
| XC-5 | Selecting a wellbore/switching view/changing the as-of date aborts stale requests; an out-of-order response never paints under the wrong label (CH-4). Tooltip/point opens the original evidence. | `chart-context-race.test.tsx` |
| XC-6 | A keyboard-reachable data table and labeled axes exist for every chart; ECharts instances and listeners are disposed on unmount. | `chart-a11y.test.tsx` |
| XC-7 | The Explore stage offers 3D / Charts / Split; wellbore view shows the wellbore set, field view the field set; wellbore selection, as-of date and chart-to-formation/perforation hover stay linked with the scene. | `explore-linking.test.tsx`, browser check |

Pressure-test/lab-test/DDR event records have no parser today; XC-1 shows them only when records exist (TASK-101 decides
and, if sources are present, adds a profile). That is a data-availability limit, not a UI downgrade.

### FL-026 Camera (CM)

| ID | Pass condition | Test |
|---|---|---|
| CM-1 | Focusing any target (element, wellbore, formation, fit-all) flies along a smooth zoom-pan path (zoom out then in on long hops), duration 0.6-2.0 s scaled by distance, ease in/out; no pose jump at start, end or when retargeted mid-flight (continues from the current pose); pointer/keyboard input cancels. | `cameraPath.test.ts`, `cameraRig.test.ts` |
| CM-2 | At arrival the camera looks at the target from a side direction chosen so the trajectory is visible: the view direction is >=35 degrees off the local tangent, and trajectory samples within a window around the target are inside the frustum (projection test). | `cameraPath.test.ts` |
| CM-3 | Single wellbore view only: a **Fly over** button plays wellhead to TD along the trajectory (parallel-transport frame, no flips), dwelling at every located element and formation/perforation in MD order, then fits all. Every located element is visited exactly once; unlocated elements are listed, not visited. | `flyOverPlan.test.ts` |
| CM-4 | Fly-over controls: play/pause/stop, previous/next stop, speed 0.5x-4x, Esc and pointer input cancel and hand control back; the current element is shown (card) and announced (aria-live); total duration at 1x is bounded (<=60 s). | `flyover-controls.test.tsx` |
| CM-5 | `prefers-reduced-motion` gives stepped jumps (no animated flight) with the same announcements; the field view has smooth transitions but no fly-over button. | `reduced-motion.test.tsx` |
| CM-6 | Per-frame work uses refs/imperative updates only (no React state per frame); p95 frame time during a flight stays within the TR-6 budget on the scene probe. | scene probe benchmark |

### FL-027 Assistant (AV)

| ID | Pass condition | Test |
|---|---|---|
| AV-1 | Conversations are project-scoped and persist across restart; UI selection (wellbore, as-of, view) is sent as typed context but never widens scope; cross-project data is never returned. | `test_chat_scope`, `test_chat_persistence` |
| AV-2 | Only allowlisted typed read-only tools run (evidence search, project/wellbore summary, formation tops, production/pressure summaries, perforation state as-of, events, trajectory summary, data issues, wellbore comparison); arguments and IDs are validated server-side; no code, SQL, shell, URL fetch or write action exists. | `test_chat_tools`, `test_chat_negative_controls` |
| AV-3 | An answer is typed blocks: `text` (citation markers), `value` (number + unit bound to a tool result), `chart` (declarative ChartSpec referencing tool-result series; the server materializes the data, the model never supplies points), `link` (AppLink: source{document,page/locator}, wellbore, element, formation, chart{kind,wellbore,window}), `gap/refusal`. Every cited/linked ID must exist in this turn's tool results and project; invalid blocks are dropped and the answer marked partially verified. Free-text numbers absent from tool results are flagged unverified. | `test_answer_validation` |
| AV-4 | Clicking a link opens the exact source page/locator in the existing viewer, flies the camera to the element/formation/wellbore, or opens the chart tab with the window set; stale/missing targets show an explicit message. | `assistant-links.test.tsx`, browser check |
| AV-5 | Generated charts render with the same chart components as the Charts tab, keep units/gaps/evidence, and open in the Charts tab on request. | `assistant-chart-block.test.tsx` |
| AV-6 | Provider refusal, truncation, malformed output, cancellation, outage and budget refusal show explicit states without fake success; per-turn step/time/tool-call bounds apply (no spend ceiling, D4); unit tests use the fake provider. | `test_chat_failure_paths` |
| AV-7 | The panel is expandable (collapsed launcher, docked, large), keyboard operable, announces streaming/finished state, and the avatar (SVG persona: idle, thinking, answering, refusal/error) honors reduced motion. | `assistant-panel.test.tsx` |
| AV-8 | Prompt-injection text in documents cannot change tools, scope or links; draft/unpublished proposals are labeled as such; unavailable data is stated, not invented. | `test_chat_negative_controls` |
| AV-9 | Live Meta check (allowed, D4) with at least 3 questions (cited fact, chart request, refusal) records protocol/usage and block validity; opt-in via the `live_meta` marker, not in default tests. | `live_meta` marker |

## 4. Design decisions

### 4.1 Formation read model (FL-024)

New backend module `backend/fieldlens/context/formations.py` (+ route) composes existing `formation_pick` records
(`dat_tables` profile: `pick.surface_name/md/tvd/tvdss/twt/qualifier/easting/northing/dip/azi`) with the wellbore
trajectory service (`wellpath`). No migration: picks are read from stored records, MD placement is computed at read
time. Response (contract frozen in wave 0, `contracts/context_layers.py`):

`FormationLayerSet{ wellbore_id | project, frame{origin,datum,exaggeration_neutral}, surfaces[FormationSurface],
conflicts[], unsupported[], generated_from{revision} }`, `FormationSurface{ surface_key, name, tier(T1|T2|T3|T4),
tier_label, picks[FormationPick], plane?{elevation_m, footprint, label}, mesh?{indices,positions,method,support_polygon},
blocked?{reason}, evidence[] }`, `FormationPick{ id, wellbore_id, md, tvd, tvdss, units/datum originals, position_enu,
qualifier, validation_state, evidence }`.

Scene elevation of a pick comes from the trajectory at its MD, so a **single-bore plane needs no datum assumption**;
planes across bores require a shared vertical reference (else blocked per FO-5). Source pick dip/azimuth are attributes
only; planes stay level and say so. Plane footprint: scene bounds plus margin, drawn translucent with outline and grid
(depth-write off, fixed render order); label chips reuse the existing label layer.

The owner-requested fallback (level planes) is consistent with CX-6 only as T2: "flat invented planes" do not satisfy
the pilot's real-context pass (CX-6 needs T3/T4); decision D1.

### 4.2 Charts (FL-025)

Reuse the series store (`series_curve`, kinds log/production, `/series` list+window) for production and pressure
(`AVG_DOWNHOLE_PRESSURE`, `AVG_DOWNHOLE_TEMPERATURE`, `AVG_DP_TUBING`, `AVG_ANNULUS_PRESS`, on-stream hours).
Add `backend/fieldlens/charts/`: (a) wellbore chart-set endpoint scoped by wellbore (series list per wellbore label
resolved through the identity/exposure model, perforation events/state from the PH engine, completion/asset-spec
events), (b) field aggregates computed server-side on full resolution. Perforation history is not exposed by any API
today; the charts lane adds a read endpoint over the existing engine. ECharts is the agreed library and is not yet in
`frontend/package.json`; wave 0 adds it (lockfile serialized). Charts lazy-load as their own chunk.

### 4.3 Camera (FL-026)

Extract camera motion from `Viewer3D.tsx`/`FieldViewer3D.tsx` into `cameraRig.ts` (imperative, refs) with pure planners
`cameraPath.ts` (van Wijk-Nuij smooth zoom-pan, arrival-pose solver keeping the trajectory in view) and
`flyOverPlan.ts` (MD-ordered stops from the scene model + formation/perforation markers, dwell/travel timing).
Existing `frame.go` 0.75 s lerp is replaced behind the same commands (`focus`, `fitAll`, `fitWellhead`) plus
`flyOver()`/`stopFlyOver()`.

### 4.4 Assistant (FL-027)

Reuse `fieldlens.assistant` (WorkUnit, BudgetLedger, Provider incl. fake/stub, bounded tool loop). Add
`backend/fieldlens/chat/` (conversations, turns, tool registry, answer validator, routes), migration `0020`.
Turns run as a persisted job polled by the UI (the repo's existing `usePolled` pattern), not an unbounded stream.
Frontend `features/assistant/` mounts in the Explore dock; link activation goes through a typed `ExploreCommands` bus
(wave 0 seam) so the chat never reaches into scene internals. Chart blocks use the chart components from FL-025.
Chat turns are recorded in the existing ledger for usage visibility but are not blocked by a spend ceiling (D4); the
reconstruction pipeline keeps its own existing limits.

### 4.5 Integration wiring (TASK-105)

`features/scene/exploreEnrichment.tsx` (`useExploreEnrichment`) connects the parts once per Explore stage (wellbore or
field): one formation store + `useFormationLayers`, one chart cursor store, the lazy `FormationLayer` passed as the
viewers' `layers`, `FormationPanel` below the inspector, `ChartPanel` in the `charts` slot (enables the 3D/Charts/Split
switch; the chart set follows the wellbore/field context) and `AssistantPanel` in the `assistant` slot. Each bus
command has one acting path: `focusWellbore/Element`, `flyOver`, `stopFlyOver` -> viewers; `focusFormation` -> the
viewer camera (`makeFocusFormationHandler`, refuses with no motion when the pose is null) plus the panel's selection;
`openChart` -> `ExploreWorkspace` (reveals Charts, applies a complete window, refuses another wellbore/field scope,
unloaded charts and invalid windows); `openSource` -> `SourceViewerHost` (page -> PDF drawer, otherwise Sources tab,
otherwise refused). Fly-over stays a single-wellbore control. The Explore row is a named-column CSS grid that stacks in
DOM order below 960px. Known limits: no as-of picker yet (`as_of` is null for charts and chat); a half-open
`openChart` window is not applied; `selected_surface_key` is not sent; an unplaceable but listed formation is
selected (reported handled) without camera motion.

### 4.6 UX revision after owner manual test (2026-11-04, UX-1..5)

Owner testing of 0.54.0 found layout and camera defects. Requirements (each lane owns its files; no contract change):

- **UX-1 Viewer stability.** The 3D canvas has a fixed, bounded height on the page (it never grows with the side lists; the
  page does not scroll because of the Explore panels). Camera framing (initial fit, Fit field, wellbore view, resets)
  is computed from wellbore/trajectory/equipment bounds only; formation picks, markers and planes are present in the
  scene but are excluded from every bounds/fit/focus-extent calculation. Opening the viewer must not drift to an empty
  or arbitrary view after the first frame. Explicit `focusFormation` still moves the camera to that formation.
- **UX-2 Only drawn formations are listed.** A surface/pick that is not drawn in the current view (plane blocked, no
  placement, other wellbore) is excluded from the formation panel, label lists and counts; blocked reasons are summarized
  once (a single collapsed note "N formations not drawn (reason)"), never repeated as cards. The contract data and
  blocking rules are unchanged.
- **UX-3 Contained cards.** Tree, scene and Inspector (incl. formation panel) have fixed, window-bounded height; each card
  scrolls internally; the page itself does not scroll for Explore content.
- **UX-4 Assistant dock.** Collapsed: a small blinking (respecting `prefers-reduced-motion`) avatar button at the
  bottom-left of the Explore area (no drawer/row). Expanded: an overlay anchored left, full width of the Explore area and
  half of the viewport height, above other elements, closable with Escape and a close button, focus managed. The assistant
  contract and behavior are unchanged.
- **UX-5 Chart cards: overview + full view.** Chart cards on the Charts/Split stage show a light overview (title, scope
  badge, the plot with reduced density and only essential info: no pan/zoom toolbars, data table, notes or long source/exclusion
  lists). Each card has an expand control opening a full-screen modal dialog (focus trap, Escape/close, labelled) with the
  full current detail (toolbars, legend, data table, sources, exclusions, notes). Same data and window state, no refetch.
  Layout columns for the overview cards are denser/more regular; global notes/exclusion banners are collapsed to a summary.

## 5. Failure conditions

No formation picks -> layer shows "no formation picks in this project" and nothing else changes. Pick depth unit/datum
unknown -> marker by MD only, plane blocked with reason. TVD disagrees with trajectory -> conflict listed, plane
blocked for that pick. Series scope ambiguous -> chart shows the ambiguity. Provider failure -> assistant shows state, no
partial fabricated answer. Camera target missing -> command ignored with an announced message. Worst misinterpretation:
an illustrative plane read as a measured horizon, or a well-level series read as one wellbore; both are labeled in-scene.

## 6. Ambiguity audit

"Formation levels" = picks (observed) and planes (illustrative), not reservoir bodies. "Field view charts" = global,
project-scoped, unreconciled-labeled until a published model associates series (FL-010 decision). "Avatar" = persona
with states, not a talking 3D character (D3). "From top to bottom" = wellhead (MD 0) to TD.

## 7. Tests and traceability

Backend: `uv run pytest backend/tests/context backend/tests/charts backend/tests/chat` + contracts + ruff/mypy strict.
Frontend: `npm --prefix frontend run lint && typecheck && test && check:contracts && build`; Playwright for the combined
flow (upload -> wellbore -> formations/fly-over -> charts -> cited chart answer -> link). Fake provider only by default.
Requirement-to-test table: this section plus [specs/README.md](README.md). Mocks/cached replays are labeled as such in
evidence; real-data (F-12/F-14/F-5) checks are separate lines.

## 8. Owner decisions — **approved 2026-11-03 18:47 EST**

| # | Decision | Approved outcome |
|---|---|---|
| D1 | Level planes vs CX-6 | Accept T2 as the labeled fallback; basic reservoir/formation boundaries are enough for now |
| D2 | Pressure/lab-test/DDR event data | Show only existing records; an empty chart state is acceptable. TASK-101 stays an optional spike |
| D3 | "Interactive avatar" | SVG persona with states and reduced-motion support; no voice, no 3D character |
| D4 | Assistant spend | **No spend cap for the assistant: budget treated as unlimited.** Live Meta checks are allowed for the assistant lane (supersedes the USD 1 / USD 5 limits for FL-027 only). Usage is still recorded by the existing ledger, but no per-turn or total spend ceiling blocks a turn. Step/time/tool-call bounds against runaway loops, and every security/grounding rule (read-only allowlisted tools, project scope, no code/SQL/URL execution, validated citations and links), stay |
| D5 | Horizon grid import (FO-7) | **Skipped for now** (TASK-099 deferred; T4 not built) |
| D6 | Fly-over scope | Single wellbore only; field view keeps smooth transitions |
| D7 | Cut line / priorities | **Priorities: production data charts, assistant + avatar, smooth camera.** Formations are basic boundaries (T1+T2, T3 only if time remains) |

Consequences: FO-7 and AV-9's USD 1 ceiling are withdrawn; AV-6's "spend bound" now means step/time bounds only. Dispatch
order follows D7: charts + assistant + camera lanes first, formation lanes in parallel at lower priority.

## Assumption registry

Demo project contains formation picks and the production workbook for F-12/F-14/F-5 (M; verified per lane first step).
Picks resolve to the same wellbore identities as the trajectories (M; FO-1). Series scope by wellbore label maps to
exposed wellbores deterministically (M; XC-2). Assistant tools over existing endpoints suffice for the demo (M; AV-3).

## Revision triggers

Owner rejects D1/D3; picks lack depth units or datum for the demo wells; production series cannot be scoped per
wellbore; fly-over cannot hold frame budget at 3 km depth; chat per-turn cost exceeds the dev cap.
