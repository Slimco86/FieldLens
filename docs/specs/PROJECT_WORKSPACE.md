# Specification: Project-owned sources and incremental uploads

> **Spec type:** Product/feature. **Backlog:** FL-015.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-28. **Author:** main orchestrator. **Decision owner:** project owner.
> **Status:** First lifecycle and upload packets approved October 28 at 11:19 EDT.
> **Delivery state:** TASK-025 done, independently accepted and integrated as 0.5.0. Upload-dependent criteria remain pending.
> **Approved revision / integration:** packet `9d630e3`; project lifecycle integrated at `3e748d9` after foundation 0.4.0 at `1293f55`.
> **Zero-Question Score:** 0 unowned questions for the approved lifecycle slice.

## How to Read This Spec

Owner: outcome, categories and assumptions. Backend/frontend: section 4 and PW
criteria. QA: failure and isolation scenarios. Covers project AC-2/8/10/11.

## Notation Key

`[Validated]` means owner-required, not implemented. `[Assumed: verify]` marks a
proposed detail for review before handoff. Owner-confirmed workflow choices below
supersede their earlier draft status. H/M/L mean high/medium/low
confidence, not statistical probability. AC score 3 means binary-testable.

## 1. Outcome Statement

A user can create and reopen a project, incrementally upload and categorize its
related source files, and inspect persistent processing states without another
project's sources or results appearing.
Verification: PW-1 through PW-8 in a fresh PostgreSQL/browser run. Outcome score 3.

## 2. Scope

### IN Scope

- Project list/create/open, name/description editing and project-scoped navigation.
  `[Validated: owner point 2; editing details assumed]`
- File batches, multi-category labels, optional custom tags, processing coverage
  and original-source navigation. Upload/jobs/readers remain FL-005's implementation.
  `[Validated: owner confirmed hybrid classification, October 28]`
- Source revisions separate from published asset-model revisions; a new upload
  does not silently replace the currently inspected reconstruction. `[Validated: confirmed review workflow]`

### OUT of Scope

Hosted accounts/sharing, cross-project asset merging, arbitrary host-directory
imports, project deletion/archiving and bulk-release import are excluded from this
increment. File removal was approved by the owner on October 30 (bytes are physically
deleted and a tombstone revision is kept; see INGESTION IN-9 and TASK-039); replacement is a new
revision (IN-5). No removal control is shown before TASK-039 lands.
Reconstruction/review belongs to FL-016; 3D belongs to FL-006/007.
Categories are not a physical folder schema or proof of the entities inside a file.

### Scope Dependencies

FL-004 supplies project/source/model contracts and the shell. PW-1/2/5/8 can be
verified before upload integration; PW-3/4/6/7 additionally consume FL-005-A.
FL-005-A depends on the workspace slice, not on completion of all FL-015 criteria.

### Open Scope Tensions

Owner wants organization without knowing all entities in advance. Approved
resolution: accept uncategorized files; suggest categories, then discover actual
entities from content. Labels never establish engineering facts.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| PW-1 | Behavioral | Create two named projects, reload/restart the API, and reopen each with its saved description and correct source/model status. Empty projects display an upload action, not fabricated assets. | 3 | [Validated] | `project-lifecycle.spec.ts` |
| PW-2 | Negative | Using project B's document/job/run/conversation/entity ID under project A returns 404; list, retrieval, graph, evidence and artifact paths expose zero B records. Same blob hash does not bypass membership. | 3 | [Validated] | `test_project_isolation` |
| PW-3 | Behavioral | Add a second batch to a project; its new source revision retains unchanged first-batch members. Repeating bytes/idempotency key creates no duplicate document or processing job. Explicit replacement retains the previous bytes/revision. | 3 | [Validated] | `test_incremental_sources` |
| PW-4 | Behavioral | One report can have completion/equipment and perforation/history categories plus a custom tag; suggested labels and user overrides retain distinct origins. A file with no category can be uploaded. | 3 | [Validated: owner October 28] | `upload-categories.spec.ts` |
| PW-5 | Negative | A tag, folder or filename cannot establish well identity, installed state, effective date, CRS or a numeric claim. A mislabeled F-12/F-11 fixture is flagged by content, not forcibly reassigned to the folder label. | 3 | [Validated] | `test_category_is_not_evidence` |
| PW-6 | Edge case | During failed/cancelled/new imports, the published model remains pinned and labeled with its source revision; the UI explicitly shows that newer sources are pending or failed. | 3 | [Assumed: verify]; owner moved verification to TASK-026 (FL-016-A) on 2026-10-30 because it needs a published model; FL-015 was closed without it | `source-model-revisions.spec.ts` |
| PW-7 | Non-behavioral | Streaming enforces 128 MiB/file, 512 MiB/batch and 200 files/batch, testing exact limit and limit+1 byte; filename/media validation precedes parsing. Oversize failure is visible and publishes no source revision. | 3 | [Validated: owner October 28; performance unmeasured] | `test_project_upload_bounds` |
| PW-8 | Behavioral | Keyboard-only navigation creates/opens a project and switches Sources/Reconstruction/Explore; unavailable capabilities state their prerequisite. Project switching invalidates pending requests and action acknowledgments. | 3 | [Assumed: verify] | `project-navigation.spec.ts` |
| PW-9 | Behavioral | Owner request October 31 (leftover projects had to be removed by hand). Deleting a project after typing its exact name, via an explicit API (`DELETE /api/v1/projects/{id}` with a confirmation body), cancels its running jobs, physically deletes every stored blob no other project references, removes every project-scoped row (documents, revisions, jobs, runs, records, series, identities, chunks, activity, ledger links) in one transaction, and leaves other projects untouched; the immutable-revision guards stay enabled for every other path (the deletion uses a designed, tested project-delete path, never a manual trigger disable); an unknown project is 404, a wrong confirmation 422, a project with a running published-model dependency states it; the deleted project never reappears in lists, search, series or identities. | 3 | [Validated: owner request] | `test_project_delete` (real PostgreSQL and storage), `test_project_delete_isolation` |

Eight criteria, all score 3. Full feature acceptance requires both workspace and
upload integration; a project form alone is not PW-3/6/7 verification.

## 4. Context and Decisions

Executor: backend owner for project persistence/API and the small initial UI;
frontend owner extends linked panels later. Main agent allocates exact base,
worktree, database, ports and single-writer contracts before delegation.
Owner approves scope/defaults. The TASK-025 allocation below owns the lifecycle slice.

**Project** is a user workspace for related assets, potentially spanning multiple
fields; it is not itself a field. **Source revision** is an immutable membership/
processing snapshot. **Model revision** is a reconstruction pinned to one source
revision. **Upload batch** is a transaction boundary, not a dataset/product entity.
There is one logical corpus per project in v1, not a separate dataset-management UI.

Project fields: server UUID, name (1-120 trimmed characters), optional description
(<=4,000 characters), created/updated timestamps, nullable latest source revision
and active model revision. These limits are `[Assumed: verify, H]`.
No CRS/date is forced at project creation; source references and analysis choices
are recorded later, never defaulted from project name or a Volve preset.

Category keys for the confirmed hybrid policy `[Assumed: verify, H; exact labels at packet review]`:

| Key | Display meaning |
|---|---|
| `trajectory` | Surveys and well-path references |
| `completion_equipment` | Completion, casing/tubing and installed equipment |
| `perforation_history` | Perforation and operational/state events |
| `production_injection` | Production and injection series |
| `well_logs` | Depth-indexed measurements/interpretations |
| `geology_reservoir` | Formation picks and interpreted reservoir context |
| `terrain_bathymetry` | Surface/seabed data |
| `general_report` | Mixed narrative or otherwise unclassified engineering report |

Store zero or more categories separately from detected format/media type, user
tags (<=20, <=64 characters each), suggested categories, classification method/
version and user override history. Local signature/header suggestions need no
paid model. Unknown/contradictory classification is visible; do not require a
paid classification call to accept a file. User tags do not extend parser enums.

Every file has immutable bytes/hash, project membership, import origin, original
name, category metadata and extraction coverage. Documents may describe several
assets. Asset links come from reconstruction with per-record/page evidence, not
from assigning one `well_id` to an entire document.

Explicit replacement identifies the old document ID; equal filename is not a
replacement request. Concurrent batches pin an expected parent source revision:
a stale parent returns 409 and requires refresh/retry, not silent last-writer-wins.
Metadata edits are audited; parser/profile changes create new extraction results
and a new source revision. Prior model evidence remains reproducible.

The approved 128 MiB limit admits the inspected 54,466,467-byte F-14 PDF; the old
25 MiB proposal did not. The 211,263,929-byte EDM export still requires a separately
approved streaming profile/limit. Batch size is not a cumulative project-storage
cap; disk-space failures remain explicit. Do not copy all 44.82 GiB into a project.

## 5. Failure Conditions

- Cross-project record appears in any response -> stop acceptance and repair
  repository/context checks; UI filtering alone is insufficient.
- Required selected source exceeds approved bounds -> return 413 and seek a
  source-specific limit/profile amendment; do not split original bytes deceptively.
- Automatic classification disagrees with content -> retain both annotations,
  flag conflict and use qualified content parsing; never manufacture asset links.

Worst misinterpretation: persistent projects with globally shared conversations
or source search fail PW-2 even if the project dropdown appears correct.

## 6. Ambiguity Audit

Project scope and incremental upload are owner requirements. The owner explicitly
confirmed hybrid labels, review/publication and 128/512 MiB / 200-file limits on
October 28. This supersedes the earlier unanswered form. Detailed packet review,
committed contracts and runtime readiness still precede dispatch.

## 7. Implementation Guidance

Planned ownership: `backend/fieldlens/projects/`, project repositories/migration,
`frontend/src/features/projects/`, project navigation and focused tests.
FL-005 owns upload/storage/jobs. Shared schemas/client have one writer.
Use real API/database persistence from the first browser checkpoint.
The first implementation packets (archived in git history)
specify the lifecycle and subsequent upload handoffs, including partial PW coverage.

Independent QA accepted `2af22aa7c91f36fc33a5ee015ae64ea2d0e3c8a0` after D1 repair.
Final combined checks passed; integration into `master` is confirmed at
`3e748d9e939a007fb62c36f211680b41d33d1fd1`, version 0.5.0. The minor bump adds
project API/UI and migration `0002_project_lifecycle` without changing the
foundation's public description limit or rewriting valid data.

#### TASK-025 scoped implementation and acceptance

API: `GET/POST /api/v1/projects`, `GET/PATCH /api/v1/projects/{project_id}`. DTOs
`ProjectCreate`, `ProjectUpdate`, `ProjectPage` reuse the foundation `Project` and
`PageInfo`. List is newest first with an opaque `(created_at, project_id)` keyset cursor.
Migration `0002_project_lifecycle` adds `char_length(description) <= 4000` and a
newest-first index; no data is rewritten.

| Criterion | Implemented-surface evidence | Not covered |
|---|---|---|
| PW-1 | `project-lifecycle.spec.ts` (real API/PostgreSQL, true API restart): two projects, edit, reload, restart, reopen, descriptions, null revision pointers | The empty-project **upload action** is deliberately absent (no fake controls); it arrives with FL-005 |
| PW-2 / SC-2 | `test_project_isolation`: project-qualified lookups, editing B leaves A, cross-project revision pointer refused by composite FK | Nested document/job/run/conversation/entity/graph routes do not exist yet |
| PW-5 | `test_category_is_not_evidence`: name/description are opaque; no well/CRS/date fields | Content-vs-label upload mislabel (F-12/F-11) needs uploads |
| PW-8 | `project-navigation.spec.ts` keyboard-only flow; delayed-A open and delayed-A save switched to B show no A content/ack; saved-ID reload and missing-ID explanation | |
| SC-4 | Request keys include project ID; abort on switch; obsolete responses and acknowledgements rejected (unit + browser) | Context-kind/revision/as-of keys beyond project are later features |
| PW-3/4/6/7 | Not run: require upload/storage/jobs | all |
| QA D1 repair | `ProjectCreate`/`ProjectUpdate` reject NUL and unpaired surrogates at the DTO boundary with typed 422 errors. Parameterized real-DB regressions cover no writes, unchanged timestamps, token ordering and valid Unicode. Independent QA reproduced 20 invalid raw-JSON cases on `2af22aa`, all 422 with no stored-row change | None for this defect |

Interaction unit tests (`tests/projects.test.tsx`) use a stubbed `fetch` and are not
persistence evidence.
Independent re-verification: 69 focused project tests and 193 full backend tests,
15 Vitest tests, frontend build and 9 Playwright tests passed. API restart and
persistence use a real FastAPI process and PostgreSQL; unit UI fetches are stubs.
An additional real-DB upgrade/downgrade/re-upgrade probe preserved an existing
project row and removed/recreated the keyset index. Initial QA also exercised
delayed failures/save acknowledgements, 53-project pagination, blocked browser
storage and forged tokens. No provider/live-engineering acceptance is implied.

Final release-tree checks were delegated to `fieldlens-task` (host-resolved
`gpt-6.1-terra`, explicit low effort): 193 backend, 15 Vitest and 9 E2E tests,
Ruff lint/format, scoped mypy, frontend lint/typecheck/contracts/build and
whitespace checks passed. Installed metadata is 0.5.0 after
`uv sync --frozen --reinstall-package fieldlens`; plain frozen sync had retained
the cached 0.4.0 metadata, so README now documents the explicit refresh.

### TASK-025 execution allocation, October 28

- Approved outcome: packet TASK-PRJ-01..05, PW-1/2/5/8 for implemented surfaces
  and SC-2/4. Create/edit/list/open two persistent empty projects, keyboard
  navigation, restart/reload recovery and stale-response/action isolation.
  Upload-dependent PW criteria, accounts, sharing, deletion, reconstruction and
  engineering data qualification are outside this assignment.
- Sole implementer: `fieldlens-backend`; interconnected API, persistence and small
  UI changes require the domain specialist, with `fieldlens-react-ui` guidance.
  A different `fieldlens-qa` invocation owns subsequent acceptance.
- Base: `b4a02b2f8c4ec5fd71d97aea240514e6d5fd2260`, target `master`, branch
  `feature/fl-015-a-projects`, checkout `/home/slimco/code/FieldLens`.
  Preserve the pre-existing dirty `.github/copilot-instructions.md` and inactive
  foundation worktree; neither belongs to the feature commit.
- Activation: session host events resolve the backend to `claude-sonnet-5.5`.
  Native `create`, `edit` and `view` completed the disposable editing smoke.
  CLI 1.0.65 warns that profile `reasoning-effort` is ignored, so the supported
  task invocation explicitly selects `medium`; provider-internal effort telemetry
  is not exposed. The owner explicitly accepts main `gpt-6-astra/high` for this
  continuation instead of requiring xhigh. No global model policy is changed.
- Owned paths: `backend/fieldlens/projects/`, project DTOs/registry and generated
  client, project persistence/migration if needed, app/API composition,
  `frontend/src/features/projects/`, focused backend/UI/browser tests,
  necessary E2E runner support, this spec and related README run instructions.
  Shared contracts/app composition are allocated serially to this worker.
  No worker edits to global VERSION, CHANGELOG, BACKLOG or agent configuration.
- Resources (**historical allocation, superseded by FL-018**: current local resources are
  Compose project `fieldlens`, container `fieldlens-postgres`, volume `fieldlens_pgdata`,
  role `fieldlens`, database `fieldlens_app`, tests `fieldlens_app_test_<8 hex>`, settings in the
  root `.env`; see [DEV_ENVIRONMENT](DEV_ENVIRONMENT.md)): task-specific Compose project `fieldlens-fl015a`, container
  `fieldlens-fl015a-postgres`, volume
  `fieldlens-fl015a_fieldlens_fl004a_pgdata`, role `fieldlens_fl015a`,
  database `fieldlens_fl015a_w1`, loopback port 55432. The foundation container
  is stopped with its volume preserved. Credentials and Compose override stay
  ignored under `.local/fieldlens/fl-015-a-projects/`; never print credentials.
  Tests use `fieldlens_fl015a_w1_test_<8-lowercase-hex>` and fresh sibling DBs.
  API 8101 and Vite 5174 are reserved; browser helper Compose project
  `fieldlens-fl015a-browser` is healthy on loopback 9323.
- Python 3.12.13/uv 0.11.20; use the existing project-local Node 24.22.2 runtime
  described in README, not the ambient Node 20. Shared host has 3.9 GiB available
  RAM and 161 GiB disk at allocation. One writer/heavy workload; no nested agents.
- Baseline and affected checks: `uv run pytest backend/tests`,
  `uv run ruff check backend scripts`, `uv run ruff format --check backend scripts`,
  `uv run mypy backend/fieldlens scripts`; frontend `lint`, `typecheck`, `test`,
  `check:contracts`, `build` scripts run separately. Focused additions use
  `uv run pytest backend/tests/projects` and
  `npm --prefix frontend run test:e2e -- tests/e2e/project-lifecycle.spec.ts`;
  retain readiness regression coverage and verify real API restart persistence.
  Run the frozen-candidate acceptance independently before integration.
- Budget: synthetic fixtures only, zero Meta/provider calls, no original corpus,
  no new paid services or system runtime changes. Checkpoint at 90 minutes; stop
  after two attempts without new evidence. Escalate contract gaps, tool/model
  mismatch, unsafe resource use or failing prerequisite checks; do not weaken ACs.
- Handoff: exact tested SHA, commands/results, scoped criteria and unrun portions,
  resources/PIDs, migration impact, exposed development usage (otherwise
  unavailable), proposed minor release note. Coding alone is not acceptance.

## Open Tensions

The former deferral of manual adjudication does not prevent a small revision
review screen. Detailed fact editing/merge/split tooling remains excluded; FL-016
must expose conflicts without pretending that Publish resolves them.

## Assumption Registry

| Assumption | Confidence | Validation / invalidation |
|---|---|---|
| Hybrid labels reduce upload burden | H | Policy approved October 28; actual usability checked in the upload walkthrough |
| One project corpus is sufficient | H | Reopen if independent named datasets within a project are requested |
| 128/512 MiB streaming limits fit selected samples and disk/RSS budgets | M | Verify exact byte-boundary tests and import/RSS measurement before acceptance |

## Adversarial Self-Critique

- A tidy file list can hide failed extraction: show per-file coverage and errors.
- Byte deduplication can leak another project's evidence: test membership, not hashes.
- A new import can silently relabel old results: display both source/model revisions.

## Revision Triggers

Reopen if owner requests sharing/deletion, a mandatory source exceeds the
approved upload profile, or classification is needed as an engineering assertion.
