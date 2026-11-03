# Specification: Explore/Reconstruction polish wave (owner list of November 3)

> **Spec type:** Product/feature (seven lanes).
> **Load-bearing frameworks:** outcome, acceptance, scope.
> **Date:** 2026-11-03. **Author:** orchestrator. **Decision owner:** project owner.
> **Status:** Approved (owner replies of November 3 15:18; plan accepted with the three decisions in section 4).
> **Backlog ID:** FL-023, TASK-086..TASK-092. **Integration version:** assigned serially at merge.
> **Base:** master `cc616df` (0.45.0), Alembic head 0019 (no migration expected).

Umbrella spec for twelve owner items. Lane sections are the per-feature contract; related
behaviour specs ([MERGE_PROPOSALS](MERGE_PROPOSALS.md), [TRAJECTORY_VIEWER](TRAJECTORY_VIEWER.md),
[RECONSTRUCTION_TAB](RECONSTRUCTION_TAB.md)) are updated by the lane that changes them.

## 1. Outcome

After this wave the demo project shows: short-name wellbores (F-5) proposed for merge with their
block-qualified wellbores; source references that name a document, page and statement and open PDFs;
an Explore tab that lists and draws only reconstructed wellbores, placed by surface location, with
visible trajectories, varied materials, a blended selection highlight, a detailed default wellhead and a
trajectory physically connected to the well hole. Verification: independent QA per lane plus one
integrated browser pass on the F-12/F-14/F-5 project.

## 2. Scope

IN: items 1-12 of the owner list. OUT: PDF.js, Blender assets, map projections or CRS reprojection,
re-running S5 to improve evidence, any live Meta spend by default tests, new migrations (Alembic 0020 reserved for lane A only if unavoidable).
Cross-cutting rules: fake provider in default tests; contracts/generated client/VERSION/CHANGELOG touched only
as stated in section 5; engineering calculations never read display-only data (tie-in, generic geometry, layout offsets).

## 3. Lanes and acceptance criteria

### A (TASK-086) S3 short-name matching, items 1
Cause (verified in the app DB): unqualified `F-5/F-12/F-14` are separate wellbores by the D9 rule; `identity_merge` and
`merge_proposal` are empty; the third S3 run succeeded with `{"groups":[]}` and the fingerprint cache then answers "no new
matches; earlier results were reused" forever. The G7 guard needs one verbatim quote naming both spellings from one document;
the survey text file (unqualified) and the survey PDF/1.xml/EDM records (qualified) do not share one.
Design (owner-decided): the **agent still decides**. Keep the model step, but feed it a compact deterministic candidate table per
block (pair, name similarity, same slot, shared-source family, survey fingerprint equality: station count/MD range/md-incl-azi
hash, same surface location, field/project context) and give it enough output and reasoning budget (no truncation; keep the
TASK-084 retry; size the output bound to block count). A pair may be proposed on a verbatim quote **or** on deterministic content
evidence (`evidence_kind`), still `pending`, still user Accept/Reject, guards G1-G6 unchanged, no auto-apply.
| ID | Criterion |
|---|---|
| A-1 | On a fixture mirroring VOLVE (F-5/F-12/F-14 short bores with identical survey fingerprints to their `15/9-` bores) fake provider returns groups -> 3 pending proposals with content evidence shown in the review UI. |
| A-2 | Guards still block: different slot, different block-qualified bore (e.g. `15/9-F-5` vs `15/9-F-5 A`), planned vs as-built, sidetrack, contradictory surface location. |
| A-3 | A previously succeeded run with 0 proposals is re-planned when the candidate evidence/guard/prompt version changed; the stage message distinguishes "model found none" from "reused" and states why. |
| A-4 | Provider output truncation/malformed still handled (existing TASK-084 tests green); estimate shown before a run; no live call in default tests. |
| A-5 | Accepting a proposal makes the qualified bore show the surface location (identity apply path unchanged). |
Owner: fieldlens-rag. Paths: `backend/fieldlens/merge_proposals/*`, `backend/fieldlens/reconstruction/matching.py`, `frontend/src/features/merge/*`, MERGE_PROPOSALS spec.

### B (TASK-087) Document content and readable evidence (backend), items 2, 6, 8
New `GET /api/v1/projects/{p}/documents/{d}/content`: project-scoped, PDF only (415 otherwise), `Content-Disposition: inline`,
stored sha256 verified, `X-Content-Type-Options: nosniff`, restrictive CSP, Range support, never a path from the client.
Evidence: `EvidenceRef` gains optional readable `locator` and `statement` (and filename); composed at read time from stored record
attributes (original text, locator); no document re-read, no S5 rerun; existing specs improve automatically. Trajectory set/survey
reference carries `document_id` and `page`.
| ID | Criterion |
|---|---|
| B-1 | Content route returns the original PDF bytes with the headers above; Range returns 206; another project's document 404; non-PDF 415; missing/tampered blob returns a typed error, not a 500. |
| B-2 | Evidence for a structured component returns filename + locator + statement instead of `extracted_record <uuid> ...`; cost is O(components) with no extra document I/O (test asserts query count). |
| B-3 | Survey/trajectory response includes `document_id` and `page` for the chosen survey set. |
| B-4 | Contracts registered and `check:contracts` clean after regenerating; OpenAPI diff documented. |
Owner: fieldlens-backend. Paths: `backend/fieldlens/ingestion/routes.py` (+ new module), `assetspec/structured.py`/evidence read path, `contracts/asset_spec.py`, trajectory source ref, generated client.

**B as implemented (TASK-087).**
- Route `GET /api/v1/projects/{p}/documents/{d}/content` (`ingestion/content.py`): lookup by project and document id only (the storage
  key comes from the row, never the client); `format_family != pdf` -> 415 `UNSUPPORTED_MEDIA_TYPE`; stored size and SHA-256 are verified by
  streaming (result remembered per file identity: path, inode, size, mtime, so a viewer's range requests do not re-hash); missing or
  damaged blob -> 409 `CONFLICT` with `details.reason` in `missing|size_mismatch|hash_mismatch` (nothing is written by a GET). Body is
  streamed from disk; one `Range` (206/416; multi-range refused), `ETag` = quoted sha256 with `If-None-Match` -> 304.
- Headers: `Content-Type: application/pdf`, `Content-Disposition: inline; filename="<ascii-safe>"; filename*=UTF-8''<pct>`,
  `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'`, `Cache-Control: private, max-age=300`. `sandbox` is
  deliberately not in the CSP and no `frame-ancestors`/`X-Frame-Options` is sent: Chromium's built-in PDF viewer does not render a
  response under CSP `sandbox` (known limitation), and the viewer frame is same-origin (Vite proxies `/api`). Not browser-verified in this
  lane (no browser allowed); lane C must confirm the iframe renders and must not add an iframe `sandbox` attribute that blocks the viewer.
- Evidence: `EvidenceRef` gains optional `filename`, `locator` (e.g. `page 3, table 2, row 5`) and `statement` (e.g.
  `Casing 9 5/8" at 2,431 m MD`). They are composed at read time (`assetspec/readable.py`) from the document row and the
  `extracted_record` named by the stored quote (`extracted_record <uuid> ...`); two batched queries per read (history included), no file
  I/O, never stored (`service._stored` strips them, and the unchanged-spec comparison ignores them, so old specs cause no new revision).
  A record that no longer exists degrades to filename + `page N`. Non-structured (model) evidence gets filename and page locator only.
- Survey: `TrajectorySetRef` (already `document_id`, `filename`) gains `page` (first station's page when the locator has one, else null).
- OpenAPI diff: one new path, `EvidenceRef` +3 nullable fields, `TrajectorySetRef` +`page`; nothing removed or renamed.

### C (TASK-088) Source links and embedded PDF viewer (frontend), items 2, 6, 8
Shared `SourceLink` + `DocumentViewer` (right drawer, sandboxed `<iframe>` of the content route, `#page=N`, Escape closes, focus returns).
Used in the Reconstruction list, upload list, Inspector evidence and Survey info. Non-PDF -> existing jump to the Sources row. No PDF.js.
Never shows a bare UUID as link text. Depends on B contract.
| ID | Criterion |
|---|---|
| C-1 | Clicking a PDF source in Reconstruction list, upload list, Inspector evidence or Survey info opens the viewer at the stated page. |
| C-2 | Evidence rows show filename, locator and statement; missing statement falls back to filename + locator, never a bare UUID. |
| C-3 | Keyboard/ARIA: dialog role, focus trap/return, Escape; viewer error state when content route fails. |
| C-4 | No new bundle dependency; viewer code lazy-loaded; frontend lint/typecheck/test/build green. |
**C as implemented (TASK-088).**
- `features/documents/SourceLink.tsx`: `<SourceLink projectId documentId filename? page? locator? statement? format? onOpenSource?>`.
  PDF (`format === "pdf"`, or without a format a `.pdf` file name) -> a button (`aria-haspopup="dialog"`, name "Open X in viewer at
  page N") that lazy-loads `DocumentViewer`; anything else -> the existing link "Open X in Sources" (`onOpenSource` jump, else the
  Sources tab). Text: file name, `(locator)`, statement as `<q>`; no file name -> "Document (filename unavailable)"; no bare UUID anywhere.
- `DocumentViewer` (own 6 kB chunk, no dependency): Mantine right drawer, `role="dialog"` labelled by file and page, focus trap, Escape
  closes, focus returns to the trigger (done by `SourceLink`, since the viewer unmounts). On open it makes one `Range: bytes=0-0`
  request to the content route so 409 (with `details.reason` text), 415, 404, 503 and network errors appear as an alert; otherwise a
  same-origin `<iframe src=".../content#page=N">` (no `sandbox`) plus an "Open in new tab" link (`target=_blank rel=noopener`).
  No per-row requests; nothing is fetched until a link is opened.
- Used by: Reconstruction Sources column and run draft evidence (page = first `locator.page`), upload list ("Open PDF" for stored
  PDFs), Inspector evidence (`filename`, `locator`, `statement`, falling back to `page N` and the raw quote) and Survey info (file
  name links at `survey_set.page`; `SurveyInfo.source` added). The Inspector reads the project id from the route when no prop is given.
- Browser check (Chromium 156 in the test browser container, same-origin iframe, `#page=2`, 3-page PDF): the built-in viewer renders
  page 2 with no CSP and with `Content-Security-Policy: default-src 'none'`; the response headers of the route need no change.
  Not checked: Firefox/Safari viewers; the full app flow against the real API (covered by vitest with a mocked `fetch`).
Owner: fieldlens-frontend. Paths: `frontend/src/features/documents/*` (new), `pipeline/ReconstructionList.tsx`, `uploads/DocumentList.tsx`, `scene/Inspector.tsx`, `scene/trajectorySource.ts` (SurveyInfo only).

### D (TASK-089) Reconstructed-only field view, true placement, default thickness, items 3, 4, 5, 7
| ID | Criterion |
|---|---|
| D-1 | Project tree, field scene and single-view dropdown list/draw only wellbores that have an asset spec; the summary line keeps total/unreconstructed counts. Trajectory/spec requests are issued only for those wellbores. |
| D-2 | When all placed wells share one CRS, datum and unit, positions are planar E/N offsets from the placed set's centroid; otherwise the labelled schematic grid. No reprojection, no guessed CRS. |
| D-3 | Wells a few metres apart (same platform) do not overlap: glyph/pad size derives from the nearest-neighbour distance; camera frames the spread and the deepest trace. |
| D-4 | Default trajectory tube radius equals the selected-state radius (`max(0.05, exaggeration*0.035)` rule) so traces are visible without clicking; selection still distinct. |
| D-5 | Layout label states "surface-location layout" vs "schematic layout"; unit/CRS/datum per well kept in the inspector. |
Owner: fieldlens-3d-motion. Paths: `scene/FieldScene.tsx`, `fieldModel.ts`, `fieldData.ts`, `trajectoryData.ts`, `FieldViewer3D.tsx`, `ExploreScene.tsx` (dropdown filter only).

### E (TASK-090) Wellbore single view placement and wellhead presence, items 11, 12 (frontend)
| ID | Criterion |
|---|---|
| E-1 | The single wellbore canvas no longer draws the "unlocated components" tray; those components remain in the list and inspector (selectable, info shown). |
| E-2 | A wellhead is always drawn at the well hole; with no wellhead in the spec the default generic wellhead (labelled "default") from the field view is used. |
| E-3 | Trajectory, casing/tubing/hole sections and MD-placed components start at the well hole with no visible gap, using lane F's tie-in segment (MD 0 to first station) with the depth records unchanged (formation-top overlay stays valid). |
| E-4 | Components with MD above the first surveyed station are placed on the tie-in; absence of the tie-in leaves the existing warning, no invention. |
Owner: fieldlens-3d-motion. Paths: `scene/sceneModel.ts`, `Viewer3D.tsx`, `trajectory.ts`, `ComponentList.tsx`. Depends on F.

### F (TASK-091) Wellhead tie-in segment (backend), item 12
Owner decision: preserve depth records for formation tops, make the connection look physical, a bent additional segment is allowed.
Rule: when the first station's MD > 0, add a derived `tie_in` segment from the wellhead (MD 0, TVD 0, origin) to the first station.
If first-station TVD ~ MD and inclination ~ 0 (within tolerance) it is vertical; otherwise use a minimum-curvature smooth
arc (zero tangent at the wellhead assumed vertical -> first station tangent; never invented dogleg beyond the segment) when the
required curvature is physically plausible, else vertical plus explicit warning. All of it flagged `derived` and display only;
survey stations, TVD/MD/depth records, perforations and formation overlays are unchanged; calculations ignore it.
| ID | Criterion |
|---|---|
| F-1 | F-5 PDF set (first station MD 145.9, TVD 145.9, incl 0): response contains a vertical tie-in 0 -> 145.9 and total surveyed stations unchanged. |
| F-2 | First station inclined (fixture): tie-in is a smooth arc ending exactly on the first station with matching tangent; TVD of every real station is untouched. |
| F-3 | Tie-in has `derived=true` kind and a warning/label code; closest-approach/perforation/length analytics are byte-identical with and without it. |
| F-4 | First station already at MD 0: no tie-in. Missing TVD/inclination: no tie-in, existing warning. |
Owner: fieldlens-geospatial. Paths: `wellpath/service.py`, `contracts/trajectory.py`, engineering tests, TRAJECTORY_VIEWER spec.

### G (TASK-092) Material fidelity, blended highlight, wellhead detail, items 9, 10, 11 (wellhead)
| ID | Criterion |
|---|---|
| G-1 | Distinct material roles with different roughness/metalness and clearer colour separation: cement matte, casing brushed steel, tubing lighter metal, painted equipment matte, perforations bright; nothing uniformly glossy. The `cement` and `openHole` roles are defined and available in the material table/palette but are not yet consumed by any component kind (no `ComponentKind` exists for them; no consumer is invented here). |
| G-2 | Selection highlight blends with the object colour (a lerp/tint plus reduced emissive, target about 30-40 %), the base colour stays readable; non-selected context optionally dimmed (`setDimmed` is an available helper, not yet wired into any viewer). Warm roles near the amber accent use a cool tint so every role reaches a linear-RGB selection distance of at least 0.25. |
| G-3 | Procedural multi-colour wellhead (body, valves/handwheels, flanges, bolts) in both field glyph and single view; no new GLB, no per-frame allocation, resources disposed. |
| G-4 | Existing scene tests green; draw-call/triangle count of the default scene does not grow more than 20 % (measured). |
Owner: fieldlens-3d-motion. Paths: `scene/resources.ts`, `primitives.ts`, `design/scenePalette.ts` only.

## 4. Decisions

- Item 12: depth preserved, additive tie-in (vertical, or smooth bend when needed), display-only. [Validated: owner Nov 3]
- Item 2/6/8: native browser PDF viewer in an embedded frame now; PDF.js later. [Validated: owner Nov 3]
- Item 1: deterministic evidence is allowed, but the agent still decides over candidates, similarity and project context with enough thinking budget; user accepts. [Validated: owner Nov 3]
- Execution is waved because the host has 7.7 GB RAM: at most two writers/test runs at a time.

## 5. Delegation

Base `cc616df` plus this spec commit; worktrees `/home/slimco/code/FieldLens-worktrees/<lane>`, branch `feature/task-0NN-...`, own `./dev` lane.
Orchestrator serializes VERSION, CHANGELOG, contract registry/generated client (B first), Alembic head. Waves: W1 = A + B; W2 = F + G;
W3 = D + C; W4 = E. Merge order B, F, A, C, D, E, G, each rebased and re-checked, one bump each. Independent QA (fieldlens-qa) per lane.
