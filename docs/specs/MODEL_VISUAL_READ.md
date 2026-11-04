# Specification: Model processing reads scanned pages visually and any readable non-PDF file

> **Spec type:** Agent task (backend, then small UI slice). Amends section 8 of
> [MODEL_PROCESSING_OUTCOME](MODEL_PROCESSING_OUTCOME.md) (TASK-075).
> **Load-bearing frameworks:** outcome, acceptance, failure conditions.
> **Date:** 2026-11-04. **Author:** orchestrator. **Decision owner:** project owner.
> **Status:** Approved for implementation (owner request 2026-11-04 10:48 EST: read scanned pages visually;
> pass files with no native parser, including `.ascii` and any file readable as text, to the model).
> **Backlog ID:** TASK-115. **Depends on:** TASK-075. **Integration version:** pending (minor).

## 1. Outcome Statement

Owner report (0.54.2): the model-processing estimate for `FWR_Completion_F14.pdf` (60 scanned pages) says
"60 of 60 selected pages have no text layer ... OCR is not available, so they send nothing and cost nothing"; the
estimate is USD 0 and nothing is read. Cause: the model step is text-only (`processing/model_step.py::_chunk_plan`
keeps only pages whose pdfium text layer has >= 20 non-space characters; `identity_read.build_messages` builds text
blocks only). It is not a regression; previously read files had text layers. Non-PDF documents are refused outright
(`not_a_pdf` in `processing/service.py`).

After this increment: (1) pages with no text layer are rendered and sent to the model as page images, with a real
cost estimate (image bound per page); results from them are labelled "read from image, unverified"; (2) documents
that are not PDFs (text, csv, xml, las, xlsx, `.ascii`, extension-less, anything that decodes as text, and binary
formats as a bounded printable-strings preview) are sent to the model as bounded text sections so it can identify
the content and extract identities. Verification: fake-provider tests (an image-only PDF built in the test, a
`.ascii` file, an xlsx) run to a stored result with a non-zero estimate and the right read mode; no live Meta call
is made by default tests.

## 2. Scope

### IN

1. **Visual pages.** A selected PDF page without a text layer is read as an image: rendered by `PageRenderer.render`
   (JPEG, long side from the renderer default), sent as an `ImagePart` in page order beside text pages of the same
   call. `pages_without_text` stays the informational list; the new `image_pages` (subset sent as images) drives the
   estimate. A page that cannot be rendered (`PageError`) is reported, sent nothing, and the run notes it.
2. **Honest cost.** The pre-flight bound of a chunk counts `image_token_bound` (`FIELDLENS_PROVIDER_IMAGE_TOKEN_BOUND`,
   default 8192) per image through the same `estimate_input_tokens` / `attempt_upper_bound_usd` the runner uses
   (runner bound <= confirmed estimate, PE-1 still holds). The estimate does not render pages (a minimal placeholder
   image stands in; only the count matters). New setting `FIELDLENS_PROCESSING_IMAGES_PER_CALL` (default 4): a call
   closes when it has `pages_per_call` pages or that many images.
3. **Unverified evidence.** A quote read from an image cannot be checked against a text layer. Identities from image
   pages are kept if the name is non-empty, the page was an image page of the call and the name occurs in the quote
   (normalized), and are stored with `read_mode = 'image'` (new column on `document_identity_proposal`, default
   `'text'`, migration `0021`) and validation state `unverified` (AX-13). They are never promoted to accepted facts; the
   existing merge-proposal/S3 flow treats them as proposals, and image-origin identities never auto-link on their own.
   Text-page identities keep the verbatim-quote check unchanged. A new warning `image_pages_unverified`
   ("N pages were read from images; quotes could not be checked") is added to the result.
4. **Non-PDF documents.** Any stored document whose family is `text`, `csv`, `xml`, `las`, `xlsx` or `ole` (the
   families intake accepts) can be estimated, confirmed and read by the model step:
   - Text-decodable content (the stored `text_encoding` or `textenc` detection; `.ascii`, `.dat`, `.asc`, extension-less
     and "random" text files all qualify, the filename is a hint only) is split into **sections** of at most 12,000
     characters on line boundaries, section `n` playing the role of page `n` (the same `<<<DOCUMENT_PAGE n>>>` blocks,
     quote check against the section text, identical validation). Default sections read: `min(5, total)`; the user
     can choose 1..total as for pages.
   - `xlsx`: rendered by the app to tab-separated text per sheet (stdlib `zipfile` + `xml.etree`; refuse any entry
     with `<!DOCTYPE`/`<!ENTITY`; <= 200 rows x 30 columns per sheet, <= 20 sheets, values as stored, no formulas run);
     sheet names are included. Sections are cut as above.
   - `ole` and any file that is mostly non-text: a bounded preview (first 4 KiB as hex+ASCII, then up to 8 KiB of
     printable-string runs >= 6 chars), labelled "binary preview"; the model is told it is a preview of an unknown
     binary, may answer `category: null` with no identities. No file is executed or opened by any external program.
   - The prompt version is bumped (`doc-identity-2`) only for the added instructions (image pages, sections, binary
     preview); the text-only prompt body for text PDFs is unchanged.
5. **Cache and reprocessing.** A stored result whose warnings include `no_text_layer` with 0 tokens (the legacy "read
   nothing" outcome) is never a cache hit, so those documents are re-readable without `force`. The cache key stays
   (document, page/section range, prompt/schema version).
6. **Eligibility and wording.** `processable` and the estimate accept non-PDF families above; refusals `not_a_pdf` remain
   only for families outside the list (none today). Reconstruction S2 (`reconstruction/reading.py`) also targets non-PDF
   documents in those families whose native state is `unsupported`. UI wording: the "OCR is not available" warning is
   replaced by "N pages have no text layer and are read visually (about X tokens each)"; the page-count field reads
   "Sections" for non-PDF documents; an identity read from an image shows an "Unverified: read from image" badge.
7. **Contracts.** Pydantic DTOs gain: estimate/state `unit` (`page` | `section`), `image_pages`, per-document
   `read_mode` summary (`text` | `image` | `mixed` | `binary_preview`), identity `read_mode`. Then
   `npm --prefix frontend run generate:contracts`.

### OUT

- OCR engines (Tesseract/Docling) and table reconstruction from scans (TASK-030 line; this is a model read).
- Widening intake beyond what it accepts today (docx/pptx/images/unknown binary are still refused at upload:
  `unsupported_signature` / `unsupported_archive`). Recommended follow-up (needs a security review, owner decision):
  accept images (reuse the visual path) and docx.
- Engineering facts: nothing read from an image or a binary preview enters calculations or published scenes without
  the normal validation; generic/unverified values never become verified.
- Any spend gate on a confirmed manual run (unchanged: TASK-075 section 8 still applies).
- Auto-reading all pages of a 500-page scan: the user still chooses the page count (default `min(5,total)`).

### Scope Dependencies

TASK-075 (merged), the existing `PageRenderer` / `ImagePart` / `MetaProvider` `input_image` path. Meta `muse-spark-1.3`
image input is assumed from the candidate harness; a bounded authorized live check is a separate owner step.

### Open Scope Tensions

None blocking. `[Assumed: owner, 2026-11-04]` 4 images and 10 pages per call, 12,000 chars per section, 8,192 tokens per
image bound (conservative for a ~1,600 px JPEG).

## 3. Acceptance Criteria

| ID | Type | Criterion | Score | Test |
|---|---|---|---|---|
| VR-1 | Behavioral | An image-only PDF (3 pages built with Pillow) estimates > 0 input tokens, `image_pages == [1,2,3]`, and a confirmed fake-provider run stores a result; the provider saw `ImagePart`s in page order | 3 | pytest |
| VR-2 | Behavioral | Runner pre-flight bound <= confirmed estimate for image and mixed (text + image) selections; 9 image pages with 4 images/call run as 3 calls | 3 | pytest |
| VR-3 | Negative | An identity from an image page is stored with `read_mode='image'`, state unverified, and a text-page identity with a quote not in the text is still dropped; image identities never auto-link | 3 | pytest |
| VR-4 | Behavioral | A `.ascii` text file (and an extension-less one, and a `.dat` that is not tabular) is estimable, confirmable and read in sections; a quote not in the section is dropped | 3 | pytest |
| VR-5 | Behavioral | An xlsx is rendered to bounded TSV sections; a workbook entry with a DOCTYPE/ENTITY is refused with a typed reason, no read | 3 | pytest |
| VR-6 | Edge | A binary (`ole`) file yields a bounded preview call; truncated/oversized files stay within the byte caps; nothing is executed | 3 | pytest |
| VR-7 | Edge | A page that fails to render is listed, sends nothing, and an all-failed selection ends `no_text_layer` with zero spend (never a silent success) | 3 | pytest |
| VR-8 | Regression | A legacy `no_text_layer`/0-token result is not a cache hit; text-PDF estimate/run, force/reuse, stub path and TASK-072/075 behaviour unchanged (existing processing suites) | 3 | pytest |
| VR-9 | Behavioral | Dialog shows the visual-read note, section wording for non-PDF and the "Unverified: read from image" badge; no remaining-budget row | 3 | vitest |
| VR-10 | Integrity | Contract drift check passes; migration `0021` upgrades/downgrades on real PostgreSQL | 3 | `check:contracts`, pytest |

Definition of done: all ACs pass with the fake provider; actual commands and results recorded; live Meta unverified is
stated explicitly.

## 4. Context and Decisions

- Decisions: images over OCR because the owner requires the model to rely on visual parsing (2026-11-04); image
  identities are proposals only (AX-13, "model-read, unverified"); non-PDF read reuses the page machinery with
  "sections" instead of a second pipeline; bounded cost shown before confirm.
- Delegation: backend slice `fieldlens-rag` (model step, prompt, validation, estimate) in worktree
  `/home/slimco/code/FieldLens-worktrees/task-115-visual-read` on `feature/task-115-visual-read`, base = master tip at
  creation. Frontend slice `fieldlens-frontend` follows in the same worktree after the generated contracts land
  (one writer at a time). Independent QA by `fieldlens-qa` afterwards. Migration number `0021` is pre-assigned to this
  lane; `VERSION`/`CHANGELOG`/backlog are orchestrator-only. No live Meta calls; own `./dev` lane/DB.
- Contracts: see IN item 7. Image bytes never persist in the database or logs (only counts and the page list).
- Agent/UI effects: as IN item 6.

## 5. Failure Conditions

- Provider rejects images (model lacks vision) -> typed `provider_rejected`/`provider_error` run failure, retryable, spend
  recorded; never a silent text-only fallback.
- A rendered image exceeds the 10 MiB part limit or `HARD_CAP_LONG_SIDE` -> that page is reported unreadable.
- A file larger than the section cap x the chosen count is read only up to the selection; the result says which sections.
- Cancel/budget/ledger failures behave as in TASK-075 (no rows written on a stop).
- Worst misinterpretation: passing an image read off as verified. Prevented by VR-3 (state + badge) and never writing
  `status` other than `model_proposal`.

## 6. Ambiguity Audit

- Section = 12,000 chars (below `MAX_TEXT_CHARS` 20,000) so the existing page-text bound applies. Binary preview counts
  as one section. Pages are always `1..N` as in TASK-075.
- Mixed calls keep page order; identity `page` is the page/section number as for text.

## 7. Implementation Guidance

Files: `processing/model_step.py`, `processing/identity_read.py` (messages with image parts, validation by read mode,
prompt), `processing/identity_store.py`, `processing/tables.py` + migration `0021`, `processing/service.py`
(eligibility, non-PDF page counting), a new `processing/document_text.py` (section reader: text, xlsx, binary preview),
`processing/runtime.py`, `reconstruction/reading.py`, `config.py`, `contracts/processing.py` (+ registry,
generated client), `frontend` processing dialog/panel. Reuse `candidates.pages.PageRenderer`, `textenc`, `ImagePart`.
Checks: `uv run pytest backend/tests/processing backend/tests/assistant backend/tests/contracts`,
`uv run ruff check backend scripts && uv run ruff format --check backend scripts`, `uv run mypy backend/fieldlens scripts`,
`npm --prefix frontend run lint && npm --prefix frontend run test && npm --prefix frontend run check:contracts`.

### Implementation handoff and integration

| Field | Record before handoff / after integration |
|---|---|
| Feature commits / tested HEAD | pending |
| Verification | pending (fake provider only; live Meta unverified) |
| Compatibility assessment | additive DTO fields + one additive migration: new feature |
| Proposed version bump | minor |
| Proposed changelog entry | TASK-115: scanned pages and non-PDF files are read by the model (unverified, estimated) |
| Integrated commit / final version | pending |
| Backlog status | in progress |

## Open Tensions

Intake widening (docx, images, unknown binaries) is left to the owner after this slice.

## Assumption Registry

Meta model accepts `input_image` (M; candidate harness precedent, not live-verified for this step); 8,192 tokens/image
bound is an upper bound (M). Invalidated by a provider rejection or a measured per-image cost above the bound.

## Adversarial Self-Critique

Could appear correct while: the estimate renders nothing so a huge scan looks cheap (guarded: bound per image is
counted); images are silently dropped when rendering fails (VR-7); image identities leak into verified matching (VR-3).

## Revision Triggers

Live Meta rejects image input; measured image tokens exceed the bound; owner widens intake.
