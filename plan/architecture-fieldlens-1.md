---
goal: Deliver the complete evidence-backed FieldLens local hackathon application
version: 1
date_created: 2026-10-27
last_updated: 2026-10-27
owner: FieldLens project owner and main orchestrator
status: Planned
tags: [architecture, implementation, orchestration, evidence, hackathon]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

The architecture and work breakdown are complete; the application is not.
This is the executable sequence for the [architecture](../docs/ARCHITECTURE.md)
and [feature specs](../docs/specs/README.md). It preserves all mandatory scope,
existing backlog IDs and owner approval gates. Blank Completed/Date cells mean
unexecuted work, not missing information.

## 1. Requirements & Constraints

- **REQ-001**: Fresh upload must produce source-backed trajectories/equipment,
  temporal perforations, seabed/formations, both chart families and cited Meta tools.
- **REQ-002**: Preserve all project AC-1 through AC-10 using the
  [traceability matrix](../docs/specs/README.md); no generic-only or cached-only success.
- **SEC-001**: No secrets/private documents in commits, browser/model context or
  logs; no arbitrary model code/SQL/URLs, access-policy changes or automatic publication.
- **CON-001**: Deadline 2026-11-04 21:00 America/New_York, UTC-05:00; indie track,
  public code and <=180-second video. Dates below are local New York calendar dates.
- **CON-002**: USD 150 total Meta allowance is not the current balance. Default
  tests use zero paid calls; all live allowances require the shared ledger/approval.
- **CON-003**: Current WSL has 7.6 GiB RAM, not twenty workers' worth of memory.
  At most two active code workers; one heavy test/parser/build workload at a time.
- **GUD-001**: Do not start a task until its explicit dependencies are integrated,
  its spec approved and its profile/model/tools/resources verified.
- **PAT-001**: Freeze shared contracts first, use independent worktrees for complete
  vertical slices, and serialize migrations, generated clients and release metadata.

## 2. Implementation Steps

The **Depends on** column is the authoritative task DAG. A comma means all named
tasks are required; `None` means no task predecessor. Global approval/permission
gates above still apply. Backlog parent rows summarize outcomes, not scheduling.
Source-data tasks cannot be promoted by a mocked dependent test.

### Implementation Phase 1

- **GOAL-001**: Establish activation and real-data evidence without changing access
  privileges. Target: October 27-28. Exit: activation recorded; data task either
  passes DF-1..9 or remains explicitly blocked. A blocked TASK-002 does not block
  source-independent Phase 2 work.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-001 | FL-001 | None | Main agent verifies DA-7 actual host model/effort/tools for each profile used, confirms approved design is committed, and records exact integration base before any implementation delegation. | | |
| TASK-002 | FL-002 | None | Owner/provider restores approved volume access or supplies authorized local files; ingestion/geospatial owners complete DF-1..9 manifest and independent fixtures. Inspect source rights/headers/time/reference mappings. No permission workaround, paid upgrade or unapproved large EDM download. | | |

### Implementation Phase 2

- **GOAL-002**: Produce a tested foundation and independently useful contract
  slices. Target: October 28. Exit: each task's specified offline/live criteria
  recorded separately. After TASK-003, TASK-004/006/007/008 are independent;
  run no more than two code workers simultaneously.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-003 | FL-004-A | TASK-001 | Backend worker implements FN-1..6 and SC-1..6: manifests/locks, migrations, loopback API, generated types, accessible shell and real test commands. Own root manifests and all shared-contract files. | | |
| TASK-004 | FL-003-A | TASK-003 | RAG worker implements MI-1..5 offline provider adapter, PostgreSQL budget reservations and finite failure/cancellation behavior in `backend/fieldlens/assistant/`; no live calls. | | |
| TASK-005 | FL-003-B | TASK-004 | RAG worker runs MI-6 only after approved USD 1 ceiling and balance/key readiness; record actual entitlement/tool protocol. No pilot documents needed. | | |
| TASK-006 | FL-005-A | TASK-003 | Backend worker implements upload/jobs/source evidence UI and IN-1/3/4/5/7 with synthetic fixtures; persistent retries/publication/fencing and explicit failures. | | |
| TASK-007 | FL-006-A | TASK-003 | Geospatial worker implements TR-1/2/3 analytic trajectory/reference/proximity engine and unit tests; no renderer or pilot acceptance claimed. | | |
| TASK-008 | FL-008-A | TASK-003 | Geospatial worker implements PH-2/3/5/6/7/9 synthetic state replay/union persistence; include exact t0..t6 fixtures, unknown baselines and same-day ambiguity. | | |

### Implementation Phase 3

- **GOAL-003**: Complete the first real upload-to-scene/evidence path and retrieval
  indexing. Target: October 29. Exit: approved pilot import and TR-7 pass.
  TASK-010 and TASK-011 can proceed independently after TASK-009.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-009 | FL-005-B | TASK-002, TASK-006 | Ingestion worker implements approved CSV/DAT/XLSX/LAS/WITSML/native-PDF profiles, IN-2/6/8, complete locators and gold record coverage. Optional OCR requires its measured profile gate. | | |
| TASK-010 | FL-006-B | TASK-007, TASK-009 | 3D worker implements imported scene/asset tree, local-origin buffers, evidence selection, TR-4..7 and scene benchmark. | | |
| TASK-011 | FL-011-A | TASK-009 | RAG worker implements scoped exact/full-text/vector/typed-graph retrieval, approved embedding fingerprint, RG-1/2 and offline gold evidence metrics. | | |

### Implementation Phase 4

- **GOAL-004**: Integrate all required enriched-scene capabilities.
  Target: October 30-31. Exit: EQ-6, PH-1/4/8, CX-6 and CH-7 pass on actual
  sources. TASK-012 through TASK-017 are dependency-independent after their listed
  prerequisites, but share finite workers/resources; TASK-018 waits for overlays.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-012 | FL-007-A | TASK-009, TASK-010 | 3D worker implements source-dimensioned procedural equipment, inspector, catalog/generic/unlocated states and EQ-1..6; no dependency on Blender. | | |
| TASK-013 | FL-008-B | TASK-008, TASK-009, TASK-010 | Frontend worker wires canonical historical state to real events, MD placement/time controls/inspector and PH-1/4/8; retain acquisition dates and context guards. | | |
| TASK-014 | FL-009-A | TASK-009, TASK-010 | Geospatial worker implements seabed source projection, typed layer API/component and CX-1/3/4/5; owns seabed-specific files. | | |
| TASK-015 | FL-009-B | TASK-009, TASK-010 | Geospatial worker implements formation depth horizons/picks, interpolation/source masks and CX-2/3/4/5; verify combined CX-6 after both layers integrate. | | |
| TASK-016 | FL-010-A | TASK-009, TASK-010 | Frontend worker implements production endpoints/chart/units/periods/evidence with CH-1/3/4/6; owns production-specific files. | | |
| TASK-017 | FL-010-B | TASK-009, TASK-010 | Frontend worker implements depth-log endpoints/tracks/nulls/acquisition evidence with CH-2/3/4/6; owns log-specific files. | | |
| TASK-018 | FL-010-C | TASK-013, TASK-016, TASK-017 | Frontend worker integrates PH overlays/shared as-of state and CH-5/7 across both chart families; tests rapid context changes. | | |

### Implementation Phase 5

- **GOAL-005**: Verify grounded assistance and the complete application, then prepare
  authorized delivery. Target: November 1-4. Exit: all DM criteria and publication
  requirements satisfied; provider replays do not count as live checks.

| Task | Slice | Depends on | Description | Completed | Date |
|---|---|---|---|---|---|
| TASK-019 | FL-011-B | TASK-004, TASK-011, TASK-012, TASK-013, TASK-018 | RAG worker implements RG-3/4/5/7 bounded tools/assistant UI/citations/action acknowledgment using offline fixtures and the real integrated domain services. | | |
| TASK-020 | FL-011-C | TASK-005, TASK-019 | RAG worker runs the fixed 32-case live gold evaluation under approved USD 3 allowance; record RG-6 and authorized equipment-research coverage, not just successful text generation. | | |
| TASK-021 | FL-012-A | TASK-014, TASK-015, TASK-019 | QA verifies combined fresh-import browser path with stub provider, negative paths/accessibility and measured AC-9/RSS. Feature owners fix defects; Terra runs known focused commands. | | |
| TASK-022 | FL-012-B | TASK-002, TASK-020, TASK-021 | QA verifies the real-source/live-provider path and all project ACs on the candidate SHA, with isolated DB/storage and actual usage/evidence. | | |
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

At launch, assign a new branch `feature/<slice>-<slug>` and worktree
`/home/slimco/code/FieldLens-worktrees/<slice>-<slug>`. Capture
`git rev-parse master` only after approved specs are committed; current observed
base `88b177e` does not contain this uncommitted architecture package.
Do not invent future hashes or create speculative worktrees during planning.

| Resource | Lane 1 | Lane 2 | Integration/demo |
|---|---|---|---|
| API port | 8101 | 8102 | 8100 |
| Frontend port | 5174 | 5175 | 5173 |
| PostgreSQL | Shared loopback 55432 service, distinct task database | Same service, different task database | Dedicated demo/integration databases |
| Database naming | `fieldlens_<slice>_w1`, hyphens replaced by underscores | `fieldlens_<slice>_w2`, same normalization | `fieldlens_demo`, separate `fieldlens_integration` |
| DB identities | Task-scoped role; no access to another task/demo DB | Same isolation rule | Owner-provisioned integration role |
| Storage | Task-specific untracked source/output/temp roots | Separate roots; immutable approved originals may be read-only shared | Dedicated accepted manifest/artifacts |
| Heavy workload | At most one across all lanes | Wait while lane 1 uses heavy slot | Rehearsal owns the slot exclusively |

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

Dependency chain with the largest data risk:
TASK-002 -> TASK-009 -> TASK-010 -> TASK-013/016/017 -> TASK-018 ->
TASK-019 -> TASK-021/020 -> TASK-022 -> TASK-023.
Foundation TASK-001/003/006, equipment TASK-012, retrieval TASK-011, layers
TASK-014/015 and provider TASK-005 are mandatory converging branches.
This is a dependency-based priority, not measured duration/critical-path slack.

| Checkpoint | Required observation | If missed |
|---|---|---|
| Oct 28, 18:00 | G1 supports mandatory families/installed assembly; foundation runs | Stop claiming schedule feasibility; owner/provider source decision needed. Continue only genuinely independent work, not invented data |
| Oct 29 evening | Fresh real upload -> trajectory -> evidence; Meta smoke qualified | Isolate failing parser/reference/provider contract; no expansion to whole archives or alternate paid stacks |
| Oct 31 evening | Equipment/history/context/both charts integrated | Use remaining capacity for required gaps, not optional GLB polish |
| Nov 1 evening | Bounded assistant and fixed evaluation passing | Fix scoped tool/retrieval failures; no citation/grounding relaxation |
| Nov 2 evening | Combined real/live acceptance and performance run complete | Escalate exact failed ACs; do not call mock/replay success a release |
| Nov 3 | Code freeze except verified fixes; rehearse and prepare recording | Rerun affected checks for every post-freeze change |
| Nov 4, 17:00 | Owner has final package/video and verified submission checklist | Keep four-hour buffer before 21:00 EST deadline; no unauthorized publication |

These are proposed scheduling checkpoints, not owner promises or proof the scope
fits. If a mandatory source cannot be acquired, the application can retain valid
partial functionality, but the **full requested demo cannot be accepted**.

Integration is serialized: receive tested commit/handoff -> reconcile with latest
master -> run affected combined checks -> classify compatibility -> allocate one
version bump -> finalize changelog/docs -> commit/merge using authorized policy ->
verify target SHA -> reconcile backlog. No automatic push/tag/publication.
Dirty worktrees are preserved; only known clean merged worktrees are cleanup candidates.

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

- **DEP-001**: G1 approved source manifest, rights, reference/time mappings and
  independent fixtures; currently blocked on official pilot visibility/local copy.
- **DEP-002**: G2 Meta entitlement/current balance/protocol, separately gated by
  MI-6; local key existence does not establish success.
- **DEP-003**: G5 Node 24/Python 3.12/DB/package/image compatibility and optional
  OCR/embedding resource/license qualification; foundation records real versions.
- **DEP-004**: FL-001 actual host activation and committed approved specifications,
  plus owner approval for live spend, source expansions and publication.
- **DEP-005**: G4 authenticated final rules and rights-safe public-code/video review.

## 5. Files

- **FILE-001**: `backend/fieldlens/`, `backend/tests/`, `backend/migrations/` and
  root Python manifest/lock: API, persistence, ingestion, engineering and assistant.
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
- **TEST-003**: PostgreSQL integration verifies revision membership, migrations,
  fenced job recovery, budget races, source idempotency and retrieval scope.
- **TEST-004**: Frontend interactions verify shared context, cancellation/races,
  both chart families, scene/evidence alternatives and action acknowledgment.
- **TEST-005**: Playwright runs fresh-import and failure/accessibility scenarios;
  benchmark all required layers plus local reads during import, not an empty scene.
- **TEST-006**: Opt-in MI/RG live checks record actual provider/gold-case/spend
  evidence. Default suites run with outbound/provider calls prohibited.

Plan validation: unique TASK/GOAL declarations, resolvable dependencies/acyclic
DAG, unique slice IDs, valid linked specs, all project ACs traced, optional TASK-024
absent from required task ancestors, and consistent pending version metadata.

## 7. Risks & Assumptions

- **RISK-001**: Missing official completion/history/context data may prevent the
  full demo. Owner/provider resolution is not an autonomous permission change.
- **RISK-002**: Native parsing may expose unsupported profiles/OCR memory costs.
  Preserve failed evidence and narrow work; do not invent content or install every parser.
- **RISK-003**: Parallel branches can conflict on contracts/migrations or exhaust
  WSL RAM. Enforce single writers, two code lanes and one heavy slot.
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
- [Persistent backlog](../docs/BACKLOG.md)
- [Development workflow](../docs/DEVELOPMENT_WORKFLOW.md)
- [Agent roster](../.github/agents/README.md)
- [Equipment source findings](../docs/EQUIPMENT_DATA_FEASIBILITY.md)
