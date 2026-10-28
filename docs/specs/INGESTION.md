# Specification: Upload to restart-safe, attributed dataset revisions

> **Spec type:** Product/feature. **Backlog:** FL-005.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-27. **Decision owner:** project owner.
> **Status:** Design complete; real source profiles remain gated by inspected evidence.
> **Zero-Question Score:** 0 unowned design questions; G1/profile qualification remains.

## How to Read This Spec

Executor: source contracts and job lifecycle. QA: IN tests. Owner: supported
formats/limits. Implements project AC-1/2/8/10; supports every data-consuming feature.

## Notation Key

`[Validated]` is a project invariant; `[Assumed: verify]` is a proposed limit/profile.
H/M/L are confidence; all AC scores are 3. Synthetic fixtures are not pilot evidence.

## 1. Outcome Statement

The user uploads supported files and obtains a persistent, evidence-linked dataset
revision or explicit record/job failures without hand-editing scene geometry.
Verification: IN-1 through IN-8. Outcome score 3.

## 2. Scope

### IN Scope

Upload UI/API, source storage, persistent jobs, native readers, record validation,
source evidence navigation and revision publication. `[Validated: project]`

### OUT of Scope

LLM-authored facts, universal PDF/CAD parsing, full-release download, manual
adjudication UI, engineering projections and retrieval ranking. OCR is an explicit
conditional adapter, not an invisible fallback that marks all pages processed.

### Scope Dependencies

FL-004-A shared contract/environment precedes implementation. Native profiles
require individually reviewed sample mappings; full G1 is required for pilot
acceptance, not for synthetic upload/job tests.

### Open Scope Tensions

The large EDM export exceeds default limits. Preserve its candidate status; require
an approved streaming profile/limit revision before accepting that file.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| IN-1 | Behavioral | Fresh multipart upload yields source hashes, revision/job IDs and immutable originals; repeating identical content/idempotency key creates no duplicate records. | 3 | [Validated] | `test_upload_idempotency` |
| IN-2 | Behavioral | Each CSV/XLSX/LAS/XML/native-PDF fixture retains original values/units and exact locators, extractor/profile version and counted coverage; original document header outranks filename classification. | 3 | [Validated] | `test_source_profiles` |
| IN-3 | Negative | Traversal/absolute paths, nested ZIP/symlink/encrypted entries, XXE/DTD, macros, unsupported signatures and expanded-size violations fail explicitly without writing outside staging or making network calls. | 3 | [Validated] | `test_hostile_uploads` |
| IN-4 | Edge case | Killing/restarting the worker mid-stage leaves an interrupted attempt; a fenced retry cannot duplicate records or let the old attempt publish. Cancellation publishes no active revision. | 3 | [Validated] | `test_job_recovery` |
| IN-5 | Behavioral | Corrected sources create a new immutable revision; failed replacements preserve old results under old labels; partial revisions expose quarantined records/counts. | 3 | [Validated] | `test_revision_publication` |
| IN-6 | Negative | Missing reference, unknown event code, drilling/completion mismatch and suspicious equal MD/TVD are flagged; no invented CRS, ordering, installed state or zero values enter valid claims. | 3 | [Validated] | `test_source_conflicts` |
| IN-7 | Non-behavioral | Streaming enforces 25 MiB/file, 100 MiB/revision, 200 files and 500 PDF pages; only one heavy stage runs and local reads meet project AC-9 during import. | 3 | [Assumed: verify] | `test_ingestion_limits`, concurrent read benchmark |
| IN-8 | Dependency | Every accepted pilot family has an approved profile and all manifest expected records/pages matched or explicitly quarantined; a missing mandatory family cannot pass G1. | 3 | [Validated] | `test_pilot_ingestion` |

Full acceptance includes IN-8; success on invented fixtures is not real ingestion
verification. A supported format with an unknown schema returns `unsupported_profile`.

## 4. Context and Decisions

Executor: FL-005-A backend worker for upload/jobs/evidence UI; FL-005-B ingestion
worker for approved readers and claim publication. Owned planned paths:
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

Persist jobs as `queued/running/succeeded/partial/failed/cancelled/interrupted`;
attempts carry lease owner, expiry, heartbeat, fencing token and stage progress.
Claim jobs with transactionally locked rows (`SKIP LOCKED`); one heavy worker.
Retries re-read durable stage outputs and reuse deterministic keys; only classified
transient failures retry once. Validation failures do not auto-retry.

Source blobs are written before metadata publication using atomic rename.
If a transaction fails, unreferenced blobs remain eligible for an explicit,
scoped cleanup job; never delete referenced originals as retry cleanup.
Active revision changes in one transaction only after final validation.
Progress reports processed/total when known, otherwise stage/count without a fake
percentage. `ready_with_issues` identifies accepted versus quarantined records.

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
