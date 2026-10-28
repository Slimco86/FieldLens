---
goal: Deliver the first persistent browser checkpoint through three bounded implementation handoffs
version: 2
date_created: 2026-10-28
last_updated: 2026-10-28
owner: FieldLens main orchestrator
status: In Progress
tags: [feature, implementation, foundation, workspace, ingestion]
---

# Introduction

![Status: In Progress](https://img.shields.io/badge/status-In_Progress-blue)

Detailed execution packets for global TASK-003, TASK-025 and TASK-006.
The owner approved these three packets for implementation on October 28 at
11:19 EDT. The planning package is integrated in `9d630e3`; this approval is not
proof that any application acceptance check has passed.
Backend editing/discovery worked after recreating its workspace profile.
Candidate `3c1d2b2` implemented the foundation but failed independent acceptance.
The owner subsequently requested direct repairs without further subagents.
Those repairs pass direct checks, including the required CLI browser suite;
see [verification](../docs/specs/FOUNDATION.md#direct-repair-verification-october-28).
Do not start TASK-025 until the acceptance decision and foundation merge are recorded.
Owner amendment at 14:47 EDT: run each feature on its own branch in
`/home/slimco/code/FieldLens`, with subagents launched from the main session,
one writer at a time. No additional worktrees; preserve the old allocation inactive.
The [global DAG](architecture-fieldlens-1.md) remains authoritative.
Local TASK-FN/PRJ/UP identifiers below are steps inside those global tasks.

**Owner decisions confirmed October 28:** F-12/F-14/F-5 cohort, evidence-safe
generic F-12 equipment, visible discrepancies, hybrid upload categories,
explicit reconstruction/review/publication, 128 MiB/file, 512 MiB/batch and
200 files/batch. G1 engineering qualification and all live-spend gates remain open.

Reading order: orchestrator -> dispatch prerequisites and dependency table;
worker -> its packet only plus linked governing contracts; tester -> packet
exit criteria and section 6. Paths below are planned, not existing code.

## 1. Requirements & Constraints

- **REQ-001**: Browser checkpoint A creates/reopens two projects, persists a
  bounded upload and its hash/job/coverage, survives restart and rejects
  cross-project access. It does not claim parsed engineering or Meta reconstruction.
- **REQ-002**: Python 3.12/uv, FastAPI/Pydantic 2, SQLAlchemy 2/Alembic,
  PostgreSQL 17/pgvector 0.8; React 19/strict TypeScript/Vite, Node 24 tooling.
  Resolve/pin compatible patches, image digest and lockfiles in TASK-003.
- **REQ-003**: One accountable `fieldlens-backend` worker per packet, on its own
  feature branch in the shared checkout; the minimal UI is part of each slice.
  Launch from the main orchestrator session. No nested agents or concurrent writers.
  Complex UI follow-ons route to the frontend profile, not a competing scaffold.
- **SEC-001**: Loopback only; default tests deny external network/provider
  calls. No cloud, system runtime replacement, Meta call or original-data commit.
- **CON-001**: At most one code worker and one heavy workload; each assignment
  checkpoints at 90 minutes and stops after two attempts without new evidence.
- **CON-002**: Approved packet base is
  `9d630e32af898cdc9292451b5258f9c2f9a1a06d`. Later packets branch only from the
  integrated result of their own prerequisite, not this original planning tip.
- **PAT-001**: Main agent commits/integrates approved planning only when authorized,
  records the resulting full SHA, verifies the selected profile/model/effort/tools
  from host evidence, and allocates resources before dispatch. No invented hashes.

### Dispatch prerequisites and allocation

1. Owner/orchestrator review the packet against its feature spec. Record approval
   and committed spec SHA in the backlog; new contract changes return for review.
2. Complete TASK-001/DA-7. Static profile files are not proof of actual model/tools.
   If host trace/selection evidence is unavailable, request owner confirmation and
   keep dispatch blocked; do not silently substitute a worker.
3. Check checkout path/branch/base ancestry and preserve unrelated dirt.
   The new foundation branch is `feature/fl-004-a-foundation-serial` in
   `/home/slimco/code/FieldLens`; the old foundation branch/worktree stays inactive.
   Create `feature/fl-015-a-projects` and `feature/fl-005-a-upload` only after
   their predecessors are integrated. The orchestrator alone switches branches,
   after workers/checks/helpers stop. Do not create additional worktrees.
4. Allocate lane 1 API `8101`, Vite `5174`, shared DB service loopback `55432`.
   Database names respectively `fieldlens_fl004a_w1`, `fieldlens_fl015a_w1`,
   `fieldlens_fl005a_w1`; test DBs append `_test_<run_id>` where run_id is eight
   lowercase hex characters generated at launch. Separate task-scoped roles.
   No test/migration command may target `fieldlens_demo` or another assignment.
5. Storage/temp root is `<checkout>/.local/fieldlens/<slice>/`, Git-ignored.
   Only approved synthetic fixtures in the first three packets; source
   qualification is a separate task. Do not mount/import the 44.82 GiB corpus.
6. Orchestrator owns any shared Compose service and integration environment.
   Workers may start only their allocated services; record process/session IDs
   and readiness. No name-based process killing or database/container volume removal.
7. Root locks, shared DTOs, migration head, generated client and app composition
   have a single allocated writer. Provider/numeric workers may run after TASK-003
   only when their file ownership and shared edits are explicitly serialized.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Global TASK-003 / FL-004-A: a fresh checkout shows a real
  readiness-aware browser shell backed by a migrated PostgreSQL instance and
  reproducible strict contracts. It is not checkpoint A by itself.

**Read:** FOUNDATION, SHARED_CONTRACTS, relevant QualityIssue contract and the
architecture's local boundary/resource sections. Skills: relevant Python evidence
and React UI guidance; no R3F, Blender, OCR or provider setup.
**Own:** root Python manifests/lock, frontend manifests/lock/config, `infra/compose.yaml`,
`backend/fieldlens/{app.py,config.py,security.py,contracts/,persistence/}`,
`backend/migrations/`, `frontend/src/{app/,api/}`, foundation tests,
`scripts/export_contracts.py`, `.gitignore` additions and actual startup/test docs.
**Exclude:** project CRUD, uploads, jobs, parsers, retrieval and all rendering.

| Task | Description | Completed | Date |
|---|---|---|---|
| TASK-FN-01 | Verify Python 3.12, uv, Node 24 and responsive Docker/Compose. If Node 24 is absent, use only approved user/project-managed setup; no system replacement. Resolve locked dependencies and the DB image digest; record actual versions and license/native-wheel issues. | | |
| TASK-FN-02 | Implement `create_app()` in `app.py`, typed/redacted configuration, `/health` and DB/migration-aware `/ready`. Use one session factory in `persistence/session.py`; no DB work or parser work at module import. Unready DB is 503, not an empty success. | | |
| TASK-FN-03 | Implement closed DTOs in `contracts/{identity,evidence,context,quality,errors}.py`, including project/source/model separation and source/draft/model contexts. Unknown quantities stay null with reasons; forbid extra request fields and nonfinite numbers. Export all public DTOs through a documented schema registry, not fake business endpoints. | | |
| TASK-FN-04 | Create the first serialized Alembic migration for the core identity/revision/membership persistence used by contract fixtures. Enforce project-qualified foreign keys. Do not create speculative engineering/provider tables; later packet migrations add their own runtime records. Verify pgvector availability without downloading an embedding model. | | |
| TASK-FN-05 | Implement the FOUNDATION token bootstrap contract: GET `/api/v1/session`, no-store `{csrf_token}`, at least 32 random bytes/process, `X-FieldLens-Token` on mutations, Host/Origin/fetch-metadata checks and no silent mutation replay after restart. Never put the token in a URL, static bundle or log. Test permitted and rejected cases. | | |
| TASK-FN-06 | Implement `scripts/export_contracts.py` and generated strict `frontend/src/api/generated.ts` with deterministic ordering; `check:contracts` generates to a temporary file and compares without modifying the tree. Define `npm` lint/typecheck/test/build/test:e2e scripts and Python test/lint/type configuration. | | |
| TASK-FN-07 | Implement an accessible empty shell and API error component. Loading, ready and unavailable/retry states are distinct. Serve the production build through FastAPI; unknown `/api/` paths return JSON 404, never SPA HTML. Dev origins use only allocated loopback URLs. | | |
| TASK-FN-08 | Pass FN-1..6 and SC-1..6, focused browser readiness checks and all affected checks in section 6. Document actual start/stop/migrate commands, record tested SHA/environment and propose a minor bump without editing global release files. | | |

Exit requires a fresh DB upgrade/downgrade/upgrade, persisted contract fixture,
identical regenerated client, visible readiness failure/recovery and zero external
calls. Record G5 stack qualification; do not claim parser/embedding/G1/G2 success.
If the token bootstrap or migration ownership is still ambiguous at dispatch,
return that single contract gap to the orchestrator before writing it.

### Implementation Phase 2

- **GOAL-002**: Global TASK-025 / FL-015-A: keyboard users create, edit, reopen and
  switch between two empty persistent projects with no fabricated assets.
  Requires integrated TASK-003; no data/provider requirement.

**Read:** PROJECT_WORKSPACE, shared Project/context/error contracts.
**Own:** `backend/fieldlens/projects/{routes,service,repository}.py`,
project migration if needed, `frontend/src/features/projects/`,
`backend/tests/projects/`, `frontend/tests/e2e/project-lifecycle.spec.ts`.
Shared client/app composition changes are allocated to this packet serially.
**Exclude:** accounts, sharing, delete, uploads, source/model publication, scene.

| Task | Description | Completed | Date |
|---|---|---|---|
| TASK-PRJ-01 | Implement GET/POST `/api/v1/projects` and GET/PATCH `/api/v1/projects/{id}`. Use server UUIDs, trimmed name 1-120 chars, description <=4,000 chars, UTC timestamps and nullable source/model pointers. No project-level inferred CRS, well identity or current date. | | |
| TASK-PRJ-02 | Add project-qualified repository lookups and cursor pagination, default 50/max 200. Malformed input is 422; missing/out-of-context IDs are 404. Mutation failures preserve prior values and expose the standard error envelope. | | |
| TASK-PRJ-03 | Build list/create/edit/open forms with labelled controls and empty/error/retry states. Sources/Reconstruction/Explore navigation shows unmet prerequisites rather than dummy functionality. Store no geometry or large data arrays in selection state. | | |
| TASK-PRJ-04 | Centralize project/context selection and query keys. On switch, abort pending requests and reject old responses/actions. Reload reopens the selected existing project; a missing saved ID returns to the list with an explanation, not a silently selected different project. | | |
| TASK-PRJ-05 | Pass PW-1/2/5/8 for implemented surfaces, SC-2/4, migration tests if changed and a two-project restart/browser walkthrough. Record unavailable upload/reconstruction surfaces explicitly; the first slice does not pass all PW criteria. | | |

Exit demonstration: create A/B, edit A, reload/restart API, reopen both, verify
descriptions and empty states, switch during a delayed A response and see no A
content under B. Use PostgreSQL, not browser-local fixture persistence.

### Implementation Phase 3

- **GOAL-003**: Global TASK-006 / FL-005-A: checkpoint A adds immutable uploads,
  persistent job status and source membership to the real project UI.
  Requires integrated TASK-025.

**Read:** INGESTION, PROJECT_WORKSPACE, shared source/job/evidence contracts.
**Own:** `backend/fieldlens/{ingestion/upload.py,jobs/,evidence/storage.py}`,
upload/job migrations, `frontend/src/features/upload/`, source-list integration,
`backend/tests/ingestion/`, `backend/tests/jobs/`,
`frontend/tests/e2e/project-upload.spec.ts`.
**Exclude:** engineering parsing, scan/Word extraction, asset attribution, Meta,
reconstruction publication, bulk imports and arbitrary host-path upload endpoints.

| Task | Description | Completed | Date |
|---|---|---|---|
| TASK-UP-01 | Implement multipart POST `/projects/{id}/imports`: stream/hash into server-generated staging keys; enforce 134217728 file bytes, 536870912 aggregate file bytes and 200 files. Bound multipart overhead to 1048576 bytes and total request body to 537919488 bytes; validate filenames/signatures and actual streamed counts, not only Content-Length. Return typed 413/415/422 errors before any revision publication. | | |
| TASK-UP-02 | Persist document/source-revision membership, expected parent, explicit replacement target and idempotency key transactionally. Atomic file rename precedes metadata publication; failure cannot move either source/model pointer or destroy old bytes. Concurrent stale parents return 409. Same filename alone never replaces a document. | | |
| TASK-UP-03 | Implement persistent job claim/heartbeat/fencing/cancel/recovery in `jobs/{repository,worker}.py`; one heavy job, 10-minute lease, 10-second heartbeat, at most one classified transient retry. Unknown profiles are retained with explicit unsupported/pending-extraction status, not claimed parsed. No parsing in FastAPI BackgroundTasks. | | |
| TASK-UP-04 | Implement project-scoped document/job reads and cancel endpoint, category/tag metadata and audited overrides. Permit uncategorized files; labels are not identities. The storage stage counts inspected bytes/files only, never pages/entities it has not parsed. | | |
| TASK-UP-05 | Build upload progress, source list, original-file metadata, category editing and persistent job/coverage/error/retry UI. A new/failed source revision never relabels the active model. Follow evidence links only through scoped server IDs, not paths supplied by the browser. | | |
| TASK-UP-06 | Pass IN-1/3/4/5/7 and PW-3/4/6/7 for this storage/job slice, exact limits and limit+1, duplicate/replacement/race tests, restart/fenced stale-worker/cancel tests and checkpoint A. Defer parser-specific portions of IN-3/7 explicitly to TASK-009/030/029; never report full ingestion acceptance. | | |

Safe storage first: accept registered upload media including selected PDF/legacy
Word originals without executing them; before a reader exists, show extraction
pending/unsupported. A storage job may succeed only with a result explicitly
named storage verification, not engineering extraction success. Source revision
coverage remains partial/unknown. ZIP expansion and PDF-page inspection are
parser-stage responsibilities before extraction can succeed.

Exit demonstration: upload a labelled synthetic permitted file into A, verify
stored SHA/bytes/category/job after restart, upload again without duplicates,
reject access through B, attempt oversized input, cancel a job and verify old
results remain. No manufactured wells or model publication.

### Worker return and integration

Return: owned paths/commit(s), tested SHA, exact commands and pass/fail/skipped
results, browser steps, DB/storage/port/process ownership, migrations/contracts,
known limitations, actual exposed model/usage metadata, proposed minor bump and
release note. Workers do not edit VERSION/CHANGELOG/BACKLOG or merge/push.
Orchestrator rechecks affected combined behavior against the latest target,
allocates one version, integrates only with authorization and updates the ledger.
Keep pending changes and inactive worktrees; stop only helpers owned by the assignment.

## 3. Alternatives

- **ALT-001**: Three concurrent scaffolding workers rejected; they would compete
  for manifests, contracts, migrations and app composition.
- **ALT-002**: Browser-only mock projects rejected; they cannot verify restart,
  project isolation or the real upload workflow.
- **ALT-003**: Waiting for every F-12 measurement rejected; these packets use
  synthetic fixtures and make no engineering-data claims.
- **ALT-004**: A universal parser in the upload packet rejected; storage/jobs and
  qualified native/scan profiles have different evidence and resource checks.

## 4. Dependencies

| Global task | Requires | Other eligible work (queued, not concurrent) |
|---|---|---|
| TASK-003 | TASK-001, approved committed packet | TASK-002 source qualification remains separate; no parallel worker |
| TASK-025 | TASK-003 integrated | TASK-004 offline Meta adapter or TASK-007/008 numeric engine may be scheduled as a later feature |
| TASK-006 | TASK-025 integrated | Provider/numeric work stays queued; no second code lane |
| TASK-009 / TASK-032 | TASK-006 / TASK-009 respectively | Next UI checkpoint: evidence and quality issues; use their feature contracts |

No full G1 or live G2 is a prerequisite for the three synthetic first packets.
No paid allowance is allocated here. G5 runtime qualification is an output of
TASK-003, not a falsely completed prerequisite.

## 5. Files

- **FILE-001**: Foundation paths above now exist. Project/upload packet paths
  remain planned; this foundation does not implement those business features.
- **FILE-002**: `tests/fixtures/synthetic/` contains clearly labelled generated test
  files only; original Volve data and runtime outputs remain ignored.
- **FILE-003**: Feature specs receive actual verification/handoff records from
  their worker; global backlog/version/changelog remain orchestrator-owned.
- **FILE-004**: Later native/scan packets produce source profiles from approved
  hashes/locators, not hardcoded audit results keyed to a filename or exact hash.

## 6. Testing

Foundation implements these commands. Direct repair checks pass; see
[README](../README.md#tests) for Node, test-database and browser-helper setup,
and the foundation spec for acceptance status:

```text
uv sync --frozen
uv run pytest backend/tests/contracts backend/tests/foundation
uv run ruff check backend scripts
uv run mypy backend/fieldlens
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test -- --run
npm --prefix frontend run check:contracts
npm --prefix frontend run build
npm --prefix frontend run test:e2e -- tests/e2e/readiness.spec.ts
```

- **TEST-001**: TASK-025 uses focused `backend/tests/projects` and
  `tests/e2e/project-lifecycle.spec.ts`; TASK-006 uses
  `backend/tests/ingestion backend/tests/jobs` and `tests/e2e/project-upload.spec.ts`.
  Run affected type/lint/build and generated-contract checks in both.
- **TEST-002**: Missing/unsafe test DB URL fails before migrations; allowlisted
  loopback PostgreSQL and browser requests only. No external provider/model calls.
- **TEST-003**: Streaming boundary tests generate data on demand, not committed
  512 MiB blobs or in-memory whole-file allocations. Test exact and +1 boundaries.
- **TEST-004**: Browser tests use one worker, allocated URLs and dedicated
  test storage/database. Record stub/real backend distinctions explicitly.
- **TEST-005**: One-byte or hash mismatches, stale parents, DB failure and
  late worker publication attempts are failures, not zero-content successes.

## 7. Risks & Assumptions

- **RISK-001**: Actual profile/model/effort cannot be observed. Stop dispatch and
  obtain host/owner evidence; do not infer it from the agent's own description.
- **RISK-002**: Package/native/image compatibility fails. Resolve patches within
  agreed families; return major stack/resource changes to the orchestrator.
- **RISK-003**: A worker needs another packet's shared files. Stop that edit and
  request single-writer allocation; do not implement a competing schema/client.
- **RISK-004**: An endpoint or security/bootstrap contract remains ambiguous.
  Return the specific gap before implementation; this plan cannot authorize guesses.
- **ASSUMPTION-001**: Docker and user-managed Node 24 can run locally; verify in
  TASK-003, not by an unrequested system installation now.
- **ASSUMPTION-002**: Small UI slices fit the backend worker's tools/skills; if not,
  orchestrator assigns a single revised vertical slice rather than nested delegation.
- **ASSUMPTION-003**: A 90-minute bound is a checkpoint, not a promise that a packet
  finishes; incomplete required tests prevent a passing handoff.

## 8. Related Specifications / Further Reading

- [Global execution DAG](architecture-fieldlens-1.md)
- [Foundation](../docs/specs/FOUNDATION.md)
- [Shared contracts](../docs/specs/SHARED_CONTRACTS.md)
- [Project workspace](../docs/specs/PROJECT_WORKSPACE.md)
- [Ingestion](../docs/specs/INGESTION.md)
- [Data quality](../docs/specs/DATA_QUALITY.md)
- [Development workflow](../docs/DEVELOPMENT_WORKFLOW.md)
- [Agent roster](../.github/agents/README.md)
