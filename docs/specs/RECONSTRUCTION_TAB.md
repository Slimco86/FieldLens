# Specification: Slim Sources tab and a Reconstruction tab listing wellbores with per-wellbore processing

> **Spec type:** Product/feature (UI restructure).
> **Date:** 2026-11-01. **Author:** orchestrator. **Decision owner:** owner.
> **Status:** Approved by the owner's 22:29 message (requirements below are his words condensed); items marked `[Assumed]` need his confirmation at the browser checkpoint.
> **Backlog ID:** FL-016 / TASK-063 (UI), TASK-064 (source_missing). **Integration version:** pending.
> **Supersedes:** the Overview and pipeline panel placement from TASK-048 (0.27.0) and TASK-053 (0.30.0) in the Sources tab.

## 1. Outcome Statement

The Sources tab is back to what the owner needs for uploading and inspecting files. A Reconstruction tab shows
the wellbores the system identified, ready ones first and highlighted, with the files behind each one and a way to
start processing for one wellbore or for all ready wellbores. Verification: browser walk-through on the seeded
Volve subset (F-12, F-5, F-14), plus vitest per behaviour.

## 2. Scope

### IN scope

**Sources tab (contents, in order; nothing else):**
1. Project header with metadata and "Edit project details" (unchanged).
2. Sources / Reconstruction / Explore tabs (unchanged).
3. Upload section (unchanged).
4. Source revision (unchanged).
5. Revision files table (unchanged), including per-file "Re-run extraction" in the expanded row.
The Overview (TASK-048) section and the pipeline panel (TASK-053) are removed from the Sources tab. Their code may
be reused in the Reconstruction tab, not duplicated.

**Reconstruction tab (replaces the "not available" placeholder when a source revision exists):**
- One list of identified wells and wellbores (well and wellbore combined, as in the owner's screenshot of
  "Well 15/9-F-12 / Wellbore 15/9-F-12 / Wellbore 15/9-F-12 PILOT", merged with the per-wellbore exposure table).
- Ordering: wellbores that are **ready to process** first, as colour-highlighted rows (never colour only: also a
  text badge "Ready"); then the rest, each with the server's reason it is not ready (gate codes, unchanged).
- Columns: Wellbore (with well and a "block not stated" badge where `BLOCK_NOT_STATED`), Readiness, Records per
  category (counts), **Sources** (the files that carry that wellbore's data per category, with the first locator,
  linking to the file in Sources), Action. The "Present" and "Validation" columns are removed. Gaps, conflicts and
  findings stay available in an expandable detail row, not inline by default.
- Action: a per-row "Process" button on ready wellbores, and a "Process all ready wellbores" button above the list.
  [Assumed] Processing means the existing estimate -> separate confirm flow (0.26.0 runs, stub provider, USD 5
  total cap) over the documents that carry the selected wellbores' data that still need processing; the estimate and
  budget are shown before any confirm; the confirm stays a separate explicit step. Label-driven model extraction
  (TASK-055) and reconstruction itself are not built; the UI says what the run does today (stub) and never reports
  it as reconstruction.
- Readiness is the server's start gate per wellbore (`/identity/start-gate`), never computed in the browser.
- Keep the existing async states, keyboard access, no colour-only status, stale-project dropping.

### OUT of scope

Merge-proposal review UI (separate task, still needed), OCR, label-driven extraction, the Explore tab, any new backend
contract unless a real gap is found (report it, do not invent).

## 3. Acceptance Criteria

| ID | Type | Criterion | Test |
|---|---|---|---|
| AC-1 | Behavioral | Sources tab shows only items 1-5 above; no Overview and no pipeline panel; file table and re-run unchanged | vitest + browser |
| AC-2 | Behavioral | Reconstruction tab lists every wellbore from the identity/exposure/start-gate APIs, ready first, highlighted with a text badge | vitest + browser |
| AC-3 | Behavioral | "Sources" column lists the real files per wellbore with first locator and links to the file row | vitest + browser vs API |
| AC-4 | Negative | No "Present" or "Validation" column; detail (gaps/conflicts/findings) only in the expanded row | vitest |
| AC-5 | Behavioral | Per-wellbore Process and Process all ready run the estimate, then a separate confirm; double click sends one request | vitest + browser |
| AC-6 | Negative | A non-ready wellbore has no enabled Process action and shows the server reason; stale-project answers are dropped | vitest |
| AC-7 | Edge | Empty project, failing endpoint, truncated lists show honest states with request id and retry | vitest |

## 4. Context and Decisions

- Decisions: owner's 22:29 requirements; D9 (block-less labels are separate wellbores until merged); D7 (USD 5 cap).
- Dependencies (all merged in 0.31.0): processing runs (0.26.0), exposure and start gate (0.28.0), merge proposals API
  (0.29.0), pipeline components in `frontend/src/features/pipeline/` and overview in `frontend/src/features/overview/`.
- Delegation: frontend agent, own worktree and branch. Independent QA with a real browser pass.

## 5. Failure behaviour and open decisions

- `[Assumed]` what "Process" does today (above). Confirm at the browser checkpoint; reconstruction proper follows
  TASK-055 and the reconstruction spec.
- Wellbores that are only candidates for a merge (e.g. `F-12` and `15/9-F-12`) are listed as separate rows until a
  merge is accepted; the merge review UI is a separate task.
