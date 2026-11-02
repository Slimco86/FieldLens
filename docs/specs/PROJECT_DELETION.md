# Specification: Delete an entire project with all its records and documents

> **Spec type:** Product/feature (backend + UI).
> **Load-bearing frameworks:** outcome, acceptance, failure conditions.
> **Date:** 2026-11-02. **Author:** orchestrator. **Decision owner:** project owner.
> **Status:** Approved (owner decisions 1-3 and parallel lane, 2026-11-02).
> **Backlog ID:** TASK-071 (PW-9 split out of TASK-039/TASK-049). **Delivery state:** ready.
> **Approved spec revision/date:** 2026-11-02. **Integration version:** pending (proposed 0.35.0 if merged second).
> **Zero-Question Score:** 0 unowned questions.

Implements PW-9 of [PROJECT_WORKSPACE](PROJECT_WORKSPACE.md). Per-document removal (IN-9) stays
in TASK-039/TASK-049.

## 1. Outcome Statement

After this increment the owner can delete a project from the sidebar by typing its name; the
project, every project-scoped row, every stored file of the project and its derived data are
gone, no other project is affected, and the API-spend ledger is kept so the USD cap is not
reduced. Verification: create a project with uploads, run processing, delete it; no row with
that `project_id` exists in any table, `projects/<id>/` is gone from storage, other projects
and the spend totals are unchanged. Outcome score: 3.

## 2. Scope

### IN Scope

1. `DELETE /api/v1/projects/{id}` with body `{confirm_name}` (must equal the project name,
   exact) returning 202 and a deletion status; `GET` shows `deletion_state`
   (`none|deleting|failed`) with counts of what will be removed (`GET .../deletion-preview`).
2. Migration `0015`: `project.deletion_state`, `deletion_requested_at`, `deletion_error`.
3. Phase 1 (transaction): lock the project row, set `deleting`, cancel queued/running ingest
   jobs, extraction, processing, reconstruction and indexing work; reject new uploads and
   runs for a deleting project (409 `project_deleting`).
4. Phase 2 (crash-resumable executor in the job loop): wait for active leases to drain;
   verify the storage-root identity (TASK-070 marker if merged, else the current guard);
   delete `projects/<id>/` (blobs, staging) from disk; then one DB transaction that sets
   `SET LOCAL fieldlens.purge_project_id = '<id>'`, nulls the circular pointers
   (`latest_source_revision_id`, `active_model_revision_id`) and deletes every table with a
   `project_id` in FK-safe order, then the project row. The four immutability triggers
   (`source_document`, `source_revision`, `source_revision_document`,
   `document_classification_event`) allow DELETE only when the row's project equals that
   setting; the guards stay enabled otherwise.
5. Spend ledger tables without `project_id` (budget, pricing, provider attempts,
   reservations) are kept; the spend accounting must not drop.
6. UI: ProjectSidebar action opens a typed-name dialog showing counts and the irreversible
   warning; "Deleting..." state with polling; on completion the project disappears and the
   persisted selection (`localStorage`, `features/projects/keys.ts`) is cleared; a failed
   deletion shows the error and Retry.

### OUT of Scope

Soft delete/undo, deleting one document (TASK-039), purging the spend ledger, export before
delete.

### Scope Dependencies

None open. Migration `0015` is pre-assigned (the storage-integrity lane uses `0014`).

## 3. Acceptance Criteria

| ID | Type | Given / when / then | Score | Test |
|---|---|---|---|---|
| AC-1 | Behavioral | Wrong `confirm_name` returns 422 and changes nothing; correct name returns 202 and state `deleting`. | 3 | API test |
| AC-2 | Completeness | A completeness test enumerates every table with a `project_id` column from `information_schema` and fails if one is not covered by the purge; after a delete of a fully populated project no table has a row for it. | 3 | backend test on PostgreSQL |
| AC-3 | Isolation | A second populated project, its blobs and the spend totals are unchanged after deleting the first. | 3 | backend test |
| AC-4 | Negative | Without the purge setting, DELETE on each of the four guarded tables still fails; a purge for project A cannot delete project B rows. | 3 | trigger tests |
| AC-5 | Behavioral | Work in flight is cancelled; uploads and runs for a deleting project get 409; the executor waits for leases to drain before touching storage. | 3 | integration test |
| AC-6 | Recovery | Killing the executor after the disk phase and before the DB transaction, then restarting, completes the deletion; a second run is a no-op; a missing `projects/<id>/` directory is not an error. | 3 | crash-resume test |
| AC-7 | Negative | A storage-root identity mismatch pauses the deletion in `failed` with a message and removes nothing from disk or DB. | 3 | integration test |
| AC-8 | Race | An upload that starts while deletion is requested ends either rejected or fully purged; no orphan row or blob remains. | 3 | concurrency test |
| AC-9 | UI | Typed-name dialog enables Delete only on exact match, shows counts, shows progress and error/retry states, clears the stored selection, keyboard and screen-reader accessible. | 3 | Vitest + Playwright |
| AC-10 | Regression | Existing project, upload and job tests pass; contracts have no drift. | 3 | full gates |

## 4. Context and Decisions

- Decisions (owner, 2026-11-02): cancel running work and wait; keep the spend ledger; ship UI
  in the same slice.
- Constraints: immutable-revision guards stay enabled; no raw SQL from request input; no
  cascade shortcuts that hide a missed table (the completeness test is mandatory).
- Delegation: `fieldlens-backend`, then `fieldlens-frontend`; independent `fieldlens-qa`.
  Branch `feature/task-071-project-delete`, worktree
  `/home/slimco/code/FieldLens-worktrees/task-071-project-delete`, base `master` `788973a`.
  Owned: `backend/fieldlens/projects/`, a new purge module, migration `0015`,
  `frontend/src/features/projects/`. Not owned: evidence/jobs/extraction/ingestion internals
  (lane TASK-070), VERSION/CHANGELOG/registry merges (orchestrator). If the job loop needs a
  hook, add it in a separate small module to limit conflicts.
- Resources: own `./dev` lane; tests on throwaway DBs; no Meta calls.

## 5. Failure Conditions

- Disk delete succeeds, DB transaction fails: state `failed` with error, retry completes it.
- Crash at any point: the state and the idempotent steps let the executor resume.
- Worst misinterpretation: deleting only the project row and relying on orphans, or disabling
  the immutability triggers globally. AC-2/AC-4 forbid both.

## 6. Ambiguity Audit

Resolved: scope (whole project), ledger retained, in-flight work cancelled. No owned blockers.

## 7. Implementation Guidance

Tables with `project_id` (current head `0013`): see the completeness test source of truth, not
this list. Circular FKs: `project.latest_source_revision_id`, `active_model_revision_id`;
self-FKs on `processing_run`, `reconstruction_run`, `source_revision`; `wellbore` parent.
`lock_project` already takes `FOR UPDATE` (`ingestion/repository.py`).

### Implementation handoff and integration

Filled at handoff per the [workflow](../DEVELOPMENT_WORKFLOW.md) section 5.

## Open Tensions

None.

## Assumption Registry

- Cancelling work drains within a bounded time (M): the executor retries with backoff and
  reports `failed` after the bound; invalidated if leases never release.

## Adversarial Self-Critique

A newly added table with `project_id` could be forgotten: AC-2 fails the build. Blobs shared
across projects do not exist (keys are per-project), so deleting the directory is safe.

## Revision Triggers

A new project-scoped table or shared blob store; a requirement for undo or export.
