# Specification: Per-wellbore reconstruction run, replacing the stub document processing in the UI

> **Spec type:** Product/feature (backend run lifecycle + UI start).
> **Date:** 2026-11-01. **Author:** orchestrator. **Decision owner:** owner.
> **Status:** Draft from the owner's 23:44 feedback; stage list and the live-model stage need his review at the
> browser checkpoint. Items marked `[Assumed]` are not confirmed.
> **Backlog ID:** FL-016 / TASK-066 (PDF extraction failure), TASK-067 (table, remove document pane),
> TASK-068 (reconstruction run API), TASK-069 (start buttons and run detail UI).
> **Supersedes:** the "Process" meaning assumed in `RECONSTRUCTION_TAB.md` (stub estimate/confirm) and the
> "Document processing" pane of TASK-053 in the UI. Extends `ASSET_RECONSTRUCTION.md` and `PROCESSING_FLOW.md`.

## 1. Outcome Statement

The owner's words: *reconstruction is the agentic process of data aggregation and asset generation for one specific
wellbore, resulting in the final 3D + chart digital twin visualization.* A ready wellbore in the Reconstruction tab
has an active **Reconstruct** button (and there is **Reconstruct all ready wellbores**). Starting it shows an
estimate, then an explicit confirm, then a persisted run with honest per-stage state. The user never sees a document
marked "Processed" unless data was actually extracted from it. The "Document processing" pane is removed from the UI:
document-level work (including label-driven extraction of PDFs that no native parser reads) is a stage inside the
wellbore reconstruction, not a separate user task. Per-file "Re-run extraction" in the Sources tab stays.

## 2. Scope

### IN scope (first slice)

A **reconstruction run** is per wellbore (a bulk start creates one run per ready wellbore, sequential, bounded
concurrency) and persists its state across restarts. Stages, each with its own state, counts, usage and error:

| Stage | Kind | Content |
|---|---|---|
| S1 Gather | deterministic | The wellbore's exposure (records per category, sources), start-gate result, documents in scope, unresolved identity candidates; fails fast when the gate no longer holds |
| S2 Extract | agent, label-driven | For each in-scope document without a native parse (e.g. completion PDFs): user label wins, else triage; extraction through the label's agent step on the TASK-036 harness; output is candidates, never facts; pages capped at 500; stub provider by default |
| S3 Identify | agent + deterministic | Merge proposals for this wellbore (TASK-057 guards); proposals are only proposed, never auto-accepted |
| S4 Assemble | deterministic | Draft configuration from validated records and accepted candidates: coverage per category, unresolved list, conflicts and warnings. No publication |

Until an agent step exists for a stage (S2 before TASK-055, S3 live), the stage is reported `not_available` with the
reason, not `succeeded`. The run summary states exactly what ran, what was skipped, cost and what remains unresolved.
Publication, the published 3D scene and the charts consume a reviewed model and belong to later tasks
(TASK-026, TASK-010 and chart tasks); this slice does not claim them.

- Spend: estimate before any run; separate confirm; one total USD 5 cap shared with all development spend (D7);
  stub provider by default; a live model call only with an explicit server-side flag and a recorded orchestrator
  authorization. Cancel, retry, interruption and provider failure persist and never read as success.
- Idempotency: starting while a run for the same wellbore and source revision is queued/running returns that run.
- Table (UI): the "Records per category" column is removed; the count moves into the Sources column so each
  category appears once: `Trajectory - 645 records` then its files, each with its own count and first locator.
  The Action column offers **Reconstruct** on ready rows; **Reconstruct all ready wellbores** sits above the list.
- UI: the "Document processing" pane, its states and the stub run list are removed. The stub step stays in the backend
  for compatibility but the UI never labels its output "Processed".

### OUT of scope

OCR (TASK-060), the review/publish UI (TASK-026), the 3D scene and charts, merge-review UI (TASK-065), live-quality
claims for S2 until TASK-055's own checks.

## 3. Acceptance Criteria

| ID | Type | Criterion | Test |
|---|---|---|---|
| RR-1 | Behavioral | `POST` estimate then separate confirm creates one persisted run per ready wellbore with S1..S4 stage rows; not-ready or stale-gate wellbores are rejected with the server reason | pytest on PostgreSQL |
| RR-2 | Behavioral | S1 and S4 produce deterministic output from existing exposure/gate data; the draft shows coverage and unresolved items per category with evidence references; no value without a source | pytest + fixtures |
| RR-3 | Negative | A stage without an agent step is `not_available`, never `succeeded`; the run is `partial`, not `succeeded`, when a stage is unavailable | pytest |
| RR-4 | Edge | Cancel, restart interruption, provider failure and duplicate start keep consistent state; a duplicate start returns the active run | pytest |
| RR-5 | Non-behavioral | No live call by default; cost estimate and usage recorded; USD 5 total cap enforced across runs; page cap 500 | pytest |
| RR-6 | Behavioral | Reconstruction tab: Reconstruct per ready wellbore and Reconstruct all ready show estimate, separate confirm, per-stage progress; double click sends one request | vitest + browser |
| RR-7 | Behavioral | One category heading per category in the Sources column with its record count; no separate records column; Document processing pane absent | vitest + browser |
| RR-8 | Negative | The UI never shows a document as "Processed" from a stub run; stub and not-available stages are labelled | vitest |
| RR-9 | Behavioral | A fresh completion PDF upload either parses/extracts or reports an honest, specific reason; never `source_missing` while storage reads hash-verified (TASK-066) | pytest + real-file browser check |

## 4. Context and Decisions

- Owner feedback 23:44: new PDFs still fail ("source_missing" with Stored hash-verified); records belong with the
  source categories; "Nothing to process" must become a start action; the Document processing pane contradicts the
  status (stub "Processed", no data, no credit use) and is not wanted; reconstruction is the agentic aggregation.
- Evidence from the owner's screenshot: the message lacks the 0.31.1 wording ("re-upload this file"), so the running
  backend may predate 0.31.1, but a fresh upload failing the same way means the per-checkout storage-root hypothesis
  of TASK-064 is not sufficient; TASK-066 diagnoses against the real file and the real runtime (read-only).
- Reuse: run engine and cost/budget code of TASK-054, exposure and gate of TASK-056, proposals of TASK-057, harness of
  TASK-036/041. Contracts flow Pydantic -> registry -> OpenAPI -> generated.ts.
- Delegation: backend agent (TASK-068), frontend agent (TASK-067, TASK-069), backend/ingestion (TASK-066); one
  writer per worktree; independent QA per feature.

## 5. Failure behaviour and open decisions

- `[Assumed]` stage list S1..S4 and that a stage without an agent step reports `not_available` (the run `partial`).
- `[Assumed]` bulk start runs wellbores sequentially with at most two concurrent; one estimate covers the bulk.
- Open: whether the user must confirm per wellbore or once for the bulk (default: once, showing the per-wellbore split).
- Open: when S2 is live, which documents count as in scope for a wellbore whose files carry several wellbores.

## Amendment (proposed, 2026-11-02): stage redesign

Draft; awaiting owner review. The stage list becomes S1 Collect sources, S2 Read documents (TASK-055 model read),
S3 Match wellbores (TASK-057 merge, grouping all files of one wellbore), S4 Assemble data, S5 Design 3D asset
(`VisualAssetSpec`). The modal explains each stage and shows informational cost only (no remaining budget, per
TASK-075). See [WELLBORE_ASSET_GENERATION](WELLBORE_ASSET_GENERATION.md) sections 3 and 5; it supersedes the
"stage list S1..S4" assumption above once approved.
