# Changelog

Human-readable changes by integration version. Versions use major.minor.patch:
breaking changes increment major, features minor, fixes/documentation patch.
See the [workflow](docs/DEVELOPMENT_WORKFLOW.md) for classification and merge rules.

## Unreleased

No unreleased changes.

## 0.55.0 - 2026-11-04

### Added

- Model processing reads scanned PDF pages visually: pages without a text layer are rendered and sent as images, with an image-token cost in the estimate. Names read from images are stored as proposals marked "read from image, unverified" and never auto-link (TASK-115).
- Non-PDF documents (text including `.ascii`/extension-less/any text-decodable file, csv, xml, las, xlsx, and a bounded binary preview) can be estimated and read by the model as sections (TASK-115).
- New setting `FIELDLENS_PROCESSING_IMAGES_PER_CALL` (default 4); migration 0021 adds `read_mode` columns; prompt version `doc-identity-2`. A legacy empty "no text layer" result is no longer a cache hit.

### Known limitations

- Live Meta image input is not verified; the processing dialog's section wording and the "unverified" badge in the results panel are not yet implemented (only the estimate callout wording changed).

## 0.54.2 - 2026-11-04

### Fixed

- Assistant launcher is now a single project-level control fixed at the bottom-right of the screen, present on every project tab and keeping its conversation across tab switches; links clicked on another tab switch to Explore first (TASK-114).

## 0.54.1 - 2026-11-04

### Fixed

- Explore 3D viewer: a canvas resize no longer re-fits the camera, so the framing no longer drifts to a blank view after load; the canvas height is bounded and formation layers are flagged out of fit bounds (TASK-111).
- Explore layout: fixed-height workspace with Tree, scene and Inspector cards scrolling internally instead of the page (TASK-112).
- Formations panel lists only surfaces drawn for the current view (identical rows merged with a count) and collapses the rest into one "N formations not drawn" summary (TASK-112).
- Assistant is a pulsing round launcher at the bottom-left that opens a full-width, half-height overlay panel (TASK-112).
- Charts: cards are light overviews with an expand button opening a full-screen detail dialog (toolbar, legend, data table, sources, notes); global notices collapse into one summary row (TASK-113).

## 0.54.0 - 2026-11-04

- **Explore enrichment (FL-024..027, TASK-096..110).** Formation tops as observed markers and labelled "level plane - illustrative" planes in both 3D views (never exaggerated, blocked across wellbores with differing/unknown vertical references), with a formation panel. Charts: wellbore-scoped set (production/injection, cumulative, pressure, on-stream, perforation timeline, `log_tracks` with formation-top lines) and field set (by-wellbore rates, cumulative, uptime, perforated length, `stratigraphic_correlation`) behind a 3D / Charts / Split stage, with an as-of date control and a "Show in 3D" action on formation-top lines; unknown perforation baselines show as gaps, never zero. Camera: smooth van Wijk transitions between elements facing the trajectory, and a single-wellbore "Fly over" that tours the trajectory top to bottom, highlighting the visited element. Assistant: expandable project chat with an SVG avatar, typed answer blocks, server-materialized charts, validated deep links (sources, elements, wellbores, formations, charts), read-only allowlisted tools (evidence search, trajectory, series, formations, equipment), no spend cap (D4), migration 0020. Slug element ids in chat contracts; regenerated client. Backend pytest, ruff, mypy; frontend 626 vitest tests, lint, typecheck, build and `check:contracts` pass. Not browser-verified, frame time (CM-6) unmeasured, live Meta (AV-9) not run. Known limits: no horizon grids/interpolated surfaces (D5), no chart-to-3D hover (button instead), no closest-approach chat tool, perforated length mostly "unknown" on real data.

## 0.53.1 - 2026-11-03

- **TASK-094b Explore contract hardening.** Truthful tier/plane/pick labels, a shared stated vertical reference required for project-scope surfaces, chart-series integrity checks (aggregates, gaps, downsample, units, scope), strict chart window bounds, degenerate-mesh rejection, and no datum on MD or scene-elevation depths. Field names and the OpenAPI schema are unchanged. Ruff, mypy, 82 contract tests, `check:contracts` and typecheck pass.

## 0.53.0 - 2026-11-03

- **TASK-094 Explore enrichment contracts (FL-025-A).** DTO-only contracts for formation layers (pick/level plane/surface tiers with explicit vertical reference and evidence), wellbore/field chart sets, and chat (typed `AppLink`, answer blocks, turns, run states), registered and exported to `generated.ts`; `echarts` 6.1.0 added. No behavior. Ruff, mypy, 77 contract tests, `check:contracts`, typecheck and lint pass.
- **TASK-095 Explore scene seams (FL-026-A).** Optional `layers` slot inside both viewer Canvases, a typed ref-based Explore command bus (focus/openSource/openChart, fly-over stubs) and 3D/Charts/Split stage regions with an assistant dock slot; no visual change until a charts slot is supplied. Lint, typecheck, 421 vitest tests and build pass; not browser-verified.

## 0.52.1 - 2026-11-03

- **TASK-093 Field-view trajectories stay visible at overview zoom.** The integrated browser pass showed the tubes as faint dotted lines at the default zoom. Each field-view trajectory now also has a 3 px screen-space minimum-width line (one merged `LineSegments2` for the whole field, +1 draw call; picking selects the well); the world-space tube is unchanged and covers the line when zoomed in. Lint, typecheck, 407 vitest tests and build pass; not browser-verified (owner testing manually).

## 0.52.0 - 2026-11-03

- **TASK-090 Wellbore view always shows a wellhead, drops unlocated blocks and joins the trace to the well hole.** Unlocated components are no longer drawn (the tray is gone) but stay in the component list and inspector and remain selectable. A generic default wellhead (labelled "default, generic: not from the sources", not a component, not counted) stands at the origin whenever the spec has no placed wellhead; a christmas tree always stands on a wellhead. The trace starts at the well head using the backend's derived, display-only `tie_in` (vertical or bent arc, labelled "Derived tie-in, display only (not surveyed)"); MD/TVD depth records and formation-top overlays are unchanged, components above the first station are placed by MD along the tie-in, and station counts use real stations only. The dead "Unlocated" view button was removed. Not browser-verified (visual look of the junction and default wellhead). Known low edges: a tie-in whose last point is within 1 mm of the first station could leave a zero-length segment; a wellhead component placed at depth suppresses the default surface wellhead.

## 0.51.0 - 2026-11-03

- **TASK-088 Source links open PDFs in an embedded viewer.** Reconstruction sources and draft evidence, the upload list ("Open PDF"), Inspector evidence and Survey info open the stored PDF in a lazy-loaded right-hand drawer at the stated page (browser's built-in viewer, `#page=N`, no sandbox, "Open in new tab" link). Evidence shows file name, locator and quoted statement instead of document ids ("Document (filename unavailable)" when unknown). One `Range: bytes=0-0` probe maps 409/415/404/503/network errors to a visible alert; nothing is fetched until a link is opened. Chromium rendering under the content route's CSP was checked only with a hand-made PDF on a loopback server, not the real API. PDF-ness for reconstruction evidence and survey sets comes from the `.pdf` file name.

## 0.50.0 - 2026-11-03

- **TASK-089 Explore lists and draws only reconstructed wellbores, placed by surface location.** The Explore tree, the field view and the single-view dropdown show only wellbores with an asset spec (a 200 on the per-wellbore asset-spec read; failures stay listed with Retry; summary counts keep the total, unreconstructed, failed and loading numbers); survey reads are issued only for them. Wells are placed at E/N offsets from the centroid of the located wells (double precision, then float32) when all share the same stated CRS, datum and metre unit, otherwise the labelled schematic grid; a well with no location waits in a labelled "unlocated" row; no reprojection or CRS guessing. Pads and glyphs scale to the nearest-neighbour spacing (same-platform wells are 1-2 m apart) and the camera frames the spread and the deepest trace. Trajectory tubes use the selected-state radius by default. Not browser-verified. The qualified bores (`15/9-F-n`) carry no surface location until their short-name merge is accepted.

## 0.49.0 - 2026-11-03

- **TASK-092 3D material fidelity, blended selection highlight, detailed wellhead.** Element roles now have distinct finishes and clearer colour separation (matte cement/open-hole/rubber roles, brushed casing steel, lighter tubing, satin paints) instead of uniform gloss; the selection highlight tints the object's own colour (35 % toward amber, a cool tint for warm-hued roles such as perforations, own-hue emissive at 0.28) instead of overlaying it; the procedural wellhead has a blue-grey spool, dark flanges with instanced studs and a brass ring, red/blue gate valves with contrasting handwheels and a gauge. Default f14 scene cost: -2 % triangles, +2 % draw calls. Visual look not yet browser-verified; `cement`/`openHole` roles and the `setDimmed` helper exist but no viewer consumes them yet.

## 0.48.0 - 2026-11-03

- **TASK-086 S3 matches short wellbore names (F-5, F-12, F-14) to their block-qualified bores.** The earlier "no new matches; earlier results were reused" was a cached empty answer: the model needed a quote naming both spellings in one document, which the data never contains. S3 now gives the model a deterministic candidate table (name similarity, same slot, source families, survey fingerprint comparison, surface-location comparison) and the model still decides; a pair may be proposed on a quote or on server-verified survey content (`evidence_kind: survey_match`, shown as "Matching survey"). Proposals stay pending for Accept/Reject. New guard G8 blocks contradictory surface locations (accept re-checks it). An empty result is re-planned when evidence, guards or the prompt change, and the stage message says whether the model found none or results were reused. S3 uses medium reasoning effort with a larger output bound (8192 + 1024 per block, retry at minimal with double), reserved USD 0.60 per call (worst case 1.80 per run); the internal provider request cap rose to 32768. No migration. Not yet verified with live Meta.

## 0.47.0 - 2026-11-03

- **TASK-091 wellhead tie-in segment in the trajectory response.** When a survey starts below the wellhead (F-5: first station MD 145.9, TVD 145.9, inclination 0), `GET .../trajectory` adds a derived, display-only `tie_in` (vertical, or a smooth bend that ends tangent to the first station when physically plausible, max 10 deg/30 m) from MD 0 to the first station, with `TIE_IN_DERIVED` / `TIE_IN_NOT_DERIVED` warnings. Surveyed stations, MD/TVD values and every calculation are unchanged; the trace is not translated. Limit: an inclined first station that is not a plausible continuation of a vertical hole gets no tie-in (the gap and a warning remain).

## 0.46.0 - 2026-11-03

- **TASK-087 document content route and readable evidence.** New `GET /api/v1/projects/{project_id}/documents/{document_id}/content` streams the original PDF (project-scoped, PDF only, stored size and sha256 verified, single Range, `nosniff`, CSP). Asset-spec evidence now carries `filename`, `locator` and a readable `statement` composed at read time from the stored record (two batched queries, no file I/O, nothing persisted, so existing specs improve without re-running S5). The survey set reference carries the PDF `page`. Additive contract change. The built-in PDF viewer under the CSP is not yet browser-verified; the source-links lane checks it.

## 0.45.0 - 2026-11-03

- **TASK-085 S5 "Design 3D asset" uses all sources.** F-5 no longer reports "no equipment data". S5 builds components deterministically from the native parser records (casing points, tubular assemblies/components, wellbore geometry sections, BHA runs, perforation intervals) with printed dimensions and record evidence, plus model-read candidates, plus a bounded, cached equipment sweep of the wellbore's documents (PDF pages read with the existing candidate harness; survey/trajectory/production/log PDFs are skipped; no USD gate of its own; per-document failures isolated; transient failures re-read next time). A casing shoe at the end of its string is folded into one labelled component with both records as evidence; intervention tools (BHA run, running tool, spear) are not drawn and are named in the stage message; conflicting source dimensions are shown generic with a note. Without a model the spec is built from structured records only; the model only labels. Missing or conflicting dimensions stay generic and never enter engineering calculations.

## 0.44.1 - 2026-11-03

- **TASK-084 fix: reconstruction S3 "Match wellbores" failed `output_truncated` on real Meta.** S3 and S5 ran at the provider's default (high) reasoning effort, which used up the output bound. They now run at low effort, a truncated reply is retried once with minimal effort and a doubled bound in the same reservation, the failed stage records the real tokens and USD, and the message reads "The model ran out of output space; try again (a retry was already attempted)" (code `output_truncated`).

## 0.44.0 - 2026-11-03

- **TASK-083 the 3D views draw the real survey.** New read-only `GET /api/v1/projects/{project_id}/wellbores/{wellbore_id}/trajectory`: the wellbore's validated as-built survey, minimum-curvature local offsets from the wellhead computed in double precision, MD/TVD references, units and the surface location with its stated CRS/datum preserved (never assumed), display-only downsampling with source/displayed counts, and the sets not drawn with reasons. A set whose north reference is not stated is blocked, not guessed. The wellbore and field views fetch it per wellbore; located equipment sits on the real trace; a wellbore without a valid survey keeps the labelled placeholder with the reason. The field view keeps its schematic grid.

## 0.43.1 - 2026-11-03

- **TASK-082 final-QA polish.** The "illustrative" badge text now meets contrast (7.5:1); both 3D canvas wrappers have
  a `group` role; focus returns to the wellbore list after "← Field view" and to Revert (Accept) or the proposal row
  (Reject/Revert) in merge review; the stale shell.spec UI-2/UI-10 assertions are updated; the e2e runner always uses a
  fresh per-run storage root (opt in to a persistent one with `FIELDLENS_E2E_STORAGE_ROOT`).

## 0.43.0 - 2026-11-03

- **TASK-079 the agent now designs the 3D asset (stage S5).** For each wellbore of a reconstruction run, S5 asks the
  configured model to label and classify the wellbore's equipment (downhole and surface: casing, tubing, packer, pump,
  wellhead, tree, choke, manifold, separator, tank, flowline and more) and builds a visual-only asset spec. The server,
  not the model, sets dimensions (only printed numbers), placement (a located part needs a complete printed MD
  interval, otherwise it goes to the unlocated tray, and never beyond the known well depth) and evidence. The latest
  valid spec is shown directly; earlier ones stay as history. A refusal, truncation, malformed answer or provider
  failure leaves the current 3D model unchanged and the run partial. Without a model, S5 reads "Not available: no model
  configured". No spend limit applies to a confirmed run; the estimate is information only.
- **Bounded public visual references.** An allowlisted research tool can look up public pictures for named equipment
  (6 queries, 10 pages, 120 s per component, 8 components per wellbore, stored as URL, retrieval date and an optional
  verified image). It is off by default with no search backend shipped (`FIELDLENS_VISUAL_RESEARCH_BACKEND`, only `off`).
  SSRF-safe: public http/https addresses on ports 80/443 only, IPv6 transition ranges rejected, pinned connection,
  re-validated redirects, size and total-time budgets, cancel honoured, page text never reaches the model.

## 0.42.0 - 2026-11-03

- **TASK-080 field view: all wellbores of a project in one 3D scene.** Explore opens in the field view when a project has
  two or more wellbores. Each wellbore is a labelled pad with a wellhead glyph and a trajectory tube; wellbores without a
  visual asset spec show as placeholders and a failed load shows "Asset specs failed to load" with Retry. Select from the
  list or the scene to fly to a wellbore, open it in the single-wellbore view, and return with "Field view".
- Positions are a labelled schematic grid ("Schematic layout, not map positions"); the permanent "Illustrative visual -
  not an engineering model" badge stays. Shared instanced geometry keeps draw calls flat (7-8 for 3 and 12 wellbores on
  software rendering). Resources are released on tab switch and the WebGL2 probe no longer leaks a context. Lazy chunk.

## 0.41.0 - 2026-11-03

- **TASK-078 the first 3D view: a labelled equipment viewer in Explore.** It renders a wellbore's visual asset spec with
  downhole and surface primitives (casing, tubing, packer, pump, plug, wellhead, Christmas tree, choke, manifold,
  separator, tank, flowline and more), every element labelled, with orbit, selection by click or keyboard list, fly-to,
  and an inspector showing label, kind, placement, representation, evidence and visual reference.
- It opens on the wellhead with surface facilities; "Fit whole well" shows the full depth. Casing radius is exaggerated
  for visibility (5x for deep wells, labelled). Components without supported placement sit in a separate "Unlocated"
  tray, never at an invented depth. A permanent "Illustrative visual - not an engineering model" badge is shown; with no
  survey the trajectory is a vertical line labelled "trajectory unavailable".
- Lazy-loaded chunk (the main bundle has no WebGL code), on-demand frame loop, resources disposed on unmount, list
  fallback when WebGL2 is unavailable. New dependencies: three, @react-three/fiber, @react-three/drei.

## 0.40.0 - 2026-11-03

- **TASK-076 reconstruction in plain stages with wellbore merge review.** The run now has five stages: Collect sources,
  Read documents, Match wellbores, Assemble data and Design 3D asset, each with a plain description, a "uses a model"
  tag, new/reused counts and an information-only cost. No remaining-budget row.
- **Wellbores that are the same are proposed, never merged silently.** Match wellbores proposes aliases (for example
  "15/9-F-12" and "F-12") with the quoted evidence; nothing merges until you click Accept in the merge review, and an
  applied merge can be reverted. Different designators and parent/sidetrack pairs are not proposed.
- The document read and the matcher use the configured model when the processing runtime is live; without a model the
  stages read "Not available: no model configured" and the run ends partial. S3 never re-asks decided or unchanged
  pairs (no repeat spend), runs once per project in bulk runs and honours cancel. The 3D step reads "not available yet"
  until the asset designer lands.
- Accepting or reverting a merge invalidates the affected wellbores' current visual asset specs. New migration 0018.

## 0.39.0 - 2026-11-03

- **TASK-075 model processing: you choose the pages and the estimate is honest.** The estimate dialog has a page count
  (1..total, default 5, always pages 1..N). The estimate is computed from the real text of the selected pages with the
  same bound the runner enforces, so the 0.37.1 "budget does not cover this call" failure cannot recur. It is an upper
  bound for one attempt per call; a retry gets reservation headroom and a recovered retry never fails the run on cost.
- A confirmed run is the authorization: no run cap, total cap, per-call ceiling or "Remaining budget" on the model
  route (the stub route keeps its old gates). Selections over `FIELDLENS_PROCESSING_PAGES_PER_CALL` (default 10) pages
  run as sequential calls; a failing chunk fails the document naming the chunk; nothing partial is stored as success.
  Pages without a text layer are counted and listed; an image-only selection ends with a "no text layer" outcome and no
  spend. Estimate details survive an API restart. Deprecated variables are marked in `.env.example`.
- Processing tests no longer depend on exported `FIELDLENS_PROCESSING_*` / `MODEL_API_KEY`.

## 0.38.0 - 2026-11-03

- **TASK-077 visual asset spec (`VisualAssetSpec`):** a typed, declarative description of a wellbore's visual 3D asset:
  downhole kinds (casing, liner, tubing, packer, ESP pump, valves, perforation interval, wellhead, tree and others) and
  surface facilities (separator, choke, manifold, tank, flowline, surface pump). Placement is located (MD interval),
  unlocated or surface; every component needs a visible label; generic components carry no numbers and source-dimensioned
  ones need evidence. A server validator drops invalid components with findings (invisible labels, control characters,
  deep nesting, bad URLs/images) instead of guessing.
- Stored per wellbore with revision history (migration 0019): the latest valid spec is current, earlier ones superseded,
  a failed generation leaves the current one untouched; there is no accept step. A deterministic stub designer builds a
  spec from equipment candidates. Routes: get current, history, generate. Purged with the project.
- Visual only: nothing here enters engineering calculations or published claims. Fixture specs for the 3D viewer included.

## 0.37.1 - 2026-11-02

- **TASK-074 live model processing no longer fails on an unconfirmed budget balance:** every live run of 0.37.0 failed
  with `provider_error: provider_unavailable` because the `processing-live` budget period never had a confirmed starting
  balance and nothing offered a way to set it. The period is now set up automatically (balance = ledger cap) when the
  live runtime starts, including an existing period with no balance; other periods are untouched. The user's manual
  confirm of an estimate in the UI remains the spend authorization.
- A failed document now states the safe reason (unconfirmed balance, paused period) in its failure message and writes one
  structured log line (run id, document id, code, reason; no key or document text).
- `FIELDLENS_PROCESSING_RUN_CAP_USD` is optional (blank means no per-run cap). Remaining limits: total processing cap
  (`FIELDLENS_PROCESSING_TOTAL_CAP_USD`, 5), per-call reservation 0.50, model pages (5).
- Known gap: an unrecorded pricing revision (only by manual row deletion) shows a step error, not the stated reason.

## 0.37.0 - 2026-11-02

- **TASK-072 re-processable, observable model processing:** "Process with model..." is available in every state and is
  labelled "Re-process with model..." once a run or result exists. A re-process forces a fresh read
  (`ProcessingEstimateRequest.force`); an opt-in "Reuse stored result" checkbox reuses the cache with no provider call.
  Each document shows its run history (state, provider/model, pages, tokens, USD, cache hit, forced) and a collapsible,
  plain-text raw model reply (bounded to 8 KiB, never rendered as HTML). New `GET
  /api/v1/projects/{p}/processing/documents/{d}/outcome`; `/processing/documents` carries `provider_info`.
- **Honest stub and misconfiguration:** a stub run is labelled "Stub run" and states that no model was called. A meta
  provider with missing key, rates or run cap now starts the app on the stub and answers estimate/confirm/retry with 409
  `CONFLICT` `details.reason=provider_misconfigured` listing the missing variable names; the UI disables the action.
- **Config:** unprefixed `PROCESSING_*` keys in `.env` are ignored by settings (prefix is `FIELDLENS_`); startup now logs
  one warning per such key naming the prefixed variable, without values. `.env.example` and `scripts/init_env.py` list
  the prefixed keys. Blank prefixed values count as unset.
- **Test safety:** `scripts/run_e2e.py` and the backend test conftest pin the stub provider and blank `MODEL_API_KEY`
  regardless of `.env` or ambient environment.
- **Project sidebar:** the delete icon is inline on the project row; long names truncate with a title.
- **Migration 0017:** `document_model_result.raw_reply` / `raw_reply_truncated`, `processing_run.force_refresh` / `model`;
  drops the unique cache-key constraint so forced runs can add rows (downgrade keeps the newest row per key).
- Live Meta processing is still unverified (stub and fake-provider tests only). Known polish items are tracked as TASK-073.

## 0.36.0 - 2026-11-02

- **TASK-055 model-assisted identity for PDFs without a native profile:** the Sources panel shows "No native parser; model
  processing available" with a **Process with model...** action that uses the estimate -> confirm flow. The model reads a
  bounded page sample (default 5, `PROCESSING_MODEL_PAGES`) and records a category and tags plus wellbore identity
  proposals with page and quote, shown as "Model-read, unverified". A failed or missing classification falls back to
  "Others (unclassified)" (`general_report` + tag `unclassified`) without failing; no identity gives a non-blocking
  warning. A user category always wins; a model suggestion replaces the document's earlier model suggestion and keeps
  native ones. A name is accepted only when it appears in its quote as a whole token (a sidetrack quote cannot validate
  the parent bore; unicode dashes and spaces are handled). Proposals link to a wellbore only on exact normalized key,
  otherwise stay unresolved. Results are cached by document and prompt version (no provider call on a hit). Typed
  retryable failures for refusal, truncation, malformed output and provider error; document text is data only (no
  tools). `PROCESSING_PROVIDER=meta` fails closed without key, rates and `PROCESSING_RUN_CAP_USD`.
  **Migration 0016** adds `document_model_result` and `document_identity_proposal` (covered by project deletion).
  Verified offline with the stub provider only; the live Meta run is pending owner authorization.

## 0.35.0 - 2026-11-02

- **TASK-071 project deletion:** a sidebar "Delete project" dialog shows what will be removed (counts, stored files) and
  requires typing the exact project name. `GET /api/v1/projects/{id}/deletion-preview` and
  `DELETE /api/v1/projects/{id}` (202, `confirm_name_mismatch` 422, idempotent retry). The project becomes read-only
  while `deletion_state` is `deleting`; a crash-resumable purge drains jobs, deletes `projects/<id>/` and every
  project-scoped row in one transaction (immutability guards stay enabled, lifted only for the purged project), checks the
  storage-root identity first, and keeps the spend ledger. A failed purge shows Retry. A completeness test covers every
  table with `project_id`. **Migration 0015** adds `project.deletion_state` and `deletion_storage_purged_at`.
  Known limits: running extraction runs are marked superseded and waited on rather than cancelled.

## 0.34.0 - 2026-11-02

- **TASK-070 storage integrity:** files are only Stored or Failed ("stored copy missing or damaged"); the word
  "quarantined" is gone from the API and UI. A storage-root identity marker (`.fieldlens-root-id` plus a DB row) stops a
  server with another root from marking real uploads failed, and replaces the 8-sample guard. Failures record a reason
  (`missing`, `size_mismatch`, `hash_mismatch`) and the writing process; DB connections are named
  `fieldlens:<lane>:<pid>`. Re-upload repairs a failed or missing original instead of reporting "already present";
  `POST .../documents/{id}/storage/retry`; a startup heal pass restores failed files whose bytes verify and queues
  extraction. `scripts/storage_root.py status|adopt`; `./dev status/restart` warn about other API processes attached to
  the same database (never kill them). Sources UI: Failed state with Retry/re-upload, repaired-upload message, Start
  extraction for run-less files, storage-root mismatch message.
  **Migration 0014** renames the stored `quarantined` state to `failed`; DTO fields `quarantined_count` -> `failed_count`
  and `JobResult.quarantined` -> `failed` (breaking for API clients, none besides the bundled frontend).
  Operator note: after upgrading, restart every FieldLens API process; stop stale lane servers first.

## 0.33.1 - 2026-11-02

- **Docs:** the delivery policy is parallel development routes in parallel linked worktrees (one writer, branch and
  `./dev` lane per independent feature; shared release metadata, contracts and migration head serialized at merge).
  Replaced the stale "one writer / one feature at a time / no additional worktrees" wording across the instruction files,
  agent profiles and registry, workflow, README and plan documents.

## 0.33.0 - 2026-11-02

- **TASK-068 reconstruction run API:** `/api/v1/projects/{id}/reconstruction-runs` with estimate, a separate confirm
  (one confirm covers a bulk estimate), list/detail, cancel and retry (retry returns a new estimate). Runs are
  persisted (migration `0013_reconstruction_runs`), bounded to 2 concurrent, duplicate start returns the active run,
  interrupted runs are recovered as `interrupted`. Stages: `gather` and `assemble` are deterministic and produce a draft
  summary with coverage, evidence references, unresolved items and conflicts; `extract` and `identify` report
  `not_available` until the agent steps exist, so every run ends `partial`, never `succeeded`. The USD 5 cap is shared
  with processing runs; no live model call path.
- **TASK-069 Reconstruct actions (UI-18):** the Reconstruction tab has an active Reconstruct button per ready wellbore
  and "Reconstruct all ready wellbores (n)": estimate dialog (per-wellbore split, USD total, remaining cap, stub with no
  live calls, 500-page cap, unavailable stages), then a separate Confirm. Rows show run state and stage progress with
  Cancel and Retry; a partial run reads as partial and its draft is labelled as not the published 3D/chart twin.
- **TASK-067 table cleanup:** the Sources column carries category headings with record counts (each file once per
  category, human-readable locators); "Records per category" and the Document processing pane (which showed
  "Processed" for stub runs with no data and no spend) are removed.
- **TASK-066 PDF `source_missing` root cause:** a backend process sharing the database but using a different storage
  root claimed verification, extraction and processing work, found healthy originals missing and marked them
  `source_missing`. Workers now claim work only when a recently stored original is readable under their own storage
  root. Known gaps (TASK-070): no protection before the first stored original exists, and an intentional wipe of the
  newest originals stalls new work. Affected files recover with Re-run extraction (409 means re-upload). Completion
  PDFs still yield no data until label-driven extraction (TASK-055).

## 0.32.0 - 2026-11-02

- **TASK-063 (UI-16) Slim Sources tab and Reconstruction tab:** the Sources tab returns to the project header with
  edit, the tabs, upload, source revision and revision files (with per-file Re-run extraction); the Overview and
  pipeline panel are removed from it. The Reconstruction tab lists identified wells and wellbores, ready ones first with
  a colour and "Ready" badge, a "Block not stated" badge for block-less labels, a Sources column (files per wellbore
  with record count and first human locator, linking to the file row) instead of Present, no Validation column, and
  gaps, conflicts and findings in an expandable row. Each ready wellbore has Process, plus "Process all ready
  wellbores": an estimate first (an identical open estimate is reused), then a separate explicit Confirm; the stub
  provider, no OCR, not reconstruction, and no merge review yet. Wellbores whose data comes only from native parsers
  show why nothing can be processed. Frontend only; no migration or contract change. Known gaps: documents without a
  native profile are not linked to a wellbore until model extraction (TASK-055); the Sources link does not focus a
  file behind "Load more files".

## 0.31.1 - 2026-11-02

- **TASK-064 re-run extraction on an unreadable original:** a file whose stored original cannot be found (for example
  the app was started from another checkout, whose `.local/fieldlens/storage` differs) no longer loops on
  `source_missing` while still marked hash-verified. Re-run extraction re-verifies the stored bytes first: if readable,
  the file returns to stored and extraction runs; if not, it is marked Quarantined and the request returns 409
  `CONFLICT` (with request id) telling the user to re-upload. A failed extraction on a missing or tampered original
  also quarantines the file. No migration or contract change. Known low: a plain `POST` without `retry` skips the
  verification, and the files list does not refresh after the 409 until the next reload.

## 0.31.0 - 2026-11-01

- **TASK-061 (D9) block-less well labels:** a label such as `F-12` or `F-5` (the Statoil survey exports name the well
  only that way) is now a wellbore and well named as written, with no block invented. It carries its records, counts
  for data exposure and the start gate with the warning `BLOCK_NOT_STATED`, and the real F-12 and F-5 exports alone now
  open the gate. Merge proposals pair a block-less wellbore with the same-designator qualified one (`F-12` with
  `15/9-F-12`) for user acceptance; guards are unchanged and nothing merges silently. Behaviour change: a lone `F-12`
  beside a single `15/9-F-12` no longer joins silently. Known low: an underscore block spelling in a quote could count
  as naming the block-less label. No migration.

## 0.30.0 - 2026-11-01

- **TASK-053 (UI-15) Processing pipeline panel in the Sources tab:** a server-driven readiness checklist (wellbore
  identified, validated trajectory, surface location as a warning only), per-wellbore data exposure with counts,
  gaps, conflicts, first locators and truncation notices, and explicit document processing: estimate (pages capped at
  500, tokens, USD, budget against the USD 5 total), a separate confirm, per-document progress, cancel and retry.
  Interrupted, failed and cancelled runs never show as success; stub runs are labelled. Frontend only. Merge review
  and OCR are not available yet. Known low: a cancelled run's per-document text repeats the word "cancelled".
- **TASK-062 diagnosis (no code change):** all 2,474 real Volve PDFs report honestly on 0.26.0 (0 failed); the
  reported "Failed (nothing is trusted)" was stale pre-0.26 state. Two reports over 128 MiB cannot be uploaded.

## 0.29.0 - 2026-11-01

- **TASK-057 (PF-7) AI identity-merge proposals and review API:** deterministic candidate blocking over resolved
  wells/wellbores and unresolved labels, a model step (stub provider only, no live call) proposing that differently
  named sources are one entity with alias evidence quotes, seven deterministic guards (G1-G7: for example no
  cross-designator, planned versus as-built or contradictory-block merges), and a review API where the user accepts,
  rejects or reverts each proposal; nothing merges silently. Accept is concurrency-safe and revert restores the exact
  well, wellbore and link rows. Backend only; review UI follows TASK-053. Known: the planned/as-built guard is lexical
  only. Migration 0012.

## 0.28.0 - 2026-11-01

- **TASK-056 (PF-6, PF-8) wellbore data exposure and start gate:** `GET /identity/exposure` groups records per wellbore
  and category with locators, validation state, gaps and conflicts; `GET /identity/start-gate` passes only with a
  wellbore and a validated trajectory (explicit planned or conflicting status fails; unstated status, stale identity
  and a missing surface location only warn, location marked unlocated). Findings and proposal lists are capped for
  display with exact totals and truncation flags. Evidence endpoint gains a required `exposure` field. Backend only;
  the UI is TASK-053. Unqualified labels (`F-12`) only resolve once TASK-061 lands.

## 0.27.0 - 2026-11-01

- **TASK-048 (UI-13) project Overview in the Sources tab:** frontend-only summary of what was parsed for the project:
  documents by state and format, extraction coverage per record kind, issues by severity with locators, resolved
  wells/wellbores with record counts, series with units and ranges, and an honest "not available yet" list. Sections
  load, fail and retry independently; answers for another project are dropped. Uses existing APIs only, so issues come
  from per-document reports (bounded to 100 reports/500 documents with a visible notice). QA: gates green (153 vitest),
  browser-verified counts, empty/error/retry, keyboard and wording; series/units, cap notice and real Volve data were
  not browser-verified.

## 0.26.0 - 2026-11-01

- **TASK-054 (PF-1..PF-3, PF-10) persistent processing runs:** project-scoped runs for selected documents with or
  without labels: estimate (pages capped at 500, route, tokens, USD, remaining budget against the USD 5 total), a
  separate explicit confirm, start, cancel and retry, interruption-safe states (never reported as succeeded), bounded
  concurrency and an honest "no native parser, processing available" document state. Confirm rejects non-finite,
  oversized and malformed amounts. Stub provider only: no live calls, no OCR; classification and label-driven extraction
  is TASK-055. Migration 0011.

## 0.25.0 - 2026-11-01

- **TASK-051 (IN-11) native Statoil survey export profile:** Added `text_statoil_survey_export` for the extensionless
  Volve "Survey Export" text files (header block, `SURVEY LIST` stations, survey program), with a new
  `well_surface_location` record kind (UTM and lat/long as written, no CRS assumed). Verified against the real F-12, F-5
  and F-14 ACTUAL/PLAN files (211/119/97/137 and 93/114 stations; every value matched the raw text). Plan versus actual
  is never inferred from file names; conflicting wording, impossible dates and inferred day-first order produce findings.
  Known low defect: an invalid date still counts as proof of day-first order for another date in the same file.

## 0.24.1 - 2026-11-01

- **Planning/process:** the owner approved the staged processing flow (`docs/specs/PROCESSING_FLOW.md`), set total live
  development/test spend to USD 5 (D7) and deferred OCR to a separate benchmark (D8, TASK-060). The workflow now runs
  independent tasks in parallel lanes (own worktree, branch, agent and `./dev` lane) with Telegram progress reporting.

## 0.24.0 - 2026-11-01

- **TASK-051 (IN-11) native Compass text survey profile, and a Latin-1 fix:** Added the `text_compass_survey_report`
  profile (shared line parsers with the PDF survey profile): extensionless or legacy-encoded Compass "Standard Survey
  Report" text exports are selected by content and yield trajectory stations, survey program and casing points with
  header-stated units, MD/TVD references, azimuth reference and datum (missing ones are findings, never assumed) and
  line/record/column locators. Validated only against synthetic fixtures; the real Volve export has not been read, and
  PDF-versus-text precedence and conflict reporting are not implemented (TASK-059). Text intake no longer refuses genuine
  heavily accented Latin-1/cp1252 text: 8-bit streams with 25-60% high bytes are accepted when the accented bytes are
  isolated, while BOM-less UTF-16 CJK and above 60% high bytes stay refused. Planning: staged processing flow
  (`docs/specs/PROCESSING_FLOW.md`, owner decisions D1..D6: processing without a label, OCR only if cheaper and faster,
  500-page bound, trajectory as the minimum start condition, unlocated (0, 0) display origin, AI identity-merge review)
  and TASK-054..059 added to the backlog.

## 0.23.0 - 2026-11-01

- **TASK-050 (IN-10), TASK-052 (UI-14), TASK-051 partial (IN-11):** Found in the owner's first manual test. An upload
  with unsupported files is now preflighted as a whole: nothing is stored and the error lists every refused file with its
  position, reason and limit (`ImportRefusal.refused_files`, additive contract); the UI marks those rows red with an icon
  and text and offers "Remove refused files and retry". Text intake is encoding tolerant: extensionless and legacy-encoded
  files (UTF-8, UTF-16, Windows-1252) are accepted when the whole file is text, the detected encoding is recorded in
  `origin_metadata.text_encoding`, and LAS/`.dat` profiles decode with it; files with NUL bytes or too many control or
  high bytes stay refused. The files table has separate Your labels, Suggested labels and Tags columns, an expandable
  Details row (SHA-256, identifiers) and bulk label assignment at upload time and for selected rows. The Compass survey text
  profile (IN-11) is still open pending a readable sample. Verified by independent QA: backend 1194 passed, frontend 143
  tests, e2e 29/29, strict typing and contract drift checks clean.

## 0.22.1 - 2026-11-01

- **TASK-041 live run and repairs:** One authorized live run (cap USD 3, USD 0.68 at placeholder rates; real cost unknown)
  read 4 of 9 planned F-14/F-5 completion pages (25 flagged, unverified, unattached candidates; two control pages returned
  no items) and failed on 5 (two budget stops after a tool-call turn, one truncated output, one schema-invalid and one
  malformed output); the evidence is in `docs/evidence/TASK041_EQUIPMENT_LIVE_RUN.md`. Repairs, verified offline: equipment
  pages are now a single turn without tools (the rotation re-request is an opt-in two-pass mode), equipment output cap
  8,192 tokens with an honest reservation (MI-5 amendment), items are validated one by one (an invalid item is stored
  rejected with its printed text, valid items persist; a malformed envelope still fails the unit with its shape named), a
  printed depth reference that contradicts the claimed one is flagged, quantity parsing accepts inch marks, glued units,
  decimal commas and fractions without guessing, depths or lengths printed in inches are flagged. The runbook gained
  `--only-failed`, `--pages`, remaining-budget checks, a `--file` bootstrap for native data, and clean argument errors.
  Additive contracts only (`RejectedItemAttributes`, `schema_invalid_item`, request output bound 8,192). No second live
  run yet; the 5 failed pages have never been re-read.

## 0.22.0 - 2026-11-01

- **TASK-041 (FL-022-D):** Added visual-level production/completion equipment candidates (EQ-8..EQ-10, offline stub
  verified; no live result yet) on the extraction harness: a closed taxonomy (casing, liner, tubing, packer, pump,
  bearing, perforation interval, isolation, accessory, other) with optional printed material, sizes and depths; a
  versioned prompt; page plans by content hash for the F-14 and F-5 completion documents (with the rotated F-14
  schematic); wrong-well documents excluded before any model call; wellbore attachment through identity, never named by
  the model; every candidate is model-read, unverified, never accepted and never used in calculations; flag-not-drop
  validators; category/wellbore filters on the candidate API. Shared validators hardened (a unit written away from its
  value is flagged, depths must sit on the item's own line, a page naming another well overrides the cover rule,
  glued `95/8` is ambiguous). A page whose image cannot be produced fails the unit before any provider call. Added a
  guarded live runbook `scripts/run_equipment_live.py` (dry run by default; requires an explicit allow flag, a spend cap
  and the live-meta environment flag; refuses the application database) and a project bootstrap helper. Contracts are
  additive; no migration. Known limits: PDFs have no record link to a wellbore (attachment uses a caller-bound label,
  not checkable on scans), the database does not itself forbid relabelling an equipment row as accepted, and the
  lane-database guard does not look at a `dbname` query override.

## 0.21.1 - 2026-11-01

- **TASK-034 integration polish:** The extraction candidates section (TASK-036) in the evidence panel now uses the design
  kit (heading, state/validation/evidence chips with icons, kit buttons, loading/error/empty states, card layout), and
  the status chips cover the `unverified` validation state and `model_proposal` evidence class. Frontend only.

## 0.21.0 - 2026-11-01

- **TASK-034 (FL-021-A):** Replaced the unstyled prototype with a designed application shell: Mantine light theme
  (cobalt brand, self-hosted Inter, lucide icons) built from one token set with a style-scan and contrast checks, a left
  sidebar for project list/create/edit/switch, URL-routed Sources / Reconstruction / Explore tabs with honest
  prerequisites, the Explore region layout (tree, stage, inspector, dock), status/evidence chips with text and icon,
  and redesigned Sources screens (upload dropzone, files table, job and revision panels, inspection and evidence
  views) with truncated long names and IDs that stay keyboard-reachable and copyable. Evidence records re-read until
  they match the report. No API change; no remove/replace/delete controls (their backend is not built). Initial JS
  163 kB gzip, zero external requests, axe clean on the tested states. The one stale e2e assertion (UP-1) was updated
  to the settled "Unsupported" state. Independent UI reviewer score 4/5; owner sign-off pending.

## 0.20.0 - 2026-11-01

- **TASK-036 (FL-022-A):** Added model-proposed extraction candidates with deterministic validation (offline stub
  provider only, no live calls): migration `0010_extraction_candidates` (`extraction_candidate`, reservation link on
  `agent_work_unit`), a closed JSON candidate schema, read-only project-scoped tools (read span, read table, project
  search, page image), pypdfium2 page rendering (about 1600 px, cache by blob/page/scale/rotation, text-layer
  orientation correction, explicit rotation), text-layer page triage, and validators that reject values that are only
  part of a longer number, check units against the quote, parse fractions, Unicode minus and decimal commas strictly,
  require the subject to be named by the source, verify page-item fields, flag parsed-value conflicts against the whole
  parsed set and flag every coordinate or trajectory-type candidate pending AX-11. Image-only reads are `model_read`,
  unverified and rejected by the calculation entry. Per-unit budget reservations link to the activity log, finished
  units settle on startup recovery, `step_key` carries an ordinal, and a candidate read API and evidence-view list were
  added. New dependencies `pypdfium2` and `Pillow`. Known limits: the image-only orientation check is opt-in (it
  rotated upright scans), no render timeout, triage selects nothing for the scanned F-14/F-5 documents (pages are
  supplied explicitly), and a unit written away from its value is not detected (follow-up).

## 0.19.0 - 2026-10-31

- **TASK-047 (FL-005-F):** Added full-resolution time-series storage for LAS curves and daily production:
  migration `0009_series_storage` (`series_axis` with one shared index per data block, `series_curve` with float64
  value arrays, NaN for missing samples, per-curve counts/min/max/unit/NULL sentinel, evidence and a series revision hash),
  written atomically with the extraction run and superseded or cascade-deleted with it; read-only
  `GET /api/v1/projects/{id}/series`, `.../series/{series_id}` and `.../series/{series_id}/window` (deterministic
  min/max- and gap-preserving downsampling `minmax-gap-v1`, bounded full-resolution mode, stable cache key, ASCII-only
  bounds, `decreasing`/`non_increasing` index orders) and the typed `SeriesService` for charts and agent tools. LAS and
  production profiles are v2 (existing runs re-derive; LAS parsing uses compact arrays: 792 MB -> 146 MB peak on 234 real
  files). A LAS file with a free-text data header (for example `15_9-19_A_CPI.las`) or a column-count mismatch stores no
  series. On the real subset 172 LAS files store series (970,241 samples) and production stores 7 wellbores / 15,634 days;
  the independent re-read matched exactly. Time-indexed or wrapped LAS files store no series (follow-ups in TASK-045).
  Migration renumbered from 0008 to 0009 at integration (after TASK-046).

## 0.18.0 - 2026-10-31

- **TASK-046 (FL-005-E):** Depth values in the perforation and formation-pick tables that carry no documented unit now
  default to meters (measured depth) with one non-blocking `MISSING_UNIT` warning per file, and missing depth
  references warn instead of blocking (profile versions 3; stated units always win; TWT, azimuth, coordinates, blanks and
  flagged picks are untouched); a defaulted depth beyond 105% of the known trajectory/log MD range emits
  `SUSPICIOUS_VALUE`. Added deterministic well/wellbore identity: one label rule shared with retrieval
  (`fieldlens.identity.labels`, retrieval behaviour unchanged), migration `0008_identity_links`
  (`well.well_key`, `wellbore.wellbore_key/suffix`, `record_wellbore_link`), post-extraction resolution with
  `IDENTITY_MISMATCH` findings for ambiguity, production-workbook `H`/`AH` bores aliased to the observed base wellbore
  with one warning, and `GET /api/v1/projects/{id}/identity`, `.../identity/wellbores/{id}/evidence` and
  `POST .../identity/resolve`. On the approved real subset: 19 wells, 35 wellbores, 17,136 records linked, none
  unresolved. Parent links are naming-based, not a drilling relationship. Independent QA passed with low notes
  (follow-ups in TASK-045).

## 0.17.0 - 2026-10-31

- **TASK-011 (FL-011-A):** Added project- and source-scoped retrieval over the extracted source observations:
  migration `0007_source_retrieval` (`retrieval_index`, `evidence_chunk` with stemmed and simple full-text vectors,
  `chunk_identifier`, `chunk_embedding`); a deterministic chunker (`chunker-3`, target 400, hard cap 480 estimated
  tokens; headers and units repeated, numbers never orphaned); exact-identifier resolution (well, wellbore and
  sidetrack distinct, nonexistent suffixes reported as unmatched, ambiguity returned explicitly), PostgreSQL
  full-text and exact-cosine pgvector search fused by RRF(60) with eligibility applied before ranking, at most 10 chunks
  and 12,000 tokens; per-hit support flags and a `weak_evidence` status (relevance floor and margin uncalibrated);
  `GET /api/v1/projects/{id}/retrieval/search` and `/retrieval/coverage`; a leased index runner on the job worker with
  ANALYZE policy; local embeddings via pinned FastEmbed `bge-small-en-v1.5` (int8 ONNX, MIT) behind the explicit
  hash-pinned `scripts/fetch_embedding_model.py`, with an explicit degraded mode (exact + full text) when unavailable;
  numeric production/trajectory tables excluded from vectors by owner policy; `fastembed` dependency. Four independent
  QA rounds (no cross-project leak at any point) found and fixed a 30-55 s cold first search, a 500 on NUL, mislabelled
  modes, missing stemming, sidetrack/parent identity leaks and lone-frequent-word false strength. Offline tests only;
  no real-data recall claim; follow-ups in TASK-045. Integration fix: a type annotation in the TASK-030 spike script
  `scripts/spikes/ocr_common.py`, needed because the new embedding dependencies make Pillow's types visible to mypy.

## 0.16.3 - 2026-10-31

- **TASK-030 phase A (FL-005-C):** Added the offline OCR/rendering/orientation evaluation for the scanned completion
  pages: `scripts/spikes/ocr_*.py` and `docs/evidence/TASK030_OCR_EVALUATION.md`. Findings (agent-read reference, not
  human-verified): RapidOCR with onnxruntime recovers 63-66 of 67 reference numbers at 300 dpi (Tesseract 54/67), only the
  rotated schematic needs a second pass, and an OCR-agreement rule would have confirmed 265 of 278 model-read numbers
  while rejecting the judged misreads; the legacy F-5 completion `.doc` has extractable text and 12 pictures (macros
  present, never read). Records the phase B design, its contract needs (an OCR issue code, no EvidenceClass change),
  third-party notices and owner decisions. No product code, contract, migration or lockfile change; the final
  evidence-text commit was reviewed by the orchestrator, not re-QA'd.

## 0.16.2 - 2026-10-31

- **TASK-044 (FL-005-D):** Added the offline check of the deferred 211 MB EDM export (PV-24) for production/completion
  equipment and perforation history: streaming spike scripts in `scripts/spikes/` (reusing the hardened XML parser,
  about 5 s and 38 MB for a full census) and `docs/evidence/TASK044_EDM_COMPLETION_CHECK.md`. Finding: the export is a
  drilling/planning database with no installed completion, perforation or dated history for F-12, F-14 or F-5, no
  units, and conflicting scenario/case datum elevations (177.165 versus 180.118); only F-14 A has design-variant
  tubing, liner and packer data (design packer depth conflicts: 8350.07 versus 8678.15). A streaming EDM profile is not
  recommended for this purpose. No product code changed; the final wording-only evidence commit was reviewed by the
  orchestrator and not re-QA'd.

## 0.16.1 - 2026-10-31

- **TASK-042 (FL-022-E):** Added the live feasibility spike of model reading of the seven approved completion
  PDFs: reviewable scripts in `scripts/spikes/` (survey, render, live runner behind `--live`, scoring) and
  `docs/evidence/TASK042_COMPLETION_SPIKE.md`. Findings (live `muse-spark-1.3` on an agent-read, not
  human-verified reference): typed equipment candidates are read reliably from upright page images at about
  1600 px and `low` effort (strict 68/83 uniform, 80/83 tuned), depths and units exact as printed, no invented
  items on control pages, but small-print digit misreads and silent empty answers on rotated pages; scanned
  documents need OCR first; the three completion reports in the F-12 folder describe F-11 wells, so no F-12
  production equipment exists in the seven files; F-11 B perforation history appears on PV-11 pages 74 and 136
  (with a 4065 versus 4063 disagreement). Spend USD 2.9036 at placeholder rates (real about one sixth,
  unverified). No product code changed.

## 0.16.0 - 2026-10-31

- **TASK-043 (FL-003-C):** Hardened the provider adapter from the live MI-6 findings: optional per-request
  reasoning effort (`minimal`/`low`/`medium`/`high`; unset keeps the provider default and old recordings still
  replay), a tool- and reasoning-aware input-token reservation bound (a one-tool request now reserves at least the
  552 billed tokens), explicit in-flight cancel settlement (the call still bills and is settled; cancel does not
  stop billing), 404/405 rejections settled as non-billable while every other 4xx stays liable, and ledger helpers
  to list, reconcile and release liable reservations that never go below known billed attempts. Rate cards are
  validated before registration; no rates changed. Independent QA found two medium defects, repaired and
  re-verified. Offline only: effort acceptance, the 404/405 non-billing rule and multi-tool token bounds are not
  yet verified live.

## 0.15.0 - 2026-10-31

- **TASK-038 (FL-022-B):** Added the persisted, project-scoped agent activity log (AX-10 backend):
  migration `0006_agent_activity_log` (`agent_work_unit`, `agent_step`), a fenced write service for the
  extraction harness (start/append/finalize, restart-safe interruption and resume without duplicate steps),
  conservative secret redaction and size bounds including evidence locator text, and read endpoints
  `GET /api/v1/projects/{id}/agent-units[/{unit_id}]` with generated client types. No hidden reasoning is stored
  and the log is never an engineering source. Independent QA found one medium defect (locator text not
  redacted or bounded), repaired and re-verified. Deferred to TASK-036: startup recovery wiring, budget
  reservation link, cancel/retry endpoints. Offline only; no UI (TASK-040).

## 0.14.1 - 2026-10-31

- **TASK-005 (FL-003-B):** Added the opt-in live Meta smoke (MI-6): `test_meta_live_smoke` behind the
  `live_meta` marker and an explicit `FIELDLENS_LIVE_META=1` plus a real-environment `MODEL_API_KEY` (default
  runs exclude it, blank the key and keep the loopback socket guard), with evidence in
  `docs/evidence/MI6_LIVE_SMOKE.md`. Live findings on `muse-spark-1.3` (Responses): text, tool round trip with
  reasoning replay and synthetic image input work; there is no embeddings endpoint; reasoning effort defaults to
  high and consumes output tokens; the input estimator under-counts tool requests (about 2.3x); in-flight
  cancel still bills. Adapter fixes are tracked as TASK-043. Placeholder-rate upper bound about USD 0.42
  across two runs (one accidental during QA), real rates and balance unconfirmed. No runtime code changed.

## 0.14.0 - 2026-10-30

- **TASK-009 (FL-005-B):** Added versioned native source profiles with attribute-level
  evidence (WITSML tubular/BHA run/bore geometry/trajectory, Volve production workbook, LAS 2.0,
  perforation and well-pick tables, Compass survey-report PDF), content-based detection, a
  persistent bounded extraction runner (leases, fenced finalize, idempotent re-runs, supersede on
  profile version change), `/extraction` endpoints and DTOs, five new data-quality codes
  (`MISSING_REFERENCE`, `MISSING_UNIT`, `SUSPICIOUS_VALUE`, `UNKNOWN_CODE`,
  `ASSEMBLY_TYPE_MISMATCH`) plus identity-mismatch reporting, a 500-page PDF limit and an evidence
  panel in source inspection. Migration `0005_native_profiles`; dependency `pypdf`; opt-in
  `FIELDLENS_LOCAL_DATA_ROOT` local-data test and a lane-safe `FIELDLENS_E2E_API_PORT` e2e override.
  On the real subset all 18 files produce reports; trajectory, production and perforation
  records exist for F-12, F-14 and F-5, equipment is drilling-side only, and perforation/pick
  depths stay `unsupported` (no documented unit/datum). Independent QA found a report-endpoint
  500 and nine further defects, all repaired and re-verified. EDM export, grids, completion PDFs
  and OCR remain deferred.

## 0.13.0 - 2026-10-30

- **TASK-004 (FL-003-A):** Added the offline provider adapter in `backend/fieldlens/assistant/`:
  message model with image parts and tool-call round trips, stub/replay/recorder providers, the
  Meta Responses wrapper (never called by default tests; no live calls), a PostgreSQL budget
  ledger (USD 150 ceiling; reserve/settle/release/reconcile; overruns are flagged and pause the
  period) and bounded work units (4 attempts, configurable tool-call bound default 6, 90 s,
  USD 0.50) with typed refusal/truncation/malformed/timeout/cancellation handling. Migration
  `0004_provider_budget`; dependency `openai`. Owner decision: the single provider key variable is
  `MODEL_API_KEY`, adopted only by the application settings as a secret (DEV_ENVIRONMENT AC-6
  amended); default tests force it blank. Independent QA found six defects, all repaired and
  re-verified. Meta behaviour, billing and token bounds remain unverified until TASK-005.

## 0.12.1 - 2026-10-30

- **Fix (FL-019):** `./dev up` failed in `alembic upgrade head` when the shell had `.env`
  exported verbatim by an editor terminal (`${FIELDLENS_DB_PORT}` left unexpanded in
  `FIELDLENS_DATABASE_URL`). Settings now resolve `${VAR}` references (undefined ones are
  rejected without echoing the URL), and the test harness ignores such unexpanded values.

## 0.12.0 - 2026-10-29

- **FL-020-C:** Added the one-way backlog -> Taiga mirror (`scripts/taiga_client.py`,
  `track.py plan|sync [--apply] [--keep-drift] [--notify] [--only IDs]`): features become user
  stories and tasks become tasks under their parent in sprint `Hackathon`, with tags (priority,
  agent), status per spec 4.2, due dates, owner assignment, blocked flags/notes from unmet
  dependencies and `#ref` dependency links. Idempotent against live state (detail fetch per
  matched item), drift reported/overwritten, retries/re-auth, operation lock, atomic 0600 state
  file, privacy/secret guards (refuses a public project without `TAIGA_ALLOW_PUBLIC=1`),
  optional Telegram summary. Orchestrator profile and workflow now require Telegram progress
  notifications. No application, API or schema change. Independent QA: live smoke (8 items,
  zero-write rerun), 536 backend tests; live `is_blocked=true` and 429/5xx paths verified on fakes only.

## 0.11.0 - 2026-10-29

- **FL-020-B:** `docs/BACKLOG.md` is now a machine-checkable ledger: one block per feature
  (FL-000..FL-020) and task (TASK-001..TASK-032) with status, priority, tags, dependencies,
  assignee, due date, sprint, spec and version; all earlier narrative is kept verbatim under
  `## Journal`. Added `scripts/ledger.py` (strict parser/validator: required fields, enums,
  duplicate IDs, dependency existence/cycles/due order/priority order, done evidence, secret
  guard, no echo of values) and `scripts/track.py check|list|plan` (no network yet; Taiga sync is
  slice C). TASK-001 is recorded as in_progress (DA-7 not yet verified for every profile);
  TASK-003's done status keeps a documented owner-exception dependency on it. No application,
  API or schema change. Independent QA PASS after one repair round (517 backend tests).

## 0.10.0 - 2026-10-29

- **FL-019-A:** Added `./dev`, a one-command local stack (`scripts/dev.py`): `up [--dev]`
  starts PostgreSQL (service-named Compose), applies migrations, rebuilds the frontend only when
  its inputs changed (atomic swap), starts the API with pid/log files and waits for a real
  `/api/v1/ready`; `down [--db]`, `restart`, `status`, `logs`, `test [backend|frontend|e2e|all]`,
  `reset-data` (typed confirmation, never the test DBs), `env-check`. Idempotent, operation
  lock, SIGINT/SIGTERM cleanup, child environment allowlist (no credentials), and
  worktree lanes with their own database/ports/storage (`down --drop-lane`). Known limits: lane
  Vite still proxies to port 8101 and `./dev test e2e` is fixed to 8101. No application, API or
  schema change. Independent QA PASS after three rounds (450 backend tests, real up/down runs).

## 0.9.0 - 2026-10-29

- **FL-020-A:** Added `scripts/notify.py`, a send-only Telegram progress notifier for the
  orchestrator: event vocabulary with 🔴 ACTION NEEDED versus 🟢/🔵/⚪ status markers, dry-run,
  `--best-effort`, 60 s duplicate suppression, secret redaction/refusal, config-shape
  validation, and an optional allowlisted inbox (`TELEGRAM_INBOX=1`, off by default; stores
  commands only, executes nothing). `scripts/toolenv.py` loads only `TELEGRAM_*`/`TAIGA_*` keys
  with dotenv comment semantics (worktrees fall back to the main checkout's `.env`);
  `fieldlens.localenv` is unchanged. `.env.example` documents the empty keys. No application,
  API or schema change. Independent QA PASS after two repair rounds (396 backend tests).

## 0.8.0 - 2026-10-29

- **FL-005-A (TASK-006):** Added project-scoped upload, storage and persistent jobs plus the
  upload/source UI. Backend: `POST /api/v1/projects/{id}/imports` (metadata part first, files
  aligned by index; 202 new / 200 replay / 409 one staging import per project / 415 unknown
  binaries), streamed 128 MiB/file, 512 MiB/batch and 200-file limits, content-hash blob
  storage, immutable source revisions with idempotent replay, fenced restart-safe jobs with one
  automatic retry, staging sweep, migration `0003_upload_jobs`, `python-multipart`. Files are
  stored and hash-verified only: no extraction, evidence claims or asset-model publication
  (unknown plain text is `unsupported`; readers and the 500-page PDF / XLSX XXE and ZIP-entry
  parse-time checks arrive with TASK-009). UI (`features/uploads`): multi-file upload with
  limit validation, progress and abort, explicit stored/unsupported/pending-extraction
  labels, revision/quarantine/partial-revision warnings, label edit with version conflicts,
  job status/cancel and idle-stopping polling; keyboard/focus and 320 px layouts. Independent
  QA: backend passed IN-1/3/4/5/7 after two repair rounds (rejected-import blob, stale staging
  files); UI passed after three rounds (focus management, "superseded" wording, 320 px
  overflow, keyboard-scrollable table, focus after removal). 380 backend (1 skipped: TASK-009),
  38 vitest and 12 browser E2E tests. Known low gaps: tab buttons break mid-word at 320 px;
  orphan-blob sweep, a real quarantined-revision browser run, 128 MiB/200-file browser runs and
  non-Chromium browsers are unverified; "superseded" is judged from the loaded page only.

## 0.7.0 - 2026-10-29

- **FL-008-A (TASK-008):** Added the deterministic perforation state engine
  `fieldlens.engineering.perforation`: as-of replay of wellbore-scoped events, unique-MD
  interval union (exact decimals, ft/m), `unknown` instead of verified zero without a
  baseline, scope-specific interval state (well-level production/shut-in never erases or
  assigns interval state), commutativity-based order analysis that never invents an order
  (over-budget groups report unresolved axes, never definite values), dataset-revision
  correction chains and per-event validation (implausible/overflow depths rejected without
  losing valid history). Engine and unit tests only: no API, UI, migration or PostgreSQL
  persistence (PH-6 persistence, PH-1/4/8 and day-range queries remain open). Independent
  QA of `aaf0fdd` passed PH-2/3/5/7/9 and engine PH-6 (299 backend tests; brute-force
  oracle over 14,488 queries with no wrong resolved result). Assumptions awaiting owner
  confirmation: a baseline precedes same-instant events; correction-chain rule; 100,000 m
  MD plausibility bound; 12-event/32-state exploration budget.

## 0.6.0 - 2026-10-29

- **FL-006-A (TASK-007):** Added the deterministic trajectory engine
  `fieldlens.engineering.trajectory`: double-precision minimum-curvature coordinates,
  survey validation that blocks affected geometry (missing CRS/datum/depth/north reference,
  unresolved magnetic/true conversion, nonfinite angles, bad MD), and bounded 3D closest
  approach with an explicit error bound (<= 0.02 m). Adds `numpy`. Engine and unit tests
  only: no API, renderer or pyproj transform. Proximity is not proof of connectivity or
  safe clearance. Independent QA of `532d517` passed TR-1/2/3 (233 backend tests); known
  low gaps: deadline can overrun inside piece construction, near-duplicate MD is not
  flagged, `depth_reference` is not compared between bores.

## 0.5.1 - 2026-10-28

- **FL-018:** Replaced the per-lane Compose files and `db.env` credentials with one
  root `compose.yaml` (project `fieldlens`: PostgreSQL plus a `test`-profile browser) and
  one gitignored root `.env`. The API, Alembic, tests and the E2E runner load `.env`
  automatically (real environment variables still win); `MODEL_API_KEY` is never loaded
  into application or test processes. `uv run python scripts/init_env.py` creates the
  missing keys idempotently, with 0600 mode and a generated password.
- Fresh names: role `fieldlens`, database `fieldlens_app`, volume `fieldlens_pgdata`.
  **Data in the old `fl004a`/`fl015a` volumes is not migrated** and the volumes are
  untouched. Tests derive a throwaway `fieldlens_app_test_<hex>` database and never use
  the application database. `infra/compose*.yaml` was removed.
- Independent QA of `2bc4129` passed AC-1..8 from a clean shell: 219 backend, 15 UI,
  9 E2E, lint/type/contract/build checks. Known limitations: hand-edited passwords
  containing `@`, `$` or `%` are not validated (generated passwords are safe), the
  not-configured readiness message does not yet name the bootstrap script, and
  `frontend_dist` stays cwd-relative.

## 0.5.0 - 2026-10-28

- **FL-015-A / TASK-025:** Added persistent project list/create/open/edit APIs
  and keyboard-accessible workspace navigation. Project switching discards stale
  reads and save acknowledgements; reload restores the selected existing project.
  Empty projects expose prerequisites without fabricated assets or upload controls.
- Added typed project requests and cursor pagination, plus migration
  `0002_project_lifecycle` for the existing 4000-character description contract
  and newest-first index. Run `uv run alembic -c backend/alembic.ini upgrade head`;
  valid foundation data is preserved. This is an additive feature, not a breaking
  public-contract change.
- Independent QA found invalid NUL input misreported as a storage failure.
  Repaired NUL/unpaired-surrogate validation now returns typed 422 errors before
  database access. Independent re-verification passed on `2af22aa`: 193 backend,
  15 UI and 9 real API/PostgreSQL browser tests, plus invalid-text and migration
  preservation probes. The browser runner supports real API process restarts.
- Uploads/jobs and their workspace criteria remain the next packet. No original
  source qualification, provider call, push, tag or publication is included.

## 0.4.0 - 2026-10-28

First runnable local foundation. The owner accepted tested repair `95da2b7` and
authorized merging it into master using direct verification as a **one-time
exception**. Independent QA remains required for future features. Integration
is recorded in the backlog; no push, tag or external publication is included.
The initial backend invocation regained editing tools, but the repair invocation
lost them again; its precise cache/registration/model-interaction cause is not proven.

- **FL-004-A / TASK-003:** Added FastAPI health/readiness, PostgreSQL migration
  baseline, typed/generated contracts, local session guards and React shell.
  Repaired nested evidence scope, generic/catalog authority bypasses, finite
  metadata/image/quantity validation, read limits and test database isolation.
  Retry retains keyboard focus, runtime metadata derives from VERSION, Node 24
  is pinned/enforced, and startup/test documentation is usable.
- Added a digest-pinned, test-only Playwright Noble browser with Docker Desktop
  loopback forwarding. The CLI suite now verifies loading, network failure,
  real database-unavailable state and keyboard Retry recovery against an owned,
  disposable API/database. No application container or host OS upgrade.
- Direct validation: 124 backend, 4 UI and 3 CLI E2E tests pass; affected
  lint/type/build/contracts checks pass. This is not independent re-verification.
- **FL-001:** Record mandatory separate-agent acceptance, repair re-verification
  and completion of the authorized commit/merge cycle for every logical feature.

- **FL-001 / FL-004:** Owner approved serial development in the existing checkout:
  one feature branch and one writer at a time, subagents launched by the main
  session, no new worktrees. Preserve legacy worktrees and pending changes.
  Updated scheduling, worker boundaries and resource allocations; model/tool
  gates remain per-assignment requirements. These governance amendments share
  this one minor version; no additional bump is allocated for the merge.

## 0.3.3 - 2026-10-28

Integrated by the owner in `9d630e3`, matching [VERSION](VERSION).
Patch bump: source qualification and implementation-planning documentation only; no implemented
API/schema or application behavior change.

### Changed

- **FL-002 / FL-007:** Verified F-5's embedded Existing completion table with
  source/image hashes, exact MD/length/OD/ID and inert OLE-image provenance.
  Expanded the F-12 installed-tally search; recorded bounded coverage and the
  continued non-finding without claiming absence from the complete release.
- Distinguished F-11 B's actual installation narrative from its dimensioned
  drawing explicitly marked Plan; kept it a conditional reserve rather than
  silently replacing F-12 or merging sidetrack identities.
- Located dated perforation evidence for all three proposed pilots. Matched
  F-14's six initial and F-5's five 2008 intervals to the static table, explained
  F-5's three-versus-five snapshot difference, and recorded 2016 additions.
- Preserved F-12's conflicting 2014 interval summary/detail and clarified that
  physical perforation length, open/isolation state and interval flow differ.
  At that inspection checkpoint cohort/history/reference/rights acceptance remained open.
- Reconciled the owner's `a4bf9ee` integration as version 0.3.2; documentation
  integration alone did not approve the then-draft behavior or close G0/G1.
- **FL-002 / FL-007 / FL-014..017:** Recorded the owner's subsequent F-12/F-14/F-5
  selection, evidence-safe generic F-12 equipment, visible discrepancies, hybrid
  labels, explicit reconstruction/review/publication and upload-limit approval.
  Final G1/live/runtime gates remain separate.
- Added a source/draft/model data-quality issue specification and shared DTO/API
  contract, named real discrepancy fixtures and generic/unlocated negative tests.
  Expanded the global DAG to 32 tasks without dropping mandatory features.
- Added detailed foundation/project/upload implementation packets with 19 internal
  steps, planned paths/checks, isolated worktrees/resources, single-writer rules and
  stop/handoff conditions. No application workers or paid calls were launched.
- Reconciled instructions, backlog and acceptance traceability; clarified inert
  legacy-Word inspection versus forbidden macro execution for the F-5 source.

### Validation

- Original XML activity locators/timestamps, static interval correspondence,
  exact-decimal union lengths, device length arithmetic and source/image hashes
  checked; evidence retained in a new ignored audit sidecar without overwriting
  prior records. Selected scans inspected visually; no general OCR or Meta calls.
- Planning checks passed for 23 Markdown files/208 local links and headings,
  table/fence structure, 32-task and 18-item dependency graphs, 12 project
  acceptance rows, DQ-1..8/EQ-7 traceability, 19 first-packet steps and whitespace.
  Mandatory tasks reach release; optional Blender does not block it.
- Documentation-only change; no application tests or completed reconstruction
  are claimed.

## 0.3.2 - 2026-10-28

Integrated by the owner in `a4bf9ee`.
Patch bump: source evidence and revised planning/specifications only; no
implemented API/schema or application behavior change.

### Changed

- **FL-014 / FL-015 / FL-016:** Resumed planning on October 28 at the owner's
  request while leaving final data qualification and implementation approval open.
  Drafted project-scoped categorized uploads, separate source/model revisions,
  composite-asset reconstruction and minimal evidence/diff review/publication.
- Made the custom persistent Meta harness responsible for reconstruction as well
  as exploration; separated proposal, validation, accepted facts and tool permissions.
  Added early source conversation and independent reconstruction gold evaluation.
- Reworked delivery into UI-verifiable project/source/reconstruction/scene/enrichment
  checkpoints, with a 31-task dependency DAG and 12 project acceptance criteria.
  Preserved all required history, context and chart families.
- Proposed streaming limits that admit the inspected F-14 PDF and explicit
  qualification of required scanned/legacy-Word equipment evidence. Hybrid labels,
  limits and review-before-publication remain defaults awaiting owner approval;
  no confirmation is inferred from the unanswered clarification form.

- **FL-002 / FL-007:** Recorded acquisition of the pinned production workbook and
  1,759-report WITSML conversion, including 402 reports under the proposed pilot
  labels. Added byte/hash provenance and exact completion/perforation locators.
- Distinguished nominal equipment sizes from actual geometry, report dates from
  operation windows, missing converted unit/datum attributes and cross-well
  activity subjects. Complete installed geometry/history gates remain open.
- Recorded the repeated official missing-volume failure and documented shared
  volume read-privilege checks without changing access or assuming an upgrade.
- Reconciled the owner's `4ae7f7b` integration as version 0.3.1, then reopened
  **FL-014** for project-centric uploads, reconstruction-agent/harness ownership
  and UI-first verification. The previous architecture is explicitly provisional;
  those design changes have not yet been agreed or implemented.
- Recorded the owner's subsequent hard data gate: pause further design and
  application implementation until essential-data access/coverage is established,
  overriding the old plan's source-independent dispatch permission.
- **FL-002:** Acquired four pinned F-5 trajectory XML sections and their mapping;
  recorded unit/overlap/reference limits and an essential-data coverage table.
  Verified local copies now live under the existing Git-ignored data directory.
- Identified the official listing's 90-day installation policy and the May 27
  installation as an expiration hypothesis. Recorded the provider support route;
  no agent-performed reinstall or account change is claimed.
- **FL-002:** Inspected the owner's subsequent local official download: 33,678
  files, all 33 candidate paths, referenced ACTUAL surveys, depth horizons,
  production, logs and original operational evidence. Recorded that the earlier
  workspace failures no longer block local inspection.
- Found report/folder misattribution, undated pilot perforation-table rows and
  an embedded TIME horizon in the nominal seabed DEPTH file. Kept raw/interpreted
  curves, conflicting depth/position references and installed/design equipment
  separate. Seismic/OW archive acquisition is unnecessary for interpreted depth
  layers; this does not close G1 or authorize application implementation.
- Verified dimensional/MD evidence in F-14's AS INSTALLED completion schematic,
  including a safety valve, PBR and packer. Identified the specifically referenced
  29-01-2008 F-12 tally as not located in inspected sources, and distinguished
  F-5's genuine Word completion report from its mislabeled drilling PDF.

### Validation

- October 28 planning checks: 26 Markdown files, 188 local links/headings,
  table/fence structure, 31-task/six-goal acyclic DAG, 17 backlog items and all
  12 project acceptance criteria traced. Verified early UI/agent independence,
  optional Blender exclusion and explicit source/draft/model scopes. No runtime
  tests, live Meta calls or implementation approval are claimed.
- Acquired mirror bytes/hashes, row counts and selected source locators checked.
  Parquet inspection used temporary Python 3.12/PyArrow 26.0.0, not an application
  dependency change. No paid model calls, application tests or pilot acceptance.
- Local filesystem inventory, native structured-data checks and source hashes
  recorded in Git-ignored audit sidecars. Document-only review; the full 44.82 GiB
  was not content-validated and no app performance claim is made.

## 0.3.1 - 2026-10-27

Integrated by the owner in `4ae7f7b`.
Patch bump: architecture/specification and data-discovery documentation;
no implemented application API/schema change or completed pilot/live audit.

### Added

- **FL-002:** Public-source discovery report, official access/license handoff,
  expanded 33-file metadata-only pilot list and draft data-feasibility spec.
- **FL-002 / FL-007:** Equipment-source reassessment, three pinned WITSML probes
  with dimensions/locators/hashes, EDT/EDM and tubular/run priorities, and a
  proposed installed-assembly feasibility checkpoint distinct from generic/BHA geometry.
- **FL-014:** Complete modular-monolith architecture, selected stack/process model,
  revision/evidence/time/API contracts, feature specifications and requirement-to-test
  traceability based on inspected evidence.
- **FL-014:** A 24-task dependency-aware implementation plan with independent
  source-free slices, required real-data/live gates, agent/worktree/file ownership,
  two resource lanes, serialized integration and deadline/rehearsal checkpoints.

### Changed

- Recorded owner-confirmed indie track, public repository, three-minute demo,
  local/container runtime and ready Meta key/public-data processing permission.
- Corrected the earlier prepared-data assumption, refreshed Docker availability,
  and distinguished metadata findings from inspected engineering samples.
- Recorded successful account sign-in and the actual catalog visibility blocker:
  missing public schema/volume, not a missing account. No access-policy changes.
- Completed the bounded alternative-source search and documented another
  drilling/completion label mismatch, plus the distinction between provider
  inspection privileges and shared-volume read access.
- Reconciled FL-013 and version 0.3.0 against the owner's `88b177e` integration;
  Blender execution and agent-host activation remain unverified.
- Moved FL-014 from data-blocked design to documentation integration-pending;
  pilot access still blocks FL-002 and real-data acceptance, not all design work.
- Split existing feature IDs into bounded implementation increments without
  removing seabed/formations, production/log charts or historical perforations.
- Selected native PDF readers with conditional measured OCR, CPU local embeddings,
  strict generated API types, finite provider budgets and separate display/analytic
  projections. Runtime/model/package qualifications remain explicit future checks.

### Validation

- Official license/access documents and selected SODIR identities inspected;
  community metadata catalog checksum verified. No pilot files, account creation,
  paid Meta calls, cloud provisioning or application implementation.
- Three public mirrored WITSML files (7,776 bytes) passed fixed-revision/blob/hash,
  bounded XML and structural field checks across 8 components and 4 bore sections;
  these are not validated installation/datum claims.
- Initial static checks passed: 22 unique candidate paths matched catalog rows, unknown
  bytes/hashes remain blank, 86 local documentation links, 15 unique backlog IDs
  with acyclic dependencies, candidate version agreement and `git diff --check`.
  These do not satisfy the draft audit's content/numerical acceptance criteria.
- Equipment follow-up checks passed for 33 exact candidate paths, 95 local
  documentation links, 15 acyclic backlog items, DF-1 through DF-9, version
  agreement, sample hashes and `git diff --check`. Pilot acceptance remains blocked.
- Architecture-package checks passed: 185 local links, 24 unique acyclic tasks,
  six phase goals, 15 acyclic backlog parents, 10 new spec structures, 84 unique
  feature/data/history criteria and traceability for all 10 project ACs. All
  13 new design documents passed table/fence/whitespace checks; independent lanes,
  optional-asset exclusion, fixture arithmetic and EST deadline/version consistency
  were checked. These are documentation checks, not executed application tests.

## 0.3.0 - 2026-10-27

Offline Blender authoring skill integrated by owner on `master` in `88b177e`.
Minor bump for a newly invocable development skill; no application API/schema
change or operational Blender validation.

### Added

- **FL-013:** Original `fieldlens-blender-assets` skill for source-aware hard-surface
  equipment modeling, reviewed bpy scripts, materials/UVs, low-poly optimization,
  previews and validated GLB handoff.
- **FL-013:** Export checklist for units, axes, pivots, semantic IDs, permitted
  resources, format/round-trip checks and runtime budgets.

### Changed

- Existing 3D/motion agent and Three.js skill now route complex offline equipment
  authoring to Blender; simple wellbore geometry stays procedural.
- Workflow, technical baseline and curation guidance distinguish Blender's bundled
  Python from backend Python and reviewed offline scripts from prohibited runtime
  generated code. Agent count and model/effort defaults are unchanged.
- Reconciled the 0.2.0 configuration integration against `35ed5d2`; host activation
  remains unverified and is not inferred from that commit.
- Removed the broad `.github/` ignore rule at the owner's request so new shared
  skills remain visible to Git.

### Validation

- Static checks passed for the new skill header, 8 skills, 11 unchanged agent
  model tiers, 2 new routing cases, 158 local references, backlog/dependency/
  version consistency and Git visibility. `git diff --check` passed.
- Blender was not found on WSL PATH. Installation, assets, real export/render/
  browser tests and any new service are explicitly deferred by the owner.

## 0.2.0 - 2026-10-27

Development-agent configuration integrated by owner on `master` in `35ed5d2`.
This confirms repository configuration, not host activation or an application
release. Minor bump for new opt-in development-agent capability.

### Added

- **FL-001:** Main Astra/xhigh orchestrator profile and ten specialist profiles
  for small tasks, frontend, backend, 3D/motion, research, ingestion/OCR, RAG,
  geospatial/engineering, QA and bounded plan repair.
- **FL-001:** Owner-approved Terra/low, Sonnet/medium and Sol/high worker tiers;
  explicit routing, no silent model fallback, no nested worker delegation,
  minimal-context assignments and model/usage verification.
- **FL-001:** Agent registry, shared execution contract, activation guidance and
  approved configuration specification.

### Changed

- Execution guidance and feature handoffs now record role/risk rationale,
  actual model/effort evidence, bounded attempts and exposed usage. Development
  usage is distinct from the shared Meta application budget.
- Reconciled FL-000 and the 0.1.0 baseline against the owner's actual integration
  commit `e8b156a`; this does not retroactively claim an application release.

### Validation

- Static checks passed for 11 YAML profiles/model tiers/tool boundaries, 12 routing
  cases, 143 local references, backlog dependencies and version consistency.
  VS Code reported no agent-file diagnostics; `git diff --check` passed.
- Host profile/model activation remains untested and is a required check before
  real feature delegation; static checks do not prove runtime model selection.
- No application implementation, new worktrees, paid Meta calls or publication.

## 0.1.0 - 2026-10-27

Initial documentation baseline, integrated on `master` by `e8b156a`.
No application release or Git tag is asserted; earlier unversioned commits
remain listed below without invented historical versions.

### Added

- **FL-000:** Development workflow for main-agent planning/orchestration, isolated
  implementation worktrees, dependency-aware parallelism, verification/handoff,
  serialized integration and backlog reconciliation.
- **FL-000:** Persistent backlog, canonical version file, changelog policy, and
  feature-template fields for delegation, compatibility and integration evidence.
- **FL-000 / FL-008:** Historical perforation requirements and a draft feature
  contract for MD/TVD intervals, total/open perforated length, date-specific
  producing/injecting/shut-in states, reperforation, uncertainty and provenance.
  These are requirements, not implemented application capabilities.

### Changed

- **FL-000:** Project, technical, source and developer guidance now account for
  historical perforation state and selected-time/revision consistency.
- **FL-000:** Clarified that the deferred application-runtime multi-agent framework
  does not exclude the required multi-agent development workflow.

### Validation

- Checked 94 local Markdown/HTML references, backlog ID/dependency integrity,
  bootstrap version consistency, all seven synthetic state/length examples and
  ft/m round trips. Skill metadata matches the previously validated baseline;
  `git diff --check` passed.
  No application feature tests, worktree-agent execution, push, release or tag
  were performed by the documentation task. Integration was subsequently confirmed
  from Git history.

## Pre-versioning history

These entries describe existing commits, not historical numbered releases.

- **2026-10-27, `2772cff`:** Design/reference assets, curated development skills
  and supporting documentation.
- **2026-10-26, `695da46`:** Initial project structure, requirements and technical
  documentation.
