# Specification: Project-owned sources and incremental uploads

> **Spec type:** Product/feature. **Backlog:** FL-015.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-28. **Author:** main orchestrator. **Decision owner:** project owner.
> **Status:** Hybrid categories, explicit review/publication and upload limits approved October 28; detailed packet review precedes dispatch.
> **Delivery state:** specifying. **Approved revision / integration:** none.
> **Zero-Question Score:** 0 unowned questions; committed packet and runtime prerequisites still gate dispatch.

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
imports, file/project deletion and bulk-release import are excluded from this
increment. Reconstruction/review belongs to FL-016; 3D belongs to FL-006/007.
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
| PW-6 | Edge case | During failed/cancelled/new imports, the published model remains pinned and labeled with its source revision; the UI explicitly shows that newer sources are pending or failed. | 3 | [Assumed: verify] | `source-model-revisions.spec.ts` |
| PW-7 | Non-behavioral | Streaming enforces 128 MiB/file, 512 MiB/batch and 200 files/batch, testing exact limit and limit+1 byte; filename/media validation precedes parsing. Oversize failure is visible and publishes no source revision. | 3 | [Validated: owner October 28; performance unmeasured] | `test_project_upload_bounds` |
| PW-8 | Behavioral | Keyboard-only navigation creates/opens a project and switches Sources/Reconstruction/Explore; unavailable capabilities state their prerequisite. Project switching invalidates pending requests and action acknowledgments. | 3 | [Assumed: verify] | `project-navigation.spec.ts` |

Eight criteria, all score 3. Full feature acceptance requires both workspace and
upload integration; a project form alone is not PW-3/6/7 verification.

## 4. Context and Decisions

Executor: backend owner for project persistence/API and the small initial UI;
frontend owner extends linked panels later. Main agent allocates exact base,
worktree, database, ports and single-writer contracts before delegation.
Owner approves scope/defaults. No branch or resource has been allocated.

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
The [first implementation packets](../../plan/feature-foundation-workspace-1.md)
specify the lifecycle and subsequent upload handoffs, including partial PW coverage.

Verification, tested SHA and integration version: not run/not assigned.
Proposed implementation bump: minor; this specification-only update is a patch.
Record exact runtime commands after foundation, not invented test successes.

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
