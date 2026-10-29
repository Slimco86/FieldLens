---
goal: Deliver the complete evidence-backed FieldLens local hackathon application
version: 4
date_created: 2026-10-27
last_updated: 2026-10-28
owner: FieldLens project owner and main orchestrator
status: Planned
tags: [architecture, implementation, orchestration, evidence, hackathon]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

**Implementation planning baseline confirmed, 2026-10-28.** The owner selected
F-12/F-14/F-5, accepted evidence-safe generic F-12 equipment and visible
discrepancies, and explicitly confirmed hybrid categories, review/publication and
128 MiB/file, 512 MiB/batch, 200-file limits. The cohort/planning hold is released.
Final G1, live-spend approval and host/tool preflight remain separate gates.
The owner integrated these packets in `9d630e3` and authorized the first three
handoffs. Activation verified the requested models but found no worker file-edit
tool; application implementation is blocked pending host capability repair.
At 14:47 EDT the owner replaced parallel worktrees with one feature branch at a
time in the existing checkout. Subagents launch from the main session; tool
preflight still applies. Existing worktrees remain inactive and preserved.

No application is implemented. This is the revised sequence for the
[architecture](../docs/ARCHITECTURE.md)
and [feature specs](../docs/specs/README.md). It preserves all mandatory scope,
existing backlog IDs and owner approval gates. Blank Completed/Date cells mean
unexecuted work, not missing information.
The [first detailed packets](feature-foundation-workspace-1.md) expand the
foundation, project lifecycle and upload/job tasks into file-owned implementation
steps with exact checks. Later slices use their feature contracts and receive a
launch-time assignment only after prerequisite interfaces/source subsets freeze.

## 1. Requirements & Constraints

- **REQ-001**: Fresh upload must produce source-backed trajectories/equipment,
  temporal perforations, seabed/formations, both chart families and cited Meta tools.
- **REQ-002**: Preserve all project AC-1 through AC-10 using the
  [traceability matrix](../docs/specs/README.md); no generic-only or cached-only success.
- **REQ-003**: AC-11/12 add project isolation, categorized incremental uploads
  and evidence-led composite-asset reconstruction, not just retrieval over a scene.
- **REQ-004**: Each product checkpoint has a browser walkthrough with real
  persistence, visible error states and source evidence; offline and live checks
  are labeled separately. Supporting backend tasks are not owner-visible milestones.
- **REQ-005**: F-12 generic equipment and F-14/F-12 conflicting records are
  required observable limitation cases, not exceptions to grounding. At least one
  real installed assembly still passes DF-9; no invented placement/dimensions.
- **SEC-001**: No secrets/private documents in commits, browser/model context or
  logs; no arbitrary model code/SQL/URLs, access-policy changes or automatic publication.
- **CON-001**: Deadline 2026-11-04 21:00 America/New_York, UTC-05:00; indie track,
  public code and <=180-second video. Dates below are local New York calendar dates.
- **CON-002**: USD 150 total Meta allowance is not the current balance. Default
  tests use zero paid calls; all live allowances require the shared ledger/approval.
- **CON-003**: Current WSL has 7.6 GiB RAM, not twenty workers' worth of memory.
  At most one active code worker; one heavy test/parser/build workload at a time.
- **GUD-001**: Do not start a task until its explicit dependencies are integrated,
  its spec approved and its profile/model/tools/resources verified.
- **PAT-001**: Freeze shared contracts first, use one feature branch at a time in
  the shared checkout, and serialize all writers, tests and integration.

## 2. Implementation Steps

The **Depends on** column is the authoritative task DAG. A comma means all named
tasks are required; `None` means no task predecessor. Global approval/permission
gates above still apply. Backlog parent rows summarize outcomes, not scheduling.
Source-data tasks cannot be promoted by a mocked dependent test.

### Implementation Phase 1

- **GOAL-001**: Browser checkpoint A: create/reopen two projects, upload a small
  permitted file, inspect stored bytes/hash/category/job status, reload and verify
  isolation. No extraction/model success is implied by file storage.
  TASK-002 is an independent final-data track, not an exit condition for A.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-001 | FL-001 | None | Main agent verifies DA-7 actual host model/effort/tools for each profile used, confirms approved design is committed, and records exact integration base before any implementation delegation. | | |
| TASK-002 | FL-002 | None | Complete DF-1..9 for owner-selected F-12/F-14/F-5: produce ignored `data/volve/demo-manifest.json` with hashes/rights/profiles/windows/expected records and independent reference/state fixtures. Use verified F-5 images/F-14 drawing and preserve F-12's approved generic limitation; tally search is not a prerequisite for source-free implementation. No bulk download, automatic F-11 B substitution or false G1 pass. | | |
| TASK-003 | FL-004-A | TASK-001 | Backend owner implements FN-1..6 and SC-1..6 in contracts/persistence/migrations, root locks and frontend app/API shell. Real PostgreSQL, loopback readiness and test commands; single shared-contract writer. | Yes; 0.4.0 / `1293f55`, owner direct-repair/verification exception | 2026-10-28 |
| TASK-025 | FL-015-A | TASK-003 | Backend owner implements project lifecycle/membership in backend/fieldlens/projects and frontend/src/features/projects; PW-1/2/5/8 with keyboard navigation and real persistence. | Yes; independent QA, 0.5.0 / `3e748d9` (lifecycle surfaces only) | 2026-10-28 |
| TASK-006 | FL-005-A | TASK-025 | Backend owner implements project upload/jobs/source list in ingestion/jobs/evidence and frontend upload; IN-1/3/4/5/7 and PW-3/4/6/7. Label stored/unsupported/pending extraction explicitly; never publish an asset model. | | |

### Implementation Phase 2

- **GOAL-002**: Browser checkpoint B: inspect extracted rows/pages, units,
  classification conflicts, coverage and a linked warning/error inspector; ask a cited source question before a
  graph/scene exists. Native evidence browsing can pass while scans are explicitly
  partial. Live source chat requires TASK-005/027; a stub does not pass that part.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-004 | FL-003-A | TASK-003 | RAG worker implements MI-1..5 offline provider adapter, PostgreSQL budget reservations and finite failure/cancellation behavior in `backend/fieldlens/assistant/`; no live calls. | | |
| TASK-005 | FL-003-B | TASK-004 | RAG worker runs MI-6 only after approved USD 1 ceiling and balance/key readiness; record actual entitlement/tool protocol. No pilot documents needed. | | |
| TASK-009 | FL-005-B | TASK-006 | Ingestion owner implements selected qualified native source profiles and evidence UI: IN-2/6 for this subset, exact record/page coverage and wrong-folder fixture. Small approved subset, not full IN-8/G1 acceptance. | | |
| TASK-032 | FL-017-A | TASK-009 | Frontend owner implements scoped issue API/list/detail/evidence navigation in `backend/fieldlens/evidence/issues.py` and `frontend/src/features/evidence/quality/`; DQ-1/2/3/4/7 and DTO-negative DQ-5/6. Serialize shared schema/client edits; source-first, no graph/3D prerequisite. | | |
| TASK-011 | FL-011-A | TASK-009 | RAG owner implements project/source-scoped exact/text/vector retrieval in retrieval, source coverage and bounded evidence search; unresolved observations are labeled. No accepted asset graph prerequisite; embedding gate/degradation explicit. | | |
| TASK-019 | FL-011-B | TASK-004, TASK-011 | RAG owner implements source-context chat/evidence UI, RG-8 offline and applicable RG-3/4/5; no geometry tools or reconstruction writes from chat. | | |
| TASK-027 | FL-011-D | TASK-005, TASK-019 | RAG owner verifies all three early live source-chat cases under separately approved <=USD 1 allowance; records exact citation/gap/refusal results. Not the complete RG-6 evaluation. | | |
| TASK-030 | FL-005-C | TASK-009 | Ingestion owner qualifies scanned-PDF and legacy-Word embedded-image profiles for selected F-14/F-5 evidence, with original locators, safe evidence viewer and human-checked attribute fixtures. Required for selected equipment, not optional OCR polish. | | |

### Implementation Phase 3

- **GOAL-003**: Browser checkpoint C: run reconstruction, inspect a candidate
  hierarchy/configuration timeline, follow attribute/edge citations, see conflicts,
  review a diff and publish/reject. A correction produces a new draft without
  changing the active model. Live Meta reconstruction is verified before claiming
  the agent delivered; no 3D dependency.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-026 | FL-016-A | TASK-019, TASK-032 | RAG owner implements reconstruction proposals/validator/review UI in reconstruction and shared assistant harness; RC-1..9 offline, DQ-6 publication boundaries, real database transactions and source-backed fixtures. Reuse issue inspector; coordinate migrations with backend; do not generate accepted facts in the model. | | |
| TASK-028 | FL-016-B | TASK-005, TASK-026, TASK-030 | RAG owner runs RC-10 on 12 independently authored gold cases and selected qualified source records under separately approved <=USD 3 allowance; record actual tool-dependent reconstruction, support and unresolved states. | | |

### Implementation Phase 4

- **GOAL-004**: Checkpoint D first adds published trajectories/equipment with linked
  evidence. Checkpoints E1/E2/E3 separately add historical state, seabed/formations,
  and production/log charts, then linked overlays/tools. Every increment has a
  browser verification; charts need a published model, not a finished 3D renderer.
  Numeric engines can start after TASK-003 despite appearing in this phase.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-007 | FL-006-A | TASK-003 | Geospatial owner implements TR-1/2/3 analytic trajectory/reference/proximity engine and unit tests in engineering; no renderer or pilot acceptance claimed. | | |
| TASK-008 | FL-008-A | TASK-003 | Geospatial owner implements PH-2/3/5/6/7/9 deterministic state/union engine; exact t0..t6 fixtures, unknown baselines and same-day ambiguity. | | |
| TASK-010 | FL-006-B | TASK-007, TASK-026 | 3D owner implements published-model scene/tree, local-origin buffers and evidence selection, TR-4..7 on qualified survey subset; never read active facts directly from upload staging. | | |
| TASK-012 | FL-007-A | TASK-010, TASK-030 | 3D worker implements source-dimensioned procedural equipment, inspector, catalog/generic/unlocated states and EQ-1..7/DQ-5 from qualified evidence. Demonstrate F-14/F-5 dimensional candidates and F-12's explicit limitation; no guessed depth, generated engineering values or Blender prerequisite. | | |
| TASK-013 | FL-008-B | TASK-008, TASK-009, TASK-010 | Frontend worker wires canonical historical state to real events, MD placement/time controls/inspector and PH-1/4/8; retain acquisition dates and context guards. | | |
| TASK-014 | FL-009-A | TASK-009, TASK-010 | Geospatial worker implements seabed source projection, typed layer API/component and CX-1/3/4/5; owns seabed-specific files. | | |
| TASK-015 | FL-009-B | TASK-009, TASK-010 | Geospatial worker implements formation depth horizons/picks, interpolation/source masks and CX-2/3/4/5; verify combined CX-6 after both layers integrate. | | |
| TASK-016 | FL-010-A | TASK-009, TASK-026 | Frontend worker implements production endpoints/chart/units/periods/evidence with CH-1/3/4/6 on published model context; owns production-specific files. | | |
| TASK-017 | FL-010-B | TASK-009, TASK-026 | Frontend worker implements depth-log endpoints/tracks/nulls/acquisition evidence with CH-2/3/4/6 on published model context; owns log-specific files. | | |
| TASK-018 | FL-010-C | TASK-013, TASK-016, TASK-017 | Frontend worker integrates PH overlays/shared as-of state and CH-5/7 across both chart families; tests rapid context changes. | | |
| TASK-031 | FL-011-E | TASK-019, TASK-012, TASK-013, TASK-014, TASK-015, TASK-018 | RAG owner extends existing chat with published-graph retrieval, all domain/navigation tools and RG-1..5/7; UI acknowledges applied/rejected/stale actions. Same harness/ledger, no second agent backend. | | |

### Implementation Phase 5

- **GOAL-005**: Verify grounded assistance and the complete application, then prepare
  authorized delivery. Target: November 1-4. Exit: all DM criteria and publication
  requirements satisfied; provider replays do not count as live checks.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-029 | FL-005-D | TASK-002, TASK-009, TASK-030 | Ingestion owner verifies IN-8 and real-source DQ-8 inputs across the final approved manifest, including expected conflicts/generic gaps as explicit outcomes. Required profiles and independent records must match; accepted limitations are not fabricated success or full coverage. | | |
| TASK-020 | FL-011-C | TASK-005, TASK-029, TASK-031 | RAG worker runs the fixed 32-case live gold evaluation under approved USD 3 allowance; record RG-6 and authorized equipment-research coverage, not just successful text generation. | | |
| TASK-021 | FL-012-A | TASK-031 | QA verifies combined create-project -> upload -> reconstruction review/publication -> scene/history/charts browser path with stub provider, negative paths/accessibility and AC-9/RSS. Feature owners fix defects. | | |
| TASK-022 | FL-012-B | TASK-002, TASK-020, TASK-021, TASK-027, TASK-028, TASK-029 | QA verifies the real-source/live-provider path, all 12 project ACs and DQ-1..8 on the candidate SHA; show F-12 generic/unlocated state and real conflicts, with isolated DB/storage and actual usage/evidence. | | |
| TASK-023 | FL-012-C | TASK-022 | Main agent finalizes operator instructions, rights-safe release inventory, VERSION/CHANGELOG and candidate; owner verifies G4, records <=180 s video and explicitly authorizes publication/submission. | | |

### Implementation Phase 6

- **GOAL-006**: Optionally improve a source-backed discrete device without displacing
  mandatory work. Execute only with owner asset approval and spare schedule/RSS.
  This task is not a prerequisite for TASK-023 or any required acceptance gate.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-024 | FL-007-B | TASK-012 | 3D worker uses approved Blender build/skill to create one source-backed asset and verify scale/IDs/GLB/budgets from the equipment spec. Skip rather than delay required features; no claim of completed asset when skipped. | | |

### Dispatch, ownership and resource allocation

The main agent retains global architecture, approval handling and integration.
Use configured profile defaults: Terra for fully specified low-risk commands/
boilerplate; domain Sonnet for the substantive slices above; Sol for one bounded
contract gap only. Do not use a short diff as proof of low engineering risk.
Missing actual model/tool capability blocks dispatch; no silent model override.

At launch, assign a new branch `feature/<slice>-<slug>` in
`/home/slimco/code/FieldLens`. Capture
`git rev-parse master` only after approved specs are committed; the first packet's
approved base is `9d630e32af898cdc9292451b5258f9c2f9a1a06d`.
Do not invent future hashes or create additional worktrees. Only the orchestrator
switches branches, after workers/checks/helpers stop and pending changes are safe.
Finish and integrate the active feature before starting the next.

| Resource | Single implementation lane | Integration/demo |
|---|---|---|
| API port | 8101 | 8100 |
| Frontend port | 5174 | 5173 |
| PostgreSQL | Loopback 55432 service, distinct task database | Dedicated demo/integration databases |
| Database naming | `fieldlens_<slice>_w1`, hyphens replaced by underscores | `fieldlens_demo`, separate `fieldlens_integration` |
| DB identities | Task-scoped role; no access to another task/demo DB | Owner-provisioned integration role |
| Storage | Task-specific untracked source/output/temp roots | Dedicated accepted manifest/artifacts |
| Heavy workload | At most one; no concurrent feature or QA work | Rehearsal owns the slot exclusively |

Verify ports/database ownership before use; if occupied, main agent records a new
specific allocation rather than terminating someone else's process. Only one
PostgreSQL container is planned (`fieldlens-db` Compose project); pin its image,
give each task a separate database and do not remove its volume during worker
cleanup. Native service use requires an explicit equivalent isolated configuration.

Root manifests/lockfiles, migration head, shared Pydantic schemas, generated TS,
app composition and global release files have **one writer at a time**.
Feature workers own isolated modules from their specs. Schema changes are reviewed
and integrated first; regenerate clients before dependent tests. No worker merges,
pushes, publishes, edits another tree or spawns workers.

Default assignment bound: one vertical slice, 90 minutes before handoff/checkpoint,
two attempts without new evidence before returning a blocker. A bounded extension
requires a new orchestrator allocation, not an endless autonomous loop.
Record actual tools/model/elapsed usage when exposed; unknown telemetry is unknown.
Heavy worker target 1536 MiB RSS, two numeric threads; stop scheduling below
1 GiB available WSL memory. QA/rehearsal pauses builds and optional Blender.

### Critical path, integration and calendar checkpoints

Product learning path:
TASK-003 -> TASK-025 -> TASK-006 -> TASK-009 -> TASK-011 -> TASK-019 ->
TASK-026 -> TASK-010/016/017 -> enrichment -> TASK-031 -> acceptance.
The early provider branch TASK-004/005/027 and reconstruction live check TASK-028
expose agent risk before the full scene. TASK-002/029 converge at final real-data
acceptance, not at project creation. TASK-030 is a source-specific prerequisite
for using scanned/Word equipment evidence. Numeric engines TASK-007/008 are
independent after foundation. This is a dependency priority, not measured slack.

Before any real-source checkpoint, record a qualified subset: immutable hashes,
rights/provider permissions, source subjects/locators, required fields and
reference/time meanings, known conflicts and independently checked expected
outputs. The main agent records approval for that subset; it does not mark full
G1 passed. Synthetic fixtures remain labeled synthetic. No stage may conceal
unsupported sources or count unavailable model tools as working features.

| Checkpoint | Required observation | If missed |
|---|---|---|
| Oct 28 evening | Confirmed defaults; review/integrate packets and preflight; target checkpoint A persists projects/files | Rebaseline dates rather than bypass packet/profile prerequisites |
| Oct 29 evening | Checkpoint B: inspect evidence and qualified early live source chat | Isolate parser/provider blocker; do not defer all Meta testing until the end |
| Oct 30 evening | Checkpoint C: source-backed reconstruction, review and live gold results | Fix identity/support/time/tool failures before extending scene polish |
| Oct 31 evening | Checkpoint D and E increments integrated with real evidence | Spend capacity on required equipment/history/context/both charts, not optional GLB |
| Nov 1 evening | Final G1/IN-8 and full tool/gold evaluation passing | Resolve exact source/coverage failures; no citation/grounding relaxation |
| Nov 2 evening | Combined real/live acceptance and performance run complete | Escalate exact failed ACs; do not call mock/replay success a release |
| Nov 3 | Code freeze except verified fixes; rehearse and prepare recording | Rerun affected checks for every post-freeze change |
| Nov 4, 17:00 | Owner has final package/video and verified submission checklist | Keep four-hour buffer before 21:00 EST deadline; no unauthorized publication |

These are proposed scheduling checkpoints, not owner promises or proof the scope
fits. The owner-approved F-12 generic limitation and explicit uncertainty are valid
demo outcomes, not a requirement to find every missing dimension. If an entire
mandatory capability lacks qualifying real evidence, the **full requested demo
cannot be accepted**. Warnings never authorize unvalidated calculations.

Integration is serialized: receive tested commit/handoff -> reconcile with latest
master -> run affected combined checks -> classify compatibility -> allocate one
version bump -> finalize changelog/docs -> commit/merge using authorized policy ->
verify target SHA -> reconcile backlog. No automatic push/tag/publication.
Pending changes and inactive legacy worktrees are preserved; no automatic removal.

## 3. Alternatives

- **ALT-001**: Microservices/Redis/Celery/Node API rejected: no demonstrated need
  for the local workload, more memory and operational failure surfaces.
- **ALT-002**: Dedicated graph/vector databases rejected: PostgreSQL satisfies
  typed relations and bounded retrieval; revisit only after measured failure.
- **ALT-003**: CAD-first reconstruction rejected: source dimensions and placement
  precede meshes; optional Blender cannot repair absent installation evidence.
- **ALT-004**: Waiting for every external gate before writing architecture rejected:
  inspected evidence supports stable validation/provenance boundaries now; gate
  affected execution/acceptance instead. This does not approve source-free coding
  of uninspected adapter semantics.

## 4. Dependencies

- **DEP-001**: Local source access is resolved. Final G1 still needs manifest,
  rights, reference/time compatibility and independent fixtures; early stages
  require their own qualified subsets, not the whole final corpus.
- **DEP-002**: G2 Meta entitlement/current balance/protocol, separately gated by
  MI-6; local key existence does not establish success.
- **DEP-003**: G5 Node 24/Python 3.12/DB/package/image compatibility and optional
  OCR/embedding resource/license qualification; foundation records real versions.
- **DEP-004**: FL-001 actual host activation and committed approved specifications,
  plus owner approval for live spend, source expansions and publication.
- **DEP-005**: G4 authenticated final rules and rights-safe public-code/video review.

## 5. Files

- **FILE-001**: `backend/fieldlens/`, `backend/tests/`, `backend/migrations/` and
  root Python manifest/lock: projects, ingestion, reconstruction, engineering and
  shared assistant harness. Feature specs define narrower single-writer ownership.
- **FILE-002**: `frontend/src/`, `frontend/tests/` and npm manifests/lock:
  generated types, linked UI, scene, evidence and both chart families.
- **FILE-003**: `infra/compose.yaml`, `scripts/`, `tests/fixtures/`: isolated local
  service setup, contract generation and permitted deterministic fixtures.
- **FILE-004**: Existing `docs/specs/`, `docs/BACKLOG.md`, `README.md`, `VERSION`
  and `CHANGELOG.md`: actual acceptance, operator instructions and serial integration.

## 6. Testing

- **TEST-001**: Foundation establishes the documented pytest/Ruff/mypy and
  npm lint/typecheck/Vitest/build/contract-generation commands; no placeholder
  successful checks and no SQLite substitution.
- **TEST-002**: Unit engineering/source contracts use independent analytic
  fixtures, PH t0..t6 states, malformed/hostile sources and explicit unknowns.
- **TEST-003**: PostgreSQL integration verifies project/source/model membership,
  migrations, fenced recovery, publication races, budget races, source idempotency,
  correction invalidation and retrieval scope.
- **TEST-004**: Frontend interactions verify shared context, cancellation/races,
  both chart families, scene/evidence alternatives and action acknowledgment.
- **TEST-005**: Playwright runs fresh-import and failure/accessibility scenarios;
  benchmark all required layers plus local reads during import, not an empty scene.
- **TEST-006**: Opt-in MI/RG/RC live checks record actual provider/gold-case/spend
  evidence. Default suites run with outbound/provider calls prohibited.
- **TEST-007**: DQ-1..8/EQ-7 exercise named F-14 reference and F-12 interval
  conflicts, generic/unlocated rendering, persistent evidence and server-side
  blocked outputs. Synthetic tests and real-source detection are separate results.

Plan validation: unique TASK/GOAL declarations, resolvable dependencies/acyclic
DAG, unique slice IDs, valid linked specs, all project ACs traced, optional TASK-024
absent from required task ancestors, and consistent pending version metadata.

## 7. Risks & Assumptions

- **RISK-001**: Missing official completion/history/context data may prevent the
  full demo. Owner/provider resolution is not an autonomous permission change.
- **RISK-002**: Native parsing may expose unsupported profiles/OCR memory costs.
  Preserve failed evidence and narrow work; do not invent content or install every parser.
- **RISK-003**: Switching the shared checkout while workers or watchers are active
  can invalidate tests or mix feature files. Enforce one feature/writer and one
  heavy slot; stop branch-bound work before the orchestrator switches branches.
- **RISK-004**: Late live-provider/rules failures can block delivery. Run G2/G4
  checks early; keep final live rehearsal and a four-hour submission buffer.
- **ASSUMPTION-001**: The owner can approve the design and arrange authorized
  source/service access; unknown availability is not treated as a completed task.
- **ASSUMPTION-002**: Current stack families can resolve on this WSL host; G5
  verifies actual locks/wheels/peer versions before accepted implementation.
- **ASSUMPTION-003**: The owner keeps mandatory scope unless explicitly amended;
  the schedule does not authorize turning context/logs/history into stretch goals.

## 8. Related Specifications / Further Reading

- [Architecture](../docs/ARCHITECTURE.md)
- [Feature specifications and traceability](../docs/specs/README.md)
- [Shared contracts](../docs/specs/SHARED_CONTRACTS.md)
- [Project workspace](../docs/specs/PROJECT_WORKSPACE.md)
- [Composite reconstruction](../docs/specs/ASSET_RECONSTRUCTION.md)
- [Persistent backlog](../docs/BACKLOG.md)
- [Development workflow](../docs/DEVELOPMENT_WORKFLOW.md)
- [Agent roster](../.github/agents/README.md)
- [Equipment source findings](../docs/EQUIPMENT_DATA_FEASIBILITY.md)
