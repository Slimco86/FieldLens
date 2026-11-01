# Specification: Staged processing flow from upload to reconstruction start

> **Spec type:** Product/feature + API contract.
> **Load-bearing frameworks:** outcome, acceptance, scope.
> **Supporting:** failure conditions, ambiguity audit.
> **Date:** 2026-11-01. **Author:** orchestrator. **Decision owner:** owner.
> **Status:** Approved by the owner, November 1 2026 14:26 EST (TASK-054, 056, 057, 058 authorized; TASK-055 after TASK-054).
> **Backlog ID:** FL-005 / FL-016 / FL-022 (TASK-053..TASK-059). **Delivery state:** specifying.
> **Approved spec revision/date:** decisions D1..D6 below, owner, November 1. **Integration version:** pending.
> **Zero-Question Score:** 0 unowned; open items listed in "Open Scope Tensions".

Complements [INGESTION.md](INGESTION.md), [AGENTIC_EXTRACTION.md](AGENTIC_EXTRACTION.md),
[ASSET_RECONSTRUCTION.md](ASSET_RECONSTRUCTION.md) and UI-15 in
[UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md). It defines the stage order and the gates between stages;
the detail of each stage stays in those documents.

## Notation Key

`[Validated]` = owner confirmed; `[Assumed: verify]` = proposed by the orchestrator, owner to confirm.

## 1. Outcome Statement

After this increment a user who has uploaded files can see, per document, whether it was parsed natively, needs
processing, or failed; can start processing of any document with or without a label; sees all data grouped per category
under each identified well/wellbore; can review AI-proposed identity merges; and can only start reconstruction when
the minimum conditions are met. Verification: browser walkthrough upload -> process -> per-wellbore data view -> merge
review -> start, against synthetic fixtures with a stub provider, then one bounded live run.

## 2. Stage model

| # | Stage | Trigger | Spend | Output |
|---|---|---|---|---|
| 1 | Import, verification, native parsing, indexing | automatic after upload | none | per-document state, native records |
| 2 | Document processing for sources without a native profile (PDF scans, other PDFs) | explicit user action, per document or selection, labels optional | model (estimate + confirm); OCR only where D2 allows | classification, label proposal, label-driven extraction candidates |
| 3 | Preliminary data exposure | automatic, read-only | none | per wellbore, per category view of associated records with source links, gaps and conflicts |
| 4 | Identity refinement | explicit user action | model (estimate + confirm) | merge proposals with alias evidence; user accepts or rejects each |
| 5 | Reconstruction | explicit user action, gated | model (estimate + confirm) | run per ASSET_RECONSTRUCTION.md |

Labels and tags are hints for stages 2 and 4, never a precondition and never evidence.

## 3. Owner decisions (November 1)

- **D1 [Validated]** PDF processing can start with or without a label. Unsupported/"no matching profile" is not a terminal
  dead end: the state reads "no native parser; model processing available, not started" and offers the action.
- **D2 [Validated]** Documents with neither identity nor label are classified first. OCR may serve as this first pass
  **only where it is demonstrably cheaper and faster** than a model page read; the benchmark (cost and time per page on
  the same pages, classification agreement) is recorded in the spec before OCR is enabled; otherwise the model reads the
  pages. This amends the October 31 "OCR dropped" decision only for this classification role. Once the identity is known
  the label is determined, and extraction is the label-driven agent step, not OCR.
- **D3 [Validated]** Read all pages up to a bound of **500 pages per document and per processing run**; the estimate shows
  pages, route (OCR or model), tokens and USD before confirmation; larger documents are refused or split by an explicit
  page range, never silently truncated.
- **D4 [Validated]** Minimum to proceed to stage 5: at least one well and wellbore identified **with a validated trajectory**.
- **D5 [Validated]** A missing surface location is a warning, not a blocker. Surface location is read from trajectory or
  well-information sources when present. When absent, the wellbore uses a **labelled local display origin (0, 0)**:
  marked "unlocated, assumed", no CRS or datum, excluded from any georeferenced calculation (cross-well distance,
  terrain/formation alignment, closest approach), replaced as soon as a sourced location exists. This is the unlocated
  representation required by the project rules, not an invented well position.
- **D7 [Validated, 2026-11-01 14:26]** The owner approved this spec. Total live-model spend for developing and testing
  everything in this spec is capped at **USD 5** (aggregate across all lanes and runs, including retries; minimize it).
  Default tests use the stub provider and never spend. Any live run needs an explicit orchestrator authorization with a
  per-run cap and is recorded in the budget ledger; the pre-run estimate must fit the remaining USD 5 less recorded spend.
- **D8 [Validated, 2026-11-01 14:26]** OCR is out of the first implementation. The OCR-versus-model comparison from D2 is
  a separate benchmark task (TASK-060); stage 2 is model-only until it proves OCR cheaper and faster.
- **D9 [Validated, 2026-11-01 16:39]** A name as written in a source (for example `F-12`, `F-5`) is a valid wellbore
  identity even without a block or well key. If it differs from a fully qualified name (`15/9-F-12`) it is a separate
  wellbore until stage 4 detects that they are one entity and the user accepts the merge; the data is then unified.
  The resolver never invents a block, and an unqualified label never merges silently (TASK-061).
- **D6 [Validated]** Sources that name the same entity differently are reconciled by an AI refinement step (stage 4)
  whose proposals the user reviews. Hard guards stay deterministic (well and wellbore are distinct; no merge across
  different wellbore designators without source support); nothing merges silently.

## 4. Acceptance criteria

| ID | Type | Given / when / then | Score | Test |
|---|---|---|---|---|
| PF-1 | Behavioral | An imported PDF without a native profile shows a "Process" action regardless of label; starting it creates a persistent processing run scoped to the project and the selected documents | 3 | `test_processing_runs_start_without_label` |
| PF-2 | Behavioral | Before confirmation the API returns an estimate (pages, route, tokens, USD, remaining project/period budget); confirmation is a separate call; nothing is spent without it | 3 | `test_processing_estimate_confirm` |
| PF-3 | Negative | A document over 500 pages is refused with the page count and the option to choose a range; no silent truncation | 3 | `test_processing_page_cap` |
| PF-4 | Behavioral | OCR is selected only for documents with no identity and no label and only when the recorded benchmark shows it cheaper and faster; otherwise the model route is used and the route is recorded per run | 3 | `test_processing_route_selection` |
| PF-5 | Behavioral | After classification a label is proposed with evidence; user-assigned labels always win; extraction follows the label's agent step | 2 | `test_classification_label_proposal` |
| PF-6 | Behavioral | The data view lists, for each wellbore, records grouped per category with source locator, validation state, gaps and open conflicts; unresolved proposals are not shown as accepted facts | 3 | `test_wellbore_data_exposure` |
| PF-7 | Behavioral | Merge proposals carry both identities, alias evidence quotes and a guard result; accept/reject is persisted; a proposal violating a deterministic guard cannot be accepted | 3 | `backend/tests/merge_proposals/` (see MERGE_PROPOSALS.md MP-1..MP-9) |
| PF-8 | Behavioral | "Start reconstruction" is disabled with the exact unmet condition until D4 holds; a missing surface location adds a warning and the local origin, never a block | 3 | `test_reconstruction_start_gate` |
| PF-9 | Negative | A wellbore on the local origin is excluded from cross-well distance, terrain alignment and closest-approach results, and the exclusion is stated | 3 | `test_unlocated_origin_excluded` |
| PF-10 | Failure | Provider failure, refusal, truncation, cancellation and budget stop leave the document in an explicit, retryable state; interrupted work never shows as processed | 3 | `test_processing_failure_states` |

### 4.1 Implementation traceability: processing-run contract (TASK-054)

Covered by `backend/tests/processing/test_processing_runs.py` (stub provider; no network, no spend): PF-1, PF-2,
PF-3 and PF-10 (`test_processing_runs_start_without_label`, `test_processing_estimate_confirm`,
`test_processing_page_cap`, `test_processing_failure_states` plus cancel, interrupted, budget-stop and
concurrency tests). Migration `0011_processing_runs`; routes under `/api/v1/projects/{project_id}/processing`:
`GET /documents`, `POST /runs/estimates`, `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/confirm|cancel|retry`.

- A retry is a **new estimate** for the retryable documents (`retry_of_run_id`); it spends only after its own confirm.
- A document sits in at most one pending/running run (partial unique index); a confirm that would double-process is 409.
- The remaining budget is the USD 5 cap (D7) minus ledger spend minus confirmed, unfinished run estimates. If actual
  usage exceeds the confirmed estimate the run stops (`confirmed_estimate_exceeded`); nothing restarts automatically.
- Seam for TASK-055: `processing.steps.ProcessingStep` (owns the page loop, reports each page through a checkpoint) and
  `PageProvider`. Only `StubProvider`/`StubStep` exist: no classification, no label-driven extraction, no live call.
- OCR is absent (D8); every run records route `model`. PF-4 and PF-5 remain open (TASK-055/060).
- Scope limits: only PDFs are processable; the 500-page upload limit (IN-7) means the range path is normally a
  defence in depth (`processing_max_pages` is lowered in tests to exercise it).

## 5. Scope

- **IN:** stage definitions and gates, the processing-run contract (estimate, confirm, state, cancel), document
  classification and label proposal, the OCR benchmark and route rule, per-wellbore data exposure, identity merge
  proposals and review, the start gate, the unlocated-origin marker.
- **OUT:** reconstruction run internals, review/publication UI, 3D scene and charts, automatic merging, automatic
  paid retries, any default that bypasses data-quality validation.
- **Dependencies:** extraction harness (TASK-036/041), identity resolver (TASK-046), time series (TASK-047), UI shell
  (TASK-034), overview (TASK-048), budget ledger (FL-003).

## 6. Open Scope Tensions

- Whether the OCR route will ever win: it is an optimization to prove (D2), not a committed deliverable. If the benchmark
  fails, stage 2 is model-only.
- PDF-versus-text duplicate sources (for example the Compass PDF and its text export) have no precedence mechanism yet
  (TASK-059).
- Budget: settled by D7 (USD 5 total for development testing).
- OCR: settled by D8 (deferred to TASK-060).

## 7. Failure conditions

Over-cap documents, missing budget, provider failure, malformed model output, a label contradicting content, two
wellbores with the same alias, a (0, 0) origin leaking into a georeferenced result, and a confirmed estimate exceeded by
actual usage (the run stops and reports; no automatic restart).

## 8. Implementation evidence: TASK-056 (PF-6, PF-8)

Read-only, no migration. `GET /api/v1/projects/{id}/identity/exposure` (all wells/wellbores with categories and gate),
`GET .../identity/start-gate` and the extended `GET .../identity/wellbores/{id}/evidence` (new `exposure` field) return
`contracts/exposure.py` DTOs; code in `backend/fieldlens/exposure/` (`rules.py` pure, `service.py` queries). Tests:
`backend/tests/identity/test_wellbore_exposure.py` (`test_wellbore_data_exposure`, `test_reconstruction_start_gate`, `test_unstated_survey_status_passes_with_warning`).

- Categories: trajectory, surface_location, logs, production, equipment_completion, perforations, other (unknown kinds
  land in `other`). Groups are per document run and record kind with exact counts and a bounded sample whose attributes
  carry locators; proposals are listed apart and `is_accepted_fact` only for accepted+valid candidates.
- "Validated trajectory" (native records are `unreviewed` by design, so it is rule-based): a current succeeded/partial
  run linked to the wellbore with >= 2 stations, each with finite in-range MD/inclination/azimuth and no invalid or
  conflicting state, strictly increasing MD, no error issue blocking geometry/calculation on the trajectory, and a
  status that is not explicitly `planned` and not conflicting. Owner decision (November 1): real Statoil exports state no
  plan/actual status in content and file names never decide it, so an **unstated** status passes the condition with the
  per-wellbore warning `SURVEY_STATUS_UNSTATED` ("plan/as-built not stated by source"). Only an explicit `planned` status
  (`TRAJECTORY_PLANNED_ONLY`) or conflicting explicit statuses (`TRAJECTORY_STATUS_CONFLICTING`) fail it; as-built is
  then required. Planned and as-built sets stay separate. Formats with no status concept are `not_applicable`.
- Surface location: `well_surface_location` record (TASK-051 profile; absent kinds yield no records) with easting+northing
  or latitude+longitude. Missing/incomplete gives warning `SURFACE_LOCATION_MISSING`/`_INCOMPLETE` and `unlocated: true`;
  never a blocker. The local display origin is TASK-058.
- Real-record check (opt-in `local_data`, `backend/tests/identity/test_local_data_exposure.py`): the Volve F-12 and F-5 ACTUAL
  Statoil exports through the real upload/extraction/identity path give `survey_status` `unstated` (passes with
  `SURVEY_STATUS_UNSTATED`) and a sourced `well_surface_location` (`located`, no unlocated flag); no key mismatch. The
  exports name the well only as `F-12`/`F-5`, so identity resolves them only beside a block-qualified source (here the
  perforation table); alone they are unresolved and the gate says `NO_WELLBORE_IDENTIFIED`.
