# Specification: Project upload to restart-safe, attributed source revisions

> **Spec type:** Product/feature. **Backlog:** FL-005.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-28. **Decision owner:** project owner.
> **Status:** Upload byte/file limits approved October 28; source profiles and detailed packet qualification remain gated.
> **Zero-Question Score:** 0 unowned design questions; G1/profile qualification remains.

## How to Read This Spec

Executor: source contracts and job lifecycle. QA: IN tests. Owner: supported
formats/limits. Implements project AC-1/2/8/10; supports every data-consuming feature.

## Notation Key

`[Validated]` is a project invariant; `[Assumed: verify]` is a proposed limit/profile.
H/M/L are confidence; all AC scores are 3. Synthetic fixtures are not pilot evidence.

## 1. Outcome Statement

The user uploads supported files within a project and obtains a persistent,
evidence-linked source revision or explicit record/job failures; ingestion does
not publish an asset model.
Verification: IN-1 through IN-9. Outcome score 3.

## 2. Scope

### IN Scope

Upload UI/API, source storage, persistent jobs, native readers, record validation,
source evidence navigation, source-revision finalization and, from October 30, removal of a
source's stored bytes with a tombstone revision (IN-9, TASK-039). `[Validated: project]`

### OUT of Scope

LLM-authored accepted facts, universal PDF/CAD parsing, full-release download, manual
adjudication UI, asset-model publication, engineering projections and retrieval ranking. OCR is an explicit
conditional adapter, not an invisible fallback that marks all pages processed.

### Scope Dependencies

FL-004-A contracts and FL-015-A project workspace precede upload implementation. Native profiles
require individually reviewed sample mappings; full G1 is required for pilot
acceptance, not for synthetic upload/job tests.

### Open Scope Tensions

The large EDM export exceeds default limits. Preserve its candidate status; require
an approved streaming profile/limit revision before accepting that file.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| IN-1 | Behavioral | Fresh project-scoped multipart upload yields source hashes, source revision/job IDs and immutable originals; repeating identical content/idempotency key creates no duplicate records. Source publication cannot move the active model pointer. | 3 | [Validated] | `test_upload_idempotency` |
| IN-2 | Behavioral | Each CSV/XLSX/LAS/XML/native-PDF fixture retains original values/units and exact locators, extractor/profile version and counted coverage; original document header outranks filename classification. | 3 | [Validated] | `test_profiles_witsml`, `test_profiles_sources`, `test_extraction_flow` (opt-in `test_local_data_profiles`) |
| IN-3 | Negative | Traversal/absolute paths, nested ZIP/symlink/encrypted entries, XXE/DTD, unsupported signatures and expanded-size violations fail explicitly without writing outside staging or making network calls. Source code/macros are never executed; an approved legacy-Word profile may read inert streams despite macro presence and records that boundary. | 3 | [Validated] | `test_hostile_uploads` |
| IN-4 | Edge case | Killing/restarting the worker mid-stage leaves an interrupted attempt; a fenced retry cannot duplicate records or let the old attempt publish. Cancellation publishes no active revision. | 3 | [Validated] | `test_job_recovery` |
| IN-5 | Behavioral | Corrected sources create a new immutable revision; failed replacements preserve old results under old labels; partial revisions expose quarantined records/counts. | 3 | [Validated] | `test_revision_publication` |
| IN-6 | Negative | Missing reference, unknown event code, drilling/completion mismatch and suspicious equal MD/TVD are flagged; no invented CRS, ordering, installed state or zero values enter valid claims. | 3 | [Validated] | `test_profiles_witsml`, `test_profiles_sources` (conflicts, placeholders, missing references/units) |
| IN-7 | Non-behavioral | Streaming enforces 128 MiB/file, 512 MiB/batch, 200 files and 500 PDF pages; test exact byte limits and +1 byte. Only one heavy stage runs and local reads meet project AC-9 during import. | 3 | [Validated byte/file limits; parser/performance limits to verify] | `test_ingestion_limits`, concurrent read benchmark |
| IN-8 | Dependency | Every accepted pilot family has an approved profile and all manifest expected records/pages matched or explicitly quarantined; a missing mandatory family cannot pass G1. | 3 | [Validated] | `test_pilot_ingestion` |
| IN-9 | Behavioral | Owner decision October 30. Removing a project document (after an explicit confirmation) physically deletes its stored bytes and derived content copies (text chunks, embeddings, page renders, extraction artifacts) and frees the disk space (a blob still referenced by another document or project is kept), cancels any running job for it first, and records a new immutable source revision that keeps only a tombstone (document ID, content hash, size, filename, classification, removal time, previous revision). Claims and evidence that came only from the removed content become inactive and non-citable (excluded from retrieval, tools, new calculations and new reconstruction runs) and say "source removed"; a published model stays pinned and is labeled as depending on a removed source (PW-6). Removal is irreversible; re-uploading the same bytes creates a fresh document and revision (the idempotency replay does not resurrect the tombstone). Other projects and documents are untouched (PW-2). | 3 | [Validated: owner, October 30; consequences Assumed: verify] | `test_source_removal_frees_bytes`, `test_removal_tombstone_revision`, `test_removed_source_excluded`, `test_reupload_after_removal`, `test_removal_cancels_job`, `test_removal_project_isolation` |
| IN-10 | Negative | Owner request November 1. When a batch contains files the server refuses (unsupported signature, executable content, DTD, empty, oversize, too many pages), the response names **every** refused file (original filename, document position in the batch, `reason` code and the human reason) and the batch outcome is stated explicitly (nothing stored, or the accepted remainder stored, as decided in the spec); the UI marks each refused file red with its reason (text and icon, not colour alone), keeps the accepted files selected, and offers retry without them. A response that cannot attribute a refusal says so. | 3 | [Decided November 1 (owner delegated): all-or-nothing. Every file is preflighted, nothing is stored if any is refused, `error.details` is `ImportRefusal` (`scope` files|batch, `refused_files[{filename, position (0-based), reason, message, error_code, status_code, limit}]`, `batch_outcome: nothing_stored`); batch-level refusals (size, count, malformed) are `scope: batch`. Backend implemented; UI pending TASK-050] | `test_upload_rejection_names_files`, Vitest + axe for the refused-file rows |
| IN-11 | Behavioral | Owner request November 1. Plain-text sources are accepted regardless of extension: extensionless files and legacy encodings (UTF-16 without BOM, Windows-1252/Latin-1) that decode without NUL/control corruption are inspected as text, the detected encoding is recorded, and content detection (never the filename) selects a profile. Binary content, executables and undecodable bytes are still refused with IN-10 reporting. The Volve Compass "Standard Survey Report" text export (extensionless `Volve F_F-<n>_F-<n>_F-<n>_ACTUAL` next to the PDF) gets a native profile that yields trajectory stations (MD, inclination, azimuth, TVD, offsets, with the units, reference and datum the file states, never assumed) and is preferred over the PDF text layer when both exist, reporting any disagreement between them as a conflict. | 3 | [Proposed: owner request, November 1; file layout to be confirmed from the sample. Intake implemented (`fieldlens/textenc.py`, encoding recorded in `origin_metadata.text_encoding`); the Compass profile is not implemented until the sample layout is read] | `test_text_intake_encodings`, `test_profiles_compass_survey_text`, opt-in `test_local_data_profiles` |

**TASK-009 implementation status (IN-2/IN-6, implementer evidence only).** Native profiles
(versioned, content-detected): WITSML tubular/bhaRun/wbGeometry/trajectory, Volve production
workbook, LAS 2.0, perforation and well-pick fixed-width `.dat`, Compass Standard Survey
Report PDF (pypdf text layer). Runs persist in `extraction_run`/`extracted_record`/
`extraction_issue` (migration `0005_native_profiles`), are executed by the job worker thread
under a lease, and an interrupted run is never shown as succeeded. A profile version change
makes the run stale and a re-queue supersedes it; unchanged re-runs are no-ops, and a failed or unsupported run is re-queued only when the profile set or content changed or on an explicit `?retry=true`. The 500-page
PDF limit is enforced at upload. Deferred: EDM export, grids, large completion PDFs/plots,
OCR (TASK-030). The Volve `Geophysical_Interpretations/Wells/README.txt` (lines 1-11) only says the picks file holds the main picks (repeated `Obs#` when a well crosses a formation several times) and the perforation file holds perforation intervals; it states no unit, depth reference or column definitions, so those depths stay `unsupported` with MISSING_UNIT/MISSING_REFERENCE findings. 

**Coverage wording (do not overstate).** "Equipment" in the coverage matrix means
drilling-assembly (tubular/BHA), bore-geometry and casing-point records; "completion" means
perforation intervals whose depths are `unsupported` (no unit/datum documented). A completion
string, packers and tubing are NOT extracted (deferred completion PDFs); every extraction
report carries that gap per wellbore in `coverage_notes`. The report keeps wellbore
labels as written (`wellbore_identities`, with the parent `well_key` separate) and raises an
`IDENTITY_MISMATCH` finding when sources spell the same well differently; labels are never
merged silently. Event times keep a `Z`/offset marker (`UTC` or `UTC+HH:MM`; not an IANA zone);
naive times stay naive and flagged. A comma in a number is accepted only as an unambiguous
thousands separator (`1,234.5`); `1,5` stays unknown.

**Known limitations (memory).** `parse_tree` can reach about 1 GB peak at the 2M-node
limit; the xlsx reader loads each sheet whole (about 290 MB for the production workbook) and
workbooks above about 40k rows are refused. Parsing runs in the worker thread with bounded
concurrency, so one large parse at a time is the supported envelope.

Opt-in real-data run: `FIELDLENS_LOCAL_DATA_ROOT=<root> uv run pytest
backend/tests/test_local_data_profiles.py -s`.

Full acceptance includes IN-8; success on invented fixtures is not real ingestion
verification. A supported format with an unknown schema returns `unsupported_profile`.

**FL-005-A implementation status (TASK-006, not yet independently accepted).** Backend tests
exist and passed on PostgreSQL for IN-1 (`test_upload_idempotency`), IN-3
(`test_hostile_uploads`; inert ZIP central-directory and byte-wise DTD checks only), IN-4
(`test_job_recovery`, `test_restart_persistence` with a real `kill -9`), IN-5
(`test_revision_publication`) and IN-7 byte/file limits (`test_ingestion_limits`, exact
boundary and +1). Not covered: IN-8 (the 500-page PDF limit landed with TASK-009), parse-time XLSX XML DTD scanning and the local-read latency/RSS benchmark.
UI checks are implemented but only implementer-verified (see the UI traceability notes
below). Storage verification is not extraction: files are labelled
`pending_extraction` or `unsupported`, never extracted.

**FL-005-A UI traceability (implementer evidence; no independent acceptance claimed).**
Code: `frontend/src/features/uploads/*`, wired into the project Sources section.

| Criterion | UI evidence |
|---|---|
| IN-1 (upload, hashes, replay) | `tests/uploads.test.tsx` (metadata part first, files aligned, expected parent, stable idempotency key on retry, HTTP 200 replay wording); `tests/e2e/uploads.spec.ts` UP-1 (real API: upload, SHA-256 shown, identical re-upload reported as a no-op, API-level 202 then 200 `replayed`). |
| IN-3 (hostile/unknown input) | E2E: an ELF-signature file gets a visible 415 message and creates no revision; unknown plain text shows `unsupported`. Server hostile-input checks remain backend-only. |
| IN-4 (cancel/retry) | Vitest: cancel via `POST .../jobs/{id}/cancel`, attempt list and "retried once automatically" note, polling stops when the job finishes or the panel unmounts. No UI test kills a worker. |
| IN-5 (partial revisions) | Vitest: revision `status`, `quarantined_count`, parent revision and per-document `replaces_document_id` render a "Partial revision ... may have displaced a previously good version" warning. Not exercised against a real partial revision in E2E (no fixture produces quarantine yet). |
| IN-7 (limits) | Vitest: client-side 128 MiB/file, 512 MiB/batch and 200-file checks block submission with an `alert`; 413/409/415 and network errors are surfaced. Server limits stay authoritative and are tested by `test_ingestion_limits`. |

Behaviour notes: statuses are shown as the API reports them (`stored`, `pending_extraction`,
`unsupported`, `quarantined`); the UI never says a file was extracted or validated. A
mid-upload abort says nothing was imported; an abort after all bytes were sent says the
outcome is unknown and a resubmit reuses the idempotency key. Not verified: real
multi-hundred-MiB uploads and progress, drag-and-drop in a browser, screen-reader output,
and a real worker retry/cancel race in the browser.

QA repairs (D1-D3) and behaviour notes:

- A rejected or failed import (409 `stale_parent`/`import_in_progress`, idempotency
  conflict, 503/DB failure) leaves no rows, no staging files and no new blob: blobs are
  published only after every validation passed, under the project lock, and a later
  failure removes just the blobs this request created and no document references
  (re-checked under the project lock, so a blob referenced by a concurrent import is kept).
  `test_upload_cleanup`.
- Abandoned `storage/staging/<uuid>` directories (e.g. after `kill -9`) are swept at API
  startup and periodically by the job loop when their newest mtime is older than
  `staging_max_age_s` (default 3600 s). Staging of in-flight requests in this process is
  never swept; symlinks are not followed. Follow-up (not implemented): a sweep of orphan
  blobs (a blob left by a crash between publish and DB commit); it is harmless (unreferenced,
  never served) but needs a race-safe reconciliation against `source_document`.
- A client disconnect mid-upload is logged at warning level without filenames or tracebacks
  and answered `400`; staging is discarded.
- In-batch duplicate bytes collapse to one document that keeps the first file's filename
  and hints; `ImportAccepted.document_ids` maps duplicates to the same id.
- A partial (`ready_with_issues`) revision that quarantines or drops a previously good
  document version still becomes the project's latest revision. UI note: surface
  `SourceRevisionSummary.status`, `quarantined_count` and the per-document
  `replaces_document_id` so users see that an older good version is no longer in the latest
  revision.
- `JobWorker._is_dead_owner` treats another worker in the same process (same pid, different
  owner id) as dead; the app runs one worker per process, so this is a documented limit.
- TASK-009 acceptance items (explicitly deferred): the 500-page PDF limit (page counting
  needs the parser); parse-time XLSX XML DTD/XXE rejection and ZIP-entry scanning during
  extraction, beyond the upload-time central-directory and byte-wise DTD checks.

## 4. Context and Decisions

Executor: FL-005-A backend worker for upload/jobs/evidence UI; FL-005-B ingestion
worker for early qualified native readers; FL-005-C for selected scanned-PDF and
legacy-Word evidence; FL-005-D for full manifest/profile acceptance. B/C provide
source observations, not active engineering claims. Owned planned paths:
`backend/fieldlens/{jobs,ingestion,evidence}`, upload/evidence frontend features
and matching tests. Both serialize migrations/generated API changes.

Use [shared envelopes](SHARED_CONTRACTS.md). Source profile key is format/version +
header/signature + profile revision, never merely a basename. Profiles declare
column/tag mappings, units/null tokens, identity, planned/as-built/drilling
classification, time semantics, table completeness and quarantine rules.
No cross-well joining from metadata-index `well` tags alone.

Registered families: CSV/DAT, XLSX read-only without macros, LAS 2.x, WITSML
1.4.1.1, native PDF text/tables. CSV numeric parsing retains source decimals;
LAS null sentinels become missing, not zero; XML UIDs and namespace paths survive.
PDF extraction uses pypdf/pdfplumber, counts all pages and reports empty/scanned
pages as `ocr_required`. Evidence UI opens PDF.js at the cited page or a structured
cell/XML/text locator view. Do not synthesize absent bounding boxes.

The inspected F-14 equipment schematic is scanned; the F-5 completion report
contains legacy-Word embedded images. These are required selected-source profiles
for pilot equipment acceptance, not optional polish or proof that native PDF text
alone is enough. FL-005-C must account for each required page/image with a reviewed
extraction fixture, original locator and safe image/text view. Unknown formats may
be retained only as explicitly unsupported sources under an approved safe storage
profile; they never report successful extraction. No macros/document code execute.
An archive's expanded bytes count against the same batch limit.

Persist jobs as `queued/running/succeeded/partial/failed/cancelled/interrupted`;
attempts carry lease owner, expiry, heartbeat, fencing token and stage progress.
Claim jobs with transactionally locked rows (`SKIP LOCKED`); one heavy worker.
Retries re-read durable stage outputs and reuse deterministic keys; only classified
transient failures retry once. Validation failures do not auto-retry.

Source blobs are written before metadata publication using atomic rename.
If a transaction fails, unreferenced blobs remain eligible for an explicit,
scoped cleanup job; never delete referenced originals as retry cleanup.
Only the latest source revision pointer changes after source validation; active
model publication belongs to FL-016 and requires an explicit reviewed revision.
Progress reports processed/total when known, otherwise stage/count without a fake
percentage. `ready_with_issues` identifies accepted versus quarantined records.

All reader/job issue outputs use [QualityIssue](SHARED_CONTRACTS.md#quality-issues)
and the [shared inspector](DATA_QUALITY.md). Missing F-12 dimensions and conflicting
source values must stay traceable; do not code special success outputs for known
filenames or audit hashes. The inspected F-5 Word file contains macro streams:
the selected profile extracts inert text/images, never invokes macros/Office code.
Storage-only success reports byte verification, not successful extraction.
The [first implementation packets](../../plan/feature-foundation-workspace-1.md)
define the upload/job slice and its explicitly deferred parser acceptance.

Conditional OCR evaluation: ingestion owner tests Docling on <=20 approved pages,
measures page/table/cell accuracy and peak RSS against the same gold fixture.
Accept only 100% required engineering attributes/locators correct, no unaccounted
pages and <=1536 MiB worker RSS. Otherwise retain explicit unresolved pages and
return a bounded plan amendment, not an unapproved alternative service.

## 5. Failure Conditions

Unknown source mapping -> quarantine the record/family and stop its projection,
not unrelated validated records. Missing write space/DB -> fail job with
sanitized diagnostics and preserve the previous active revision.
Worst misinterpretation: extraction of one page cannot count as processing a
whole PDF; IN-2/8 compare coverage and required records.

## 6. Ambiguity Audit

Publication, correction and recovery behavior are fixed above. Source-specific
units/event codes/tolerances are owned G1 decisions due before adapter acceptance.
The source manifest is never replaced by the metadata-only candidate CSV.

## 7. Implementation Guidance

First FL-005-A: IN-1/3/4/5/7 plus accessible progress/evidence skeleton.
Then FL-005-B: IN-2/6/8 and source adapters; accepted source evidence enables
downstream real-data tests. Planned checks:
`uv run pytest backend/tests/ingestion backend/tests/jobs`,
frontend upload/evidence interaction tests, relevant type/build checks.
Record actual fixtures, profile versions, RSS, elapsed time and results.
No implementation verification yet; propose minor on delivery.

## Open Tensions

OCR failure cannot waive required equipment/history data. Select a cleaner
authorized source or seek a scope/profile amendment from the owner.

## Assumption Registry

Required source formats fit initial profiles (M; G1 validates).
Native extraction preserves needed tables (M; gold cells validate).
One heavy worker meets local latency/RSS budgets (M; IN-7 measures).

## Adversarial Self-Critique

Filename labels may hide another well/report type; test internal headers.
Job retries may publish twice; kill and fence attempts.
PDF parsers may silently omit tables; compare per-page coverage and gold cells.

## Revision Triggers

Reopen profiles on a new XML/LAS dialect, OCR accuracy/RSS failure, or required
source files exceeding approved limits; retain all failed evidence.
