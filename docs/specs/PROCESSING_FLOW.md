# Specification: Staged processing flow from upload to reconstruction start

> **Spec type:** Product/feature + API contract.
> **Load-bearing frameworks:** outcome, acceptance, scope.
> **Supporting:** failure conditions, ambiguity audit.
> **Date:** 2026-11-01. **Author:** orchestrator. **Decision owner:** owner.
> **Status:** Draft (owner decisions of November 1 recorded; not implementation approval).
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
| PF-7 | Behavioral | Merge proposals carry both identities, alias evidence quotes and a guard result; accept/reject is persisted; a proposal violating a deterministic guard cannot be accepted | 3 | `test_identity_merge_proposals` |
| PF-8 | Behavioral | "Start reconstruction" is disabled with the exact unmet condition until D4 holds; a missing surface location adds a warning and the local origin, never a block | 3 | `test_reconstruction_start_gate` |
| PF-9 | Negative | A wellbore on the local origin is excluded from cross-well distance, terrain alignment and closest-approach results, and the exclusion is stated | 3 | `test_unlocated_origin_excluded` |
| PF-10 | Failure | Provider failure, refusal, truncation, cancellation and budget stop leave the document in an explicit, retryable state; interrupted work never shows as processed | 3 | `test_processing_failure_states` |

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
- Per-project budget cap for stage 2 and 4: proposed as the remaining Meta development budget shown in the estimate
  `[Assumed: verify]`; no per-project number was set.

## 7. Failure conditions

Over-cap documents, missing budget, provider failure, malformed model output, a label contradicting content, two
wellbores with the same alias, a (0, 0) origin leaking into a georeferenced result, and a confirmed estimate exceeded by
actual usage (the run stops and reports; no automatic restart).
