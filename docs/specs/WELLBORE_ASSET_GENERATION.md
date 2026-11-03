# Specification: Wellbore identity grouping and agent-generated visual 3D asset

> **Spec type:** Product/feature (agent stages + contract + 3D viewer). **Date:** 2026-11-02.
> **Author:** orchestrator. **Decision owner:** owner.
> **Status:** Approved for implementation by the owner on 2026-11-02 (answers in section 14); Q1 and Q3 were answered at 23:46 (below); they supersede the earlier defaults. `[Proposed]` marks my decisions awaiting confirmation; `[Open]` marks questions.
> **Backlog:** FL-023 (TASK-076..TASK-081). Related TASK-075 lives in [MODEL_PROCESSING_OUTCOME](MODEL_PROCESSING_OUTCOME.md) §8.
> **Extends:** [RECONSTRUCTION_RUN](RECONSTRUCTION_RUN.md) (stage list), [MERGE_PROPOSALS](MERGE_PROPOSALS.md),
> [EQUIPMENT_RECONSTRUCTION](EQUIPMENT_RECONSTRUCTION.md), [TRAJECTORY_VIEWER](TRAJECTORY_VIEWER.md),
> [DOCUMENT_IDENTIFICATION](DOCUMENT_IDENTIFICATION.md). Does not change engineering-truth rules.

## 1. Outcome

The reconstruction agent (a) recognises that differently named sources describe one wellbore ("15/9-F-12" and "F-12")
and merges them so the wellbore has one group of files, then (b) reads that wellbore's schematic/equipment sources and
produces a **visual 3D representation of the wellbore asset**: trajectory plus a plausible assembly (casing, tubing,
packers, pumps, valves, perforations, wellhead/tree). Representation is *close enough for visual interaction*, not an
engineering-accurate model. It is shown for one wellbore and for many wellbores together (field view). Charts,
history, formations and reservoir wrapping are a later feature and out of scope here.

## 2. What the owner screenshot shows (current state)

The reconstruction estimate modal lists S1 Gather, S2 Extract, S3 Identify, S4 Assemble; S2/S3 say "Not available yet"
and the run ends `partial`. Reasons it makes no sense to a user: the stages are internal names; the two agent stages
are placeholders although their backends exist (TASK-055 document read, TASK-057 merge proposals); the two real
stages cost USD 0 and produce only a coverage summary; nothing leads toward a 3D result.

Why "F-12" and "15/9-F-12" stay separate today: PDFs read by the model (TASK-055) yield identity *proposals* that link
only on an exact normalised key; a block-less `F-12` is therefore a second wellbore. TASK-057 already proposes and
validates same-entity merges (including the block-less case, D9) but only the backend exists (no review UI, TASK-065
proposed) and no reconstruction stage invokes it.

## 3. Reconstruction run, redefined `[Proposed]`

| Stage | Name shown to the user | Kind | Content |
|---|---|---|---|
| S1 | Collect sources | deterministic | As today (exposure, gate, documents in scope) |
| S2 | Read documents | agent | For in-scope PDFs without a native profile, run the TASK-055 model read (category + wellbore identity proposals) with TASK-075 estimate rules; results are unverified proposals |
| S3 | Match wellbores | agent + deterministic | Group aliases of one wellbore (TASK-057 guards G1..G7), then re-resolve so **all files of the merged wellbore are one group**; review/revert in the UI |
| S4 | Assemble data | deterministic | Draft configuration from validated records and accepted candidates (as today) |
| S5 | Design 3D asset | agent + deterministic | Build the `VisualAssetSpec` (section 5) for the merged wellbore; optional bounded web search for visual references |

The modal explains each stage in plain words, shows what is *new work* vs *reused result* per stage, a cost per stage
and total (informational, no remaining budget, per TASK-075), and no "Not available yet" once the executors exist.
A stage that has nothing to do says so ("no documents need reading"). A run still never reads as success if a stage
failed or an agent step was stubbed.

**Merge autonomy `[Open Q1]`.** Today proposals are never auto-accepted. Owner wording: "the model must merge it".
`[Proposed]`: a proposal that passes every deterministic guard **and** carries verified alias quotes is applied
automatically as a persisted, revertible merge record, listed in the run detail with a one-click revert; anything that
fails a guard or has weak evidence stays a reviewable proposal. Different designators (renames) stay forbidden.

## 4. Inputs for the asset, in priority order (engineering-truth rules unchanged)

1. Source-dimensioned records and completion/schematic documents: native records (casing, tubing, perforations, trajectory)
   and TASK-041 equipment candidates (category taxonomy, MD, quote, page).
2. Catalog/web visual references for components whose manufacturer/model is documented in the sources
   (bounded research, section 6).
3. Generic illustrative shapes by category, clearly labelled.

Placement known from sources -> `located` at its MD interval; unknown -> `unlocated` (shown in a side preview, never at
an invented depth). Everything the model contributes is `model_read`/illustrative and never enters physical
calculations or the published engineering claims (EQ-9 stays in force).

## 5. The contract: `VisualAssetSpec` (declarative, no model code)

`[Proposed]` The agent never writes meshes, Blender scripts or three.js code. It emits a typed, versioned JSON document
validated server-side; a deterministic, reviewed renderer turns it into geometry.

- Header: project, wellbore id, source revision, merge/identity revision, spec version, generator (provider/model/run),
  generated-at, `status` (draft/accepted), `visual_only: true`.
- `components[]`: `id`, `kind` (closed enum of registered primitives: `casing`, `liner`, `tubing`, `packer`, `pump_esp`,
  `bearing`, `plug`, `nipple`, `valve`, `mandrel`, `perforation_interval`, `wellhead`, `christmas_tree`,
  `generic_block`), `label`, `placement` (`located` with `md_top`/`md_bottom` + unit + depth reference, or
  `unlocated`), optional bounded numeric `params` per kind (OD/ID/length, with unit), `representation`
  (`source_dimensioned` | `catalog_reference` | `generic_illustrative`), `evidence[]` (document/page/quote or
  candidate id), optional `visual_reference` {url, title, retrieved_at, note}, `confidence_note` (free text, not proof).
- Server validation: schema/enums/bounds; located components inside the trajectory MD range; no `source_dimensioned`
  without evidence; generic never marked dimensioned; reference URLs are strings (never fetched by the app); unknown
  kinds rejected; size limits. A rejected component is dropped with a finding; it never silently becomes a guess.
- Persistence: new table(s) keyed by project + wellbore + revision (migration reserved 0019), purge-safe.

## 6. Visual references from the web `[Proposed]`

Only when a component has a documented manufacturer/model/type and no schematic dimensions. An allowlisted tool
`research_visual_reference(manufacturer, model, kind)` (the provider's built-in web search if the live smoke shows
Muse Spark supports it, `[Open Q4]`) returns a text description of shape/proportions and a source URL. Limits follow the
equipment spec: at most 3 queries and 5 inspected pages per component, 60 s, disabled without explicit permission in the
confirmed estimate. The app stores URL, title, retrieval date and the description; it does **not** download or
redistribute images. Result labels: "external visual reference, not evidence of installation". Web pages are untrusted
data, never instructions.

## 7. Rendering and views

- **Technology `[Open Q2]`.** `[Proposed]` Three.js/React Three Fiber with a procedural, parametric primitive library
  driven by the spec (no per-asset GLB). Blender MCP at run time conflicts with the agreed boundaries (Blender is not a
  runtime dependency; model-generated bpy/scene scripts are never executed) and cannot work on the user's local
  single-user browser demo without a Blender install. Blender stays an *offline* authoring path for a few reusable
  hero GLBs (TASK-024) that the renderer may substitute per `kind`; it is not needed for the first slice.
- **Single-wellbore view** (Explore tab): trajectory tube from the deterministic minimum-curvature engine (TASK-007),
  components positioned by MD, radius exaggeration labelled, pick -> inspector with evidence/"illustrative" badge,
  keyboard asset list, local render origin, GPU resources disposed, no per-frame React state.
- **Field view**: all wellbores of the project in one scene, simplified LOD assets, instancing/shared materials, fly-to a
  wellbore, selection linked to the Reconstruction table. Trajectories only come from validated surveys.
- Draft preview `[Open Q3]`: `[Proposed]` a generated spec is viewable immediately as a **Draft** (badge) from the run
  detail; the Explore tab shows accepted specs only; acceptance is a single explicit user action after validation
  (the full review/publish UI, TASK-026, remains separate).

## 8. Scope boundaries

IN: S2/S3 executors and merge UI, redesigned modal, `VisualAssetSpec` contract/validator/persistence, asset-designer
agent with stub provider, renderer foundation and primitives, single and field views, bounded live acceptance.
OUT: plots/history/perforation time state, formations/reservoir/seabed layers, accurate CAD, published-model engineering
claims, OCR, equipment installation dates. These attach to the same wellbore asset in later features.

## 9. Acceptance criteria

| ID | Type | Criterion | Test |
|---|---|---|---|
| AG-1 | Behavioral | A project with `15/9-F-12` and block-less `F-12` sources: S3 proposes the merge with alias quotes; a guard-passing proposal is applied revertibly (or queued, per Q1); afterwards the Reconstruction table shows one wellbore with all files; revert restores two | pytest + browser |
| AG-2 | Negative | Different designators, parent/sidetrack, or guard-failing proposals never merge automatically; blocked proposals explain why | pytest |
| AG-3 | Behavioral | The reconstruction modal lists the five stages in plain language with per-stage cost and a total, no remaining budget, no "Not available yet" for implemented stages | vitest + browser |
| AG-4 | Behavioral | S5 turns candidates/records of a fixture wellbore into a valid `VisualAssetSpec`; invalid model output is dropped with findings; nothing is invented to fill gaps | pytest (stub + fake provider) |
| AG-5 | Negative | Generic/model-read components are labelled illustrative, never enter calculations or published claims; no `source_dimensioned` without evidence | pytest |
| AG-6 | Behavioral | Unknown placement renders in the unlocated preview, not at an invented MD | vitest + browser |
| AG-7 | Behavioral | Single-wellbore view renders trajectory and components from a spec; selecting a component shows its evidence/illustrative state; keyboard-accessible list | vitest + Playwright |
| AG-8 | Non-behavioral | Field view with >= 3 wellbores stays interactive on the WSL browser (reported frame time, draw calls); no leaks on tab switch | Playwright, measured |
| AG-9 | Negative | Visual-reference research respects limits, stores URL/date/description only, treats pages as untrusted, is off unless confirmed | pytest |
| AG-10 | Safety | Default tests and e2e never call Meta; live runs only with an explicit owner allowance and are reported separately | pytest guard |

## 10. Delivery plan (parallel worktrees, one writer each)

| Lane | Task | Content | Depends on | Owner agent |
|---|---|---|---|---|
| A | TASK-075 | Estimate from real text, page choice, chunked calls, no spend gates | none | fieldlens-rag (backend) + fieldlens-frontend |
| B | TASK-076 | S2/S3 executors, auto-apply merge policy, merge review UI (absorbs TASK-065), new modal | TASK-055, TASK-057 | fieldlens-rag + fieldlens-frontend |
| C | TASK-077 | `VisualAssetSpec` contract, validator, persistence (migration 0019), stub designer, fixtures | TASK-041 (candidates) | fieldlens-backend |
| D | TASK-078 | R3F foundation, primitive library, single-wellbore view on fixture specs | TASK-077 contract merged | fieldlens-3d-motion |
| E | TASK-079 | S5 live asset designer + visual-reference tool + estimate | TASK-076, TASK-077 | fieldlens-rag |
| F | TASK-080 | Field (multi-wellbore) view, LOD/instancing | TASK-078 | fieldlens-3d-motion |
| G | TASK-081 | Independent QA + bounded live acceptance (owner allowance) | all | fieldlens-qa |

Parallelism: A, B, C start together; D starts when C's contract commit is merged (a small first merge); E after B and
C; F after D. Serialized shared surfaces: contract registry + `generated.ts` (merge order C -> B -> A rebases), Alembic
heads (0018 reserved for B, 0019 for C; 0017 is current), VERSION/CHANGELOG (orchestrator, one bump per merge).
Release plan: A = 0.38.0, B = 0.39.0, C = 0.40.0 (contract only), D = 0.41.0, E = 0.42.0, F = 0.43.0.
Every lane gets independent QA before merge.

## 11. Schedule reality (deadline 2026-11-04 21:00 EST)

About 45 hours remain. A and B are 0.5-1 day each; C is about half a day; D (first 3D in the app, none exists today)
and E are the long poles. `[Proposed]` priority if time is short: A -> B -> C -> D -> E, with F (field view) as the first
item to cut; do not downgrade AG-7 (single view) silently.

## 12. Failure behaviour

Model failure, malformed spec or provider outage leaves the previous accepted spec untouched, records the run as
failed/partial, spends only what was reserved, and never produces a scene with invented values. A merge that is reverted
re-groups files and invalidates the dependent draft spec.

## 13. Open questions for the owner

- **Q1 Merge autonomy:** auto-apply guard-passing, quote-verified merges (revertible), or always ask? (default above: auto-apply)
- **Q2 Rendering:** declarative spec + Three.js primitives (my proposal) vs Blender MCP at run time. If Blender MCP is wanted
  for development-time authoring of reusable GLBs only, that is compatible (TASK-024).
- **Q3 Preview/acceptance:** draft preview with one-click accept (default) vs publish-only.
- **Q4 Web search:** allowed to use the provider's web search for visual references; per-run permission in the estimate
  (default), and USD allowance for the live acceptance run (needs a number).
- **Q5 Scope of the first demo wellbore:** F-12 (generic placeholders where dimensions are missing) first, or F-14/F-5
  (source-dimensioned)? Default: F-14 or F-5 for the dimensioned showpiece, F-12 for the generic/unlocated case.

## 14. Owner decisions (2026-11-02 23:40)

- **Q2 Rendering:** declarative spec rendered by Three.js (or comparable); it must look visually appealing. Blender MCP not used at run time.
- **Q4 Web visual references:** images may be stored (as a bounded, size-limited, content-type-checked file) or kept as a URL. No USD limit on the
  search; instead guard against loops: bounded number of queries/pages, stop on repeated queries/URLs, a wall-clock limit, and a clear
  "found / not found" outcome. This supersedes the "3 queries / 5 pages" and "no image download" figures in section 6 for this feature only:
  the limits become configurable step limits (defaults 6 queries, 10 pages, 120 s per component).
- **Q5 Test wellbore:** the most complete wellbore of the project; the rest are processed by the owner afterwards.
- **Q6 Pages:** `1..N` is sufficient.
- **Estimate:** computed from the real document text (token count of the actual selected pages), as in MODEL_PROCESSING_OUTCOME section 8.
- **Q1 (owner, 23:46): ALWAYS ASK.** Nothing merges automatically. S3 only creates merge proposals (alias quotes, guard results); a merge is applied only when the user clicks Accept on that proposal; applied merges stay revertible. This supersedes the auto-apply wording in sections 3 and AG-1.
- **Q3 (owner, 23:46): SHOW DIRECTLY.** A generated asset appears in the viewer immediately; there is no Draft/Accept gate. The latest valid generated spec per wellbore is the current one; earlier ones are kept as history; a failed generation leaves the current one untouched. The 'Draft' badge/Accept action in sections 5 and 7 is removed; the 'illustrative / visual only' label stays.
- **Component scope (owner, 23:46):** everything that contributes to visual presence belongs in the composite model: casing, liner, tubing, packers, pumps, valves, wellhead, christmas tree and also surface facilities such as separators, chokes, manifolds, tanks and flowlines. The closed kind enum is extended accordingly (e.g. `separator`, `choke`, `manifold`, `tank`, `flowline`, `pump_surface`). **Every element carries a visible label** (non-empty, validated; shown in the 3D view and the list).

## 15. TASK-079 implementation notes (S5 live designer)

- **Division of labour.** The model sees a bounded, ref-labelled list of the wellbore's equipment candidates (untrusted data) and
  returns per ref only `kind`, `label`, wanted `representation` and a short `note`. The server builds every component from the stored
  candidate: dimensions only from printed numbers, `located` only from a complete printed MD interval (otherwise `unlocated`),
  surface facilities at `surface`, evidence from the candidate. The model can only downgrade: `source_dimensioned` needs printed
  dimensions and evidence, `catalog_reference` needs a stored external reference (and carries no numbers), everything else is
  `generic_illustrative` with a "Missing: ..." comment. Candidates the model omits are kept deterministically; invented refs,
  duplicate refs and unknown kinds are dropped and counted. A component the validator rejects is rebuilt as a generic one.
- **Outcomes.** Refusal, truncation, malformed output, provider failure and validation failure leave the current spec untouched
  and make S5 a non-fatal `failed` stage (run `partial`); a successful S5 lets the run end `succeeded`. Without a live model S5 is
  `stubbed` and stores nothing (the existing "Generate (stub)" route is unchanged). A run belongs to one wellbore; a bulk estimate
  queues one run per wellbore. A user-confirmed run is the authorization; the S5 estimate is information only (no spend gate).
- **Visual-reference research (`assetspec/research.py`).** Pluggable `SearchBackend`, OFF by default (`FIELDLENS_VISUAL_RESEARCH_BACKEND=off`
  is the only shipped value; limits `FIELDLENS_VISUAL_RESEARCH_MAX_QUERIES=6`, `_MAX_PAGES=10`, `_DEADLINE_S=120` per component, no USD
  limit). Only a short equipment-name hint leaves the app. Only URLs returned by the backend are fetched; http/https on 80/443,
  all resolved addresses must be public, the connection is pinned to the validated address, every redirect is re-validated,
  response size/time/content type are capped, at most 8 components per wellbore are researched, repeated queries/URLs stop the loop and the
  result is an explicit found / not found. The model never receives page text or URLs, only a sanitised title. Stored: URL, title,
  retrieval date, labelled note ("External visual reference, not evidence of installation") and optionally a content-addressed image
  file (png/jpeg/webp, <= 2 MiB) under `<storage root>/visual-references`.
- **MD range.** S5 passes the wellbore's known maximum MD (`identity.resolver.known_md_max`, +5%) to the validator; a located part beyond it becomes an unlocated generic one. A wellbore with no trajectory/log range gets no check (never guessed).
- **Not done / open.** No real search backend is shipped (needs an owner-chosen provider and key); Meta built-in web search is not
  used. No live Meta call was made (AG-10).
