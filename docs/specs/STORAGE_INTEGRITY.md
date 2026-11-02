# Specification: A stored file is either Stored or Failed, and every failure is recoverable

> **Spec type:** Product/feature (backend + UI + dev tooling).
> **Load-bearing frameworks:** outcome, acceptance, failure conditions.
> **Supporting:** ambiguity audit.
> **Date:** 2026-11-02. **Author:** orchestrator. **Decision owner:** project owner.
> **Status:** Approved (owner: decisions 1-3 and "that sounds reasonable", 2026-11-02; quarantine removal accepted).
> **Backlog ID:** TASK-070 (amended). **Delivery state:** ready.
> **Approved spec revision/date:** 2026-11-02. **Integration version:** pending (proposed 0.34.0).
> **Zero-Question Score:** 0 unowned questions.

Extends [INGESTION](INGESTION.md) IN-5 (storage verification) and the TASK-066 guard
(0.33.0). Supersedes the "quarantined" file state as a user-visible concept.

## How to Read This Spec

Owner: sections 1-2. Implementer: sections 2-4 and 7. Tester: section 3 and 5.

## Notation Key

As in the [feature template](FEATURE_TEMPLATE.md).

## 1. Outcome Statement

After this increment the user sees only two storage outcomes for an uploaded file:
**Stored**, or **Failed: stored copy missing or damaged**, and a failed file can always be
recovered from the UI (Retry when the bytes are present and verify, otherwise Re-upload of
the same file, which repairs it instead of reporting "already present"). A background
process with the wrong storage root can no longer mark a file failed.
Verification: the reproduction from the 2026-11-02 incident (a stale server with another
storage root verifying real uploads) leaves every file Stored, and files already marked
`quarantined` heal on upgrade. Outcome score: 3.

## 2. Scope

### IN Scope

1. **Root identity marker (TASK-070).** One persisted identity for the storage root: a
   DB row (`storage_root_identity`, single row, migration `0014`) and
   `<root>/.fieldlens-root-id`. Every blob-reading worker (verification job worker,
   extraction runner, indexing/processing workers, reverify route) compares the marker
   before claiming work or writing any failure. Missing marker file plus no blobs plus no
   DB row creates both (fresh install); a mismatch refuses the work, logs once per minute
   and reports `storage_root_mismatch` in readiness. An explicit
   `uv run python scripts/storage_root.py adopt` re-binds an intentionally wiped or
   moved root (typed confirmation); `./dev reset-data` re-initialises both. This replaces
   the heuristic sample of 8 stored originals in `evidence/root_guard.py`.
2. **Failure semantics.** A document is written Failed only when the root identity passed
   and the blob is genuinely missing or its size/SHA-256 differs; the reason code
   (`missing`, `size_mismatch`, `hash_mismatch`) and the writing process's identity are
   stored. The API and UI vocabulary is `stored | failed`; the word "quarantined" no
   longer appears in DTOs, UI or messages. The persisted value may stay `quarantined`
   internally only if renaming needs a risky constraint change; the implementer states
   the choice in the handoff.
3. **Recovery.**
   - Re-upload of a file whose latest-revision copy is Failed or whose blob is missing
     repairs it: the uploaded bytes (hash-verified) are published to the blob store, the
     document returns to Stored and extraction is enqueued. Fully intact duplicates stay
     "deduplicated" with no job.
   - Retry action on a Failed document: re-verify the bytes; on success Stored and
     extraction is enqueued; otherwise the message says to re-upload this file.
   - Startup/bootstrap heal pass (bounded, logged): re-verifies Failed documents of this
     root and restores those whose bytes verify; enqueues extraction for stored documents
     that have no run.
4. **Extraction attribution.** A `source_missing` run failure records the failing
   process identity (host, pid, lane/root id); DB connections set `application_name`
   (`fieldlens:<lane>:<pid>`).
5. **UI.** Sources list and Evidence panel: Stored / Failed states, the Retry and
   Re-upload actions, no "waiting for worker" dead end for a Failed or run-less document
   (it shows a state and an action). Message for Failed: "Failed: stored copy missing or
   damaged."
6. **Dev tool.** `./dev status` and `./dev restart` list other FieldLens API processes on
   this host (own lane and others) that hold connections to the configured database and
   warn that they are not managed by this lane; they never kill them.

### OUT of Scope

Cloud storage, multi-user locking, renaming the DB value if risky, any change to
extraction/classification behavior (TASK-055), project deletion (TASK-071, separate lane).

### Scope Dependencies

TASK-066 (done, 0.33.0). None open. Migration number `0014` is pre-assigned to this lane;
the project-delete lane uses `0015`.

### Open Scope Tensions

None.

## 3. Acceptance Criteria

| ID | Type | Given / when / then | Score | Test |
|---|---|---|---|---|
| AC-1 | Behavioral | Given a root with marker M, a verifier running with a root whose marker differs (or missing while the DB row exists) claims no job and writes no failure; readiness reports `storage_root_mismatch`. | 3 | backend integration, two temp roots |
| AC-2 | Behavioral | Fresh DB and empty root: first start creates the DB row and marker; a second start with the same root passes; no stored original is required for the guard to work. | 3 | backend test |
| AC-3 | Negative | A genuinely deleted blob under the right root: the document becomes Failed with reason `missing`; an intact blob never becomes Failed. | 3 | backend test |
| AC-4 | Behavioral | Re-upload of the same bytes for a Failed document with a missing blob restores the blob, sets Stored, enqueues extraction and returns a non-"deduplicated" outcome; an intact duplicate still returns deduplicated with no job. | 3 | backend + API test |
| AC-5 | Behavioral | Retry on a Failed document whose bytes verify sets Stored and enqueues extraction; with bytes missing it returns a clear re-upload message and changes nothing. | 3 | API test |
| AC-6 | Behavioral | Heal pass on a DB copy containing the two incident documents (state `quarantined`, blobs present, hashes match) restores both to Stored and enqueues one extraction each; idempotent on a second run. | 3 | backend test with fixture blobs |
| AC-7 | Behavioral | A `source_missing` run failure row records the process identity; every DB connection of the app has an `application_name` starting `fieldlens:`. | 3 | backend test |
| AC-8 | UI | No UI string or DTO field contains "quarantine"; Failed shows the stated message with Retry/Re-upload; a run-less Stored document shows its state plus a start action or a precise reason, never only "waiting for worker". | 3 | Vitest + Playwright |
| AC-9 | Behavioral | `./dev status` lists a second FieldLens API process attached to the same DB with a warning and does not signal it. | 3 | tool test with a fake process table |
| AC-10 | Regression | Existing storage, ingestion, extraction and upload tests pass; the contracts check shows no drift. | 3 | full gates |

Definition of done: all ACs pass with recorded commands; independent QA by another agent
including a real browser run on the lane; version/changelog finalised by the orchestrator.

## 4. Context and Decisions

- Root cause of the incident: a stale `task-048` worktree server (pid 257492) running
  pre-guard code on port 8161 verified real uploads against a different storage root and
  wrote `quarantined`. The 0.33.0 guard only protects processes running the new code.
- Quarantine was designed so a partially verified revision could still publish (IN-5);
  uploads already hash bytes while streaming, so in practice every case was a false
  positive. The user-visible concept is removed; revision publication keeps using the
  stored verdict internally.
- Delegation: `fieldlens-backend` (backend, migration, dev tool), then `fieldlens-frontend`
  (UI part, same lane after the backend contract lands); independent `fieldlens-qa`.
  Branch `feature/task-070-storage-integrity`, worktree
  `/home/slimco/code/FieldLens-worktrees/task-070-storage-integrity`, base `master`
  `788973a`. Owned: `backend/fieldlens/evidence/`, `backend/fieldlens/jobs/`,
  `backend/fieldlens/extraction/`, `backend/fieldlens/ingestion/`, `backend/fieldlens/db*`
  connection setup, `scripts/dev.py`, new `scripts/storage_root.py`, migration `0014`,
  `frontend/src/features/uploads/`. Not owned: projects routes/UI (lane TASK-071),
  VERSION/CHANGELOG/registry merges (orchestrator).
- Contracts: DTO changes go through `contracts/registry.py` and
  `npm --prefix frontend run generate:contracts`; the orchestrator resolves registry/client
  conflicts at merge.
- Resources: own `./dev` lane (database, ports, storage root), tests on throwaway DBs, no
  Meta calls (default tests spend nothing).

## 5. Failure Conditions

- Assumption: the root marker is trustworthy. Deviation: the marker file is deleted while
  blobs remain. Action: refuse work, report `storage_root_mismatch`, offer `adopt`; never
  fail documents.
- Assumption: a missing blob under the right root is real. Deviation: restore/re-upload.
  Action: Failed with reason plus Re-upload; the document is never silently re-created.
- Re-verify or heal crashes midway: idempotent, state only changes after a hash-verified
  blob exists.
- Worst misinterpretation: hiding the word "quarantined" while the same dead end remains.
  AC-4/5/6/8 require an actual recovery path and a state change.

## 6. Ambiguity Audit

Resolved: removal of "quarantine" from UI and API (owner accepted); DB value rename
optional (implementer documents). `adopt` requires typed confirmation. No owned blockers.

## 7. Implementation Guidance

Start at `evidence/root_guard.py` (replace), `jobs/worker.py` (`_verify_all`),
`extraction/runner.py` (`_mark_unreadable`, `requeue_document`, `enqueue_missing`),
`extraction/routes.py` (`_reverify_original`), `ingestion/repository.py`
(`publish_import` dedupe branch), `EvidencePanel.tsx` and `DocumentList.tsx`.

### Implementation handoff and integration

Filled at handoff per the [workflow](../DEVELOPMENT_WORKFLOW.md) section 5.

## Open Tensions

None.

## Assumption Registry

- Uploads hash bytes while streaming (H, verified in code 2026-11-02): genuine mismatch is
  near-impossible; invalidated if a mismatch appears with the right root.

## Adversarial Self-Critique

The marker could itself go stale after a manual copy of `.local`; the `adopt` path and the
readiness message cover that. Warning signal: documents Failed while readiness is OK.

## Revision Triggers

Storage moved to a different backend; a genuine hash mismatch observed with a verified root.
