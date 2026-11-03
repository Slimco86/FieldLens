# FieldLens backlog

Main-agent-owned, persistent work ledger (reformatted October 30 as a machine-checkable
ledger; pre-conversion text last updated 2026-10-28).
See [workflow](DEVELOPMENT_WORKFLOW.md) for gates and
[project scope](PROJECT_SPEC.md) for mandatory requirements.

**This file is now the ledger source** ([tracking spec](specs/TRACKING.md), section 4.1): the
`## Features` and `## Tasks` blocks below are parsed by `scripts/track.py` and later mirrored to
Taiga. The [execution plan](../plan/architecture-fieldlens-1.md) task table remains the
design-time DAG; its TASK rows were copied here, and this file is authoritative for status,
priority, dates and assignment from now on. All earlier narrative lives unchanged under
`## Journal`; history stays out of item blocks.

## Legend

- **Status:** `proposed`, `specifying`, `ready`, `in_progress`, `testing`,
  `integration_pending`, `done`, `blocked`, `cancelled`. `done` requires `Version` and real
  `Evidence`; a `done` item may only depend on `done` items (the sole exception is the
  owner-approved pair TASK-003 -> TASK-001, listed in `DONE_WITH_OPEN_DEPS` in `ledger.py`).
- **Priority:** `P0` (first persisted UI, early agent risk, reconstruction, acceptance/release),
  `P1` (required enrichment and tooling), `P2` (optional).
- **Tags** (fixed vocabulary, lowercase kebab-case): `foundation`, `ingestion`, `backend`,
  `frontend`, `3d`, `charts`, `rag`, `geospatial`, `qa`, `infra`, `data`, `docs`, `agent`,
  `release`.
- **Assignee:** `owner`, `agent:<profile>` (a [custom profile](../.github/agents/README.md)
  such as `agent:fieldlens-backend`) or `unassigned`. **Due:** `YYYY-MM-DD` inside the
  Hackathon sprint (2026-10-29..2026-11-04; deadline Nov 4 21:00 EST); done items carry their
  integration date (earlier dates are allowed for done items only). Due dates and priorities are
  the orchestrator's proposal from the dependency order: first UI Oct 31, early agent risk
  Nov 1, reconstruction Nov 2, enrichment Nov 3, acceptance/release Nov 4.
  A dependency's due date must not be later than the item's own, and a non-done item must not
  depend on a non-done item of lower priority (P0 > P1 > P2; BK-1 addition, raise the
  dependency instead).
- **Parent / Slice** (tasks only): Parent is the feature ID; Slice is the original plan slice
  (for example `FL-004-A`).

## How to edit

Change only the field table and the three bold labels (`Outcome.`, `Next action.`,
`Evidence.`, one to four sentences each) of an item; use exactly the field names above, one
value per row, `Depends on` as `none` or comma-separated IDs. Put dated narrative, handoff
records and verification detail in the Journal, not in item blocks. Then run:

```text
uv run python scripts/track.py check      # exits non-zero and lists violations with line numbers
uv run python scripts/track.py list --status in_progress --tag backend
uv run python scripts/track.py plan       # summary; Taiga sync arrives with FL-020-C
```

## Features

### FL-000 · Perforation requirements and versioned parallel-development governance

| Field | Value |
|---|---|
| Type | feature |
| Status | done |
| Priority | P1 |
| Tags | docs |
| Depends on | none |
| Assignee | owner |
| Due | 2026-10-27 |
| Sprint | Hackathon |
| Spec | none |
| Version | 0.1.0 |

**Outcome.** Adopted perforation requirements and the versioned parallel-development governance baseline.
**Next action.** None; implementation of the documented product features is tracked separately.
**Evidence.** Integrated by owner in `e8b156a`, version 0.1.0; verification record in the Journal.

### FL-001 · Custom development-agent roles, serial branch delegation and resource boundaries

| Field | Value |
|---|---|
| Type | feature |
| Status | in_progress |
| Priority | P0 |
| Tags | agent |
| Depends on | FL-000 |
| Assignee | owner |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/DEVELOPMENT_AGENTS.md |
| Version | none |

**Outcome.** Agree custom development-agent roles, serial branch delegation and resource boundaries. Profiles are defined; actual host activation and tool verification remain required per assignment.
**Next action.** Verify profile, model and tools per assignment; remaining profiles still require activation and no blanket host fix is claimed. The CLI ignores YAML effort, so worker effort is selected explicitly, and the owner accepts main Astra/high for this continuation.
**Evidence.** TASK-025 backend native editing smoke passes and the host resolves Sonnet 5.5; see the Journal for the activation record.

### FL-002 · Demo dataset qualification: hashes, rights and independent gold fixtures for F-12, F-14 and F-5

| Field | Value |
|---|---|
| Type | feature |
| Status | in_progress |
| Priority | P0 |
| Tags | data, ingestion |
| Depends on | none |
| Assignee | owner |
| Due | 2026-11-01 |
| Sprint | Hackathon |
| Spec | specs/DATA_FEASIBILITY.md |
| Version | none |

**Outcome.** Qualify the real demo dataset for the owner-selected F-12/F-14/F-5 cohort: which files, their hashes and rights, and human-checked reference records (including dated perforation/state evidence) that parsers, reconstruction and the final demo are tested against. This is test ground truth, not an upload feature and not a limit on what users can upload. The owner accepted the generic/unlocated F-12 limitation.
**Next action.** Final hashed profiles, windows and reference/state/rights fixtures remain in TASK-002; the full-manifest ingestion check is TASK-029. G1 is not passed. FL-005 no longer depends on this feature (owner decision October 30); each early parser subset records its own fixtures. No automatic F-11 B replacement or further tally-search blocker.
**Evidence.** Owner selection and the data-feasibility spec; see the Journal data-audit sections.

### FL-003 · Meta entitlement/protocol verification and shared budget controls

| Field | Value |
|---|---|
| Type | feature |
| Status | in_progress |
| Priority | P0 |
| Tags | rag, backend |
| Depends on | FL-004 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-01 |
| Sprint | Hackathon |
| Spec | specs/META_INTEGRATION.md |
| Version | none |

**Outcome.** Verify Meta entitlement/protocols and agree shared budget controls. The offline adapter and ledger come first, then a separate opt-in live smoke.
**Next action.** TASK-004 (offline adapter) is integrated in 0.13.0; next TASK-005 (live smoke, only after the approved USD 1 ceiling). No G1 dependency.
**Evidence.** none yet

### FL-004 · Runnable stack, database/migrations and common identity/evidence/time contracts

| Field | Value |
|---|---|
| Type | feature |
| Status | done |
| Priority | P0 |
| Tags | foundation, backend, frontend, infra |
| Depends on | FL-014 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-28 |
| Sprint | Hackathon |
| Spec | specs/FOUNDATION.md |
| Version | 0.4.0 |

**Outcome.** Established the runnable stack, database/migrations and common identity/evidence/time contracts. The owner approved a one-time direct-verification exception for this foundation.
**Next action.** None; later features use independently verified acceptance.
**Evidence.** Tested repair `95da2b7` integrated into master at `1293f55`, version 0.4.0; 124 backend, 4 UI and 3 CLI E2E tests plus quality gates pass. [Direct-repair evidence](specs/FOUNDATION.md#direct-repair-verification-october-28).

### FL-005 · Upload project sources into traceable, persistent, restart-safe source revisions

| Field | Value |
|---|---|
| Type | feature |
| Status | in_progress |
| Priority | P0 |
| Tags | ingestion, backend, frontend |
| Depends on | FL-004 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | none |

**Outcome.** Upload project sources into traceable, persistent, restart-safe source revisions. TASK-006 upload/storage/jobs/source UI is done and independently accepted (IN-1/3/4/5/7, except the 500-page PDF and parse-time XML/ZIP checks deferred to TASK-009).
**Next action.** Native profiles/evidence (TASK-009), source removal/replacement (TASK-039), scanned/Word profiles (TASK-030) and final manifest acceptance (TASK-029) remain. Upload and parsing are the first priority (owner, October 30), ahead of the UI redesign.
**Evidence.** TASK-006 integrated as `fb275f4`, version 0.8.0.

### FL-006 · Published-model trajectories with evidence and deterministic closest approach

| Field | Value |
|---|---|
| Type | feature |
| Status | in_progress |
| Priority | P0 |
| Tags | geospatial, 3d, backend |
| Depends on | FL-005, FL-016 |
| Assignee | agent:fieldlens-geospatial |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/TRAJECTORY_VIEWER.md |
| Version | none |

**Outcome.** Inspect published-model trajectories with evidence and deterministic closest approach. The TASK-007 analytic engine is done and independently accepted (TR-1/2/3).
**Next action.** The reconstructed model scene (TASK-010, TR-4..7) remains.
**Evidence.** TASK-007 integrated as `532d517`, version 0.6.0.

### FL-007 · Equipment reconstruction with catalog/generic fallbacks and source-aware placement

| Field | Value |
|---|---|
| Type | feature |
| Status | specifying |
| Priority | P0 |
| Tags | 3d, geospatial |
| Depends on | FL-006 |
| Assignee | agent:fieldlens-3d-motion |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/EQUIPMENT_RECONSTRUCTION.md |
| Version | none |

**Outcome.** Reconstruct equipment with catalog/generic fallbacks and source-aware placement. The first slice is procedural installed-evidence equipment; optional Blender work comes later.
**Next action.** DF-9 is still required before the procedural slice (TASK-012); TASK-024 (Blender) is optional and never blocks release.
**Evidence.** none yet

### FL-008 · Dated perforation intervals, state transitions and total/open perforated length

| Field | Value |
|---|---|
| Type | feature |
| Status | in_progress |
| Priority | P0 |
| Tags | geospatial, frontend |
| Depends on | FL-005, FL-006 |
| Assignee | agent:fieldlens-geospatial |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/PERFORATION_HISTORY.md |
| Version | none |

**Outcome.** Inspect dated perforation intervals, state transitions and total/open perforated length. The TASK-008 engine is done and independently accepted (PH-2/3/5/7/9, engine-level PH-6).
**Next action.** PH-6 persistence, PH-1/4/8 and real event/scene integration (TASK-013) remain.
**Evidence.** TASK-008 integrated as `aaf0fdd`, version 0.7.0.

### FL-009 · Aligned terrain/bathymetry and reservoir/formation context

| Field | Value |
|---|---|
| Type | feature |
| Status | specifying |
| Priority | P0 |
| Tags | geospatial, 3d |
| Depends on | FL-006 |
| Assignee | agent:fieldlens-geospatial |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/CONTEXT_LAYERS.md |
| Version | none |

**Outcome.** Display aligned terrain/bathymetry and reservoir/formation context. Seabed and formation slices are independent and both mandatory.
**Next action.** Dispatch TASK-014 (seabed) and TASK-015 (formations) after their prerequisites.
**Evidence.** none yet

### FL-010 · Production and depth logs linked to asset/time selection and perforation overlays

| Field | Value |
|---|---|
| Type | feature |
| Status | specifying |
| Priority | P0 |
| Tags | charts, frontend |
| Depends on | FL-005, FL-016, FL-008 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/LINKED_CHARTS.md |
| Version | none |

**Outcome.** Link production and depth logs to asset/time selection and perforation overlays. Production/log views need model context, not finished 3D; overlays follow the perforation history.
**Next action.** Dispatch TASK-016 and TASK-017 after TASK-009/026, then TASK-018 for the overlays.
**Evidence.** none yet

### FL-011 · Early source chat, then evidence-backed model/graph/tool exploration

| Field | Value |
|---|---|
| Type | feature |
| Status | specifying |
| Priority | P0 |
| Tags | rag, frontend |
| Depends on | FL-003, FL-005, FL-006, FL-007, FL-008, FL-010, FL-016 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/RETRIEVAL_ASSISTANT.md |
| Version | none |

**Outcome.** Deliver early source chat, then evidence-backed model/graph/tool exploration. TASK-011/019/027 source chat precedes reconstruction and 3D.
**Next action.** Full domain tools (TASK-031) and the 32-case live evaluation (TASK-020) follow the early source chat.
**Evidence.** none yet

### FL-012 · Fresh-upload to scene/history, charts and cited-answer demo verified end to end

| Field | Value |
|---|---|
| Type | feature |
| Status | specifying |
| Priority | P0 |
| Tags | qa, release |
| Depends on | FL-002, FL-009, FL-011 |
| Assignee | agent:fieldlens-qa |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/DEMO_ACCEPTANCE.md |
| Version | none |

**Outcome.** Verify the complete fresh-upload, scene/history, charts and cited-answer demo. Offline combined checks come first, then real/live verification, then the authorized release and recording.
**Next action.** Run TASK-021, TASK-022 and TASK-023 in order once their prerequisites are done.
**Evidence.** none yet

### FL-013 · Offline Blender equipment-authoring skill and export handoff

| Field | Value |
|---|---|
| Type | feature |
| Status | done |
| Priority | P2 |
| Tags | 3d, docs |
| Depends on | none |
| Assignee | owner |
| Due | 2026-10-27 |
| Sprint | Hackathon |
| Spec | ../.github/skills/fieldlens-blender-assets/SKILL.md |
| Version | 0.3.0 |

**Outcome.** Curated an offline Blender equipment-authoring skill and export handoff. This is skill and workflow only; installation and asset creation are deferred.
**Next action.** None for FL-013; pin Blender and run real export checks only in a separately approved asset task (TASK-024).
**Evidence.** Integrated by owner in `88b177e`, version 0.3.0.

### FL-014 · Project-centric architecture, primary reconstruction agent and UI-verifiable orchestration plan

| Field | Value |
|---|---|
| Type | feature |
| Status | done |
| Priority | P0 |
| Tags | docs |
| Depends on | none |
| Assignee | owner |
| Due | 2026-10-28 |
| Sprint | Hackathon |
| Spec | ARCHITECTURE.md |
| Version | 0.3.3 |

**Outcome.** Finalized the project-centric architecture, primary reconstruction agent and UI-verifiable orchestration plan. The owner authorized first-packet implementation on October 28.
**Next action.** None; document checks only, no application verification implied.
**Evidence.** Owner integrated the 32-task DAG, specifications and first packets in `9d630e3`, version 0.3.3; checks recorded in the Journal.

### FL-015 · Isolated projects with categorized, incremental sources

| Field | Value |
|---|---|
| Type | feature |
| Status | done |
| Priority | P0 |
| Tags | backend, frontend |
| Depends on | FL-004 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-29 |
| Sprint | Hackathon |
| Spec | specs/PROJECT_WORKSPACE.md |
| Version | 0.8.0 |

**Outcome.** Create/reopen isolated projects with categorized, incremental sources. TASK-025 delivered lifecycle/isolation/navigation and TASK-006 the upload-related criteria (PW-3/4/7).
**Next action.** None. PW-6 (published model stays pinned while newer sources are pending/failed) needs a published model and moves, by owner decision October 30, into the TASK-026 acceptance; it is not verified by this closure.
**Evidence.** Independently accepted repair `2af22aa` integrated at `3e748d9`, version 0.5.0; see [PW evidence](specs/PROJECT_WORKSPACE.md#task-025-scoped-implementation-and-acceptance). TASK-006 (`fb275f4`, 0.8.0).

### FL-016 · Composite entities/relationships/configurations with evidence and reviewed model publication

| Field | Value |
|---|---|
| Type | feature |
| Status | specifying |
| Priority | P0 |
| Tags | rag, backend, frontend |
| Depends on | FL-004 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/ASSET_RECONSTRUCTION.md |
| Version | none |

**Outcome.** Reconstruct composite entities, relationships and configurations with evidence and reviewed model publication. The review policy is confirmed.
**Next action.** TASK-026 consumes early chat (TASK-019) and TASK-032 issues, not full FL-011; gold fixtures and the live allowance remain separate gates (TASK-028).
**Evidence.** none yet

### FL-017 · Source-linked warnings/errors and the exact effect of missing/conflicting data

| Field | Value |
|---|---|
| Type | feature |
| Status | specifying |
| Priority | P0 |
| Tags | frontend, backend, data |
| Depends on | FL-004, FL-005 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/DATA_QUALITY.md |
| Version | none |

**Outcome.** Inspect source-linked warnings and errors and the exact effect of missing or conflicting data. TASK-032 is the source-first issue inspector; there is no manual override/fact editor or new telemetry service.
**Next action.** FL-016/FL-007 wire publication and generic boundaries; TASK-022 verifies all DQ criteria.
**Evidence.** none yet

### FL-018 · Single Compose project and one root .env loaded automatically by code

| Field | Value |
|---|---|
| Type | feature |
| Status | done |
| Priority | P1 |
| Tags | infra |
| Depends on | FL-004 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-28 |
| Sprint | Hackathon |
| Spec | specs/DEV_ENVIRONMENT.md |
| Version | 0.5.1 |

**Outcome.** Replaced per-lane `db.env`/override files with a single Compose project and one root `.env` loaded automatically by code. Fresh `fieldlens`/`fieldlens_app` names are used and old volumes are untouched.
**Next action.** Follow-ups: validate hand-edited password charset, name `scripts/init_env.py` in the readiness message, anchor `frontend_dist`.
**Evidence.** Owner-approved October 28; implementation `2bc4129`, independent QA PASS AC-1..8 (219 backend, 15 UI, 9 E2E); version 0.5.1.

### FL-019 · One-command local stack ./dev (Postgres, migrations, API, optional Vite, tests, lane-aware)

| Field | Value |
|---|---|
| Type | feature |
| Status | done |
| Priority | P1 |
| Tags | infra |
| Depends on | FL-018 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-29 |
| Sprint | Hackathon |
| Spec | specs/DEV_TOOLING.md |
| Version | 0.10.0 |

**Outcome.** One-command local stack `./dev` (Postgres, migrations, API, optional Vite, tests, lane-aware). Limits: lane Vite proxies to 8101 and `./dev test e2e` is fixed to 8101.
**Next action.** None.
**Evidence.** Owner-approved October 29; version 0.10.0 (`feature/fl-019-a-dev-script`), independent QA PASS after 3 rounds, 450 backend tests.

### FL-020 · Telegram notifications, machine-checkable backlog ledger and one-way Taiga sync

| Field | Value |
|---|---|
| Type | feature |
| Status | done |
| Priority | P1 |
| Tags | infra, docs |
| Depends on | FL-018 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-29 |
| Sprint | Hackathon |
| Spec | specs/TRACKING.md |
| Version | 0.12.0 |

**Outcome.** Telegram notifications, a machine-checkable backlog ledger and one-way Taiga sync (sprint `Hackathon`); owner-approved October 29. Slices A (notify.py, 0.9.0), B (ledger and `track.py check`, 0.11.0) and C (Taiga sync, 0.12.0) are integrated.
**Next action.** Run `track.py sync --apply` after every backlog edit. Open follow-ups: owner accepted the public Taiga project (`TAIGA_ALLOW_PUBLIC=1`); a dedicated bot is advised before enabling the Telegram inbox; live `is_blocked=true` and 429/5xx paths were verified on fakes only.
**Evidence.** Slice A on `feature/fl-020-a-notify`: independent QA PASS after 2 repairs, 396 backend tests, version 0.9.0. Slice B: independent QA PASS after 1 repair, 517 tests, 0.11.0. Slice C: independent QA PASS after 1 repair incl. live 8-item smoke with zero-write rerun, 536 tests, 0.12.0.

### FL-021 · Demo-grade application shell and visual design system

| Field | Value |
|---|---|
| Type | feature |
| Status | ready |
| Priority | P0 |
| Tags | frontend |
| Depends on | FL-004 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/UI_DESIGN_SYSTEM.md |
| Version | none |

**Outcome.** Replace the unstyled prototype pages with a designed, structured, accessible light-theme product UI for the demo, built on Mantine: a left sidebar for project management; per-project top tabs Sources (file management), Reconstruction (log of agentic parsing, extraction and relationships) and Explore (3D model, charts, assistant, with tree/stage/inspector/dock regions); shared components and states; redesigned Projects and Sources screens. Large screens only. Later features mount into the shell instead of restyling it.
**Next action.** Owner approved the spec October 30 (TASK-033). Sequenced after upload and parsing (TASK-009, TASK-039); then TASK-034 builds the shell and TASK-037 polishes the integrated app.
**Evidence.** Spec approved with owner decisions recorded (specs/UI_DESIGN_SYSTEM.md section 6). Implementation not started; the current UI is 136 lines of default-styled CSS with no layout or design structure.

### FL-022 · Agent-assisted extraction of ambiguous source content with deterministic validation

| Field | Value |
|---|---|
| Type | feature |
| Status | in_progress |
| Priority | P0 |
| Tags | ingestion, rag, backend |
| Depends on | FL-003, FL-005 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/AGENTIC_EXTRACTION.md |
| Version | none |

**Outcome.** Where deterministic native parsers cannot answer a specific question (ambiguous tables, free-text reports, scanned or legacy-Word content, unclear units or identities), the harness lets the model, using allowlisted read-only content tools and page images, propose typed, source-located candidate claims that deterministic validators accept, reject or flag. Each work unit leaves an activity log shown in the Reconstruction tab. Deterministic extraction stays first; a model proposal is never an accepted fact and never overrides a parsed value.
**Next action.** Owner approved the spec October 30 (TASK-035). Order: TASK-038 (activity log backend), then TASK-036 (extraction) after TASK-004, TASK-009 and TASK-011; TASK-040 (Reconstruction view) after the shell. Stub provider only, no live spend.
**Evidence.** Spec approved with owner decisions recorded (specs/AGENTIC_EXTRACTION.md section 6). Implementation not started; added by the owner's October 30 realignment (no existing task covered model judgement in extraction).

### FL-023 · Wellbore identity grouping and agent-generated visual 3D asset (single and field view)

| Field | Value |
|---|---|
| Type | feature |
| Status | in_progress |
| Priority | P0 |
| Tags | rag, backend, frontend, 3d |
| Depends on | FL-022 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/WELLBORE_ASSET_GENERATION.md |
| Version | none |

**Outcome.** The reconstruction agent merges differently named sources of one wellbore into one file group, then designs a declarative, validated visual asset (trajectory plus plausible assembly, labelled illustrative) rendered in single-wellbore and multi-wellbore (field) 3D views. Plots, history, formations and reservoir are a later feature.
**Next action.** Approved 2026-11-02; lanes TASK-075/076/077 start in parallel worktrees.
**Evidence.** none yet; planning only (2026-11-02).

## Tasks

Rows copied from the plan's task table (the plan stays the design-time DAG); `Parent` strips
the slice letter and `Slice` keeps the plan's original string.

### TASK-001 · Verify host model/effort/tools for each profile used (DA-7) and record the integration base

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | agent, docs |
| Depends on | none |
| Assignee | agent:fieldlens-orchestrator |
| Due | 2026-10-30 |
| Sprint | Hackathon |
| Spec | specs/DEVELOPMENT_AGENTS.md |
| Version | 0.12.1 |
| Parent | FL-001 |
| Slice | FL-001 |

**Outcome.** The main agent verifies DA-7 actual host model/effort/tools for each profile used, confirms the approved design is committed and records the exact integration base before implementation delegation. Closed by the owner on October 30: profile verification is performed and recorded per assignment at dispatch, not as one up-front sweep.
**Next action.** None. Every dispatch still needs its own fresh preflight (profile, resolved model, effort, tools) recorded in its handoff; a profile with no recorded preflight is not trusted.
**Evidence.** Owner decision October 30 (waiver of the up-front all-profile sweep). Preflights recorded for the backend profile (resolved Sonnet 5.5 in host events; native create/edit/read/delete worked, TASK-025 preflights); foundation integrated at `1293f55` (0.4.0); current integrated version 0.12.1.

### TASK-002 · Demo dataset manifest and independent reference (gold) fixtures for F-12/F-14/F-5 (DF-1..9)

| Field | Value |
|---|---|
| Type | task |
| Status | in_progress |
| Priority | P0 |
| Tags | data, ingestion |
| Depends on | none |
| Assignee | owner |
| Due | 2026-11-01 |
| Sprint | Hackathon |
| Spec | specs/DATA_FEASIBILITY.md |
| Version | none |
| Parent | FL-002 |
| Slice | FL-002 |

**Outcome.** Produce the ignored `data/volve/demo-manifest.json` for F-12/F-14/F-5: the exact source files with hashes and rights, the parser profile each needs, the date/depth windows, and the expected records with independent, human-checked reference/state fixtures (DF-1..9). It is ground truth for TASK-029 and TASK-022, not an upload step. Use the verified F-5 images and F-14 drawing and preserve F-12's approved generic limitation; no bulk download, automatic F-11 B substitution or false G1 pass.
**Next action.** Continue main-agent bounded source work or a separately verified ingestion assignment; it blocks only TASK-029/022, not parsers (TASK-009 records its own subset fixtures). Tally search is not a prerequisite.
**Evidence.** Partial source audits only; see the Journal data sections and the data-feasibility spec. G1 is not passed.

### TASK-003 · Foundation: contracts, persistence, migrations, root locks and app shell

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | foundation, backend, frontend |
| Depends on | TASK-001 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-28 |
| Sprint | Hackathon |
| Spec | specs/FOUNDATION.md |
| Version | 0.4.0 |
| Parent | FL-004 |
| Slice | FL-004-A |

**Outcome.** Backend owner implements FN-1..6 and SC-1..6 in contracts/persistence/migrations, root locks and the frontend app/API shell, with real PostgreSQL, loopback readiness and test commands and a single shared-contract writer.
**Next action.** None.
**Evidence.** Integrated at `1293f55`, version 0.4.0, under the owner's direct-repair/verification exception.

### TASK-025 · Project lifecycle and membership (PW-1/2/5/8)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, frontend |
| Depends on | TASK-003 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-28 |
| Sprint | Hackathon |
| Spec | specs/PROJECT_WORKSPACE.md |
| Version | 0.5.0 |
| Parent | FL-015 |
| Slice | FL-015-A |

**Outcome.** Backend owner implements project lifecycle/membership in backend/fieldlens/projects and frontend/src/features/projects: PW-1/2/5/8 with keyboard navigation and real persistence.
**Next action.** None; the upload-related PW criteria were delivered by TASK-006.
**Evidence.** Independent QA; integrated at `3e748d9`, version 0.5.0 (lifecycle surfaces only).

### TASK-006 · Project upload, storage, jobs and source list UI (IN-1/3/4/5/7, PW-3/4/6/7)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, backend, frontend |
| Depends on | TASK-025 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-29 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | 0.8.0 |
| Parent | FL-005 |
| Slice | FL-005-A |

**Outcome.** Backend owner implements project upload/jobs/source list in ingestion/jobs/evidence and the frontend upload: IN-1/3/4/5/7 and PW-3/4/6/7. Stored, unsupported and pending extraction are labelled explicitly and no asset model is published.
**Next action.** None; native profiles and evidence follow in TASK-009.
**Evidence.** Independent QA; UI `fb275f4`, merged as version 0.8.0.

### TASK-004 · Offline provider adapter, budget reservations and failure/cancellation behavior (MI-1..5)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | rag, backend |
| Depends on | TASK-003 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/META_INTEGRATION.md |
| Version | 0.13.0 |
| Parent | FL-003 |
| Slice | FL-003-A |

**Outcome.** RAG worker implements the MI-1..5 offline provider adapter, PostgreSQL budget reservations and finite failure/cancellation behavior in `backend/fieldlens/assistant/`; no live calls.
**Next action.** None. TASK-005 (live smoke, MI-6) is the next FL-003 slice; the single provider key variable is `MODEL_API_KEY` (owner decision October 30). Its image-input check and the token-bound comparison belong there.
**Evidence.** Integrated October 30 as version 0.13.0 (merge of `feature/task-004-provider-adapter`, head `d52c895`). Independent QA (`fieldlens-qa`) found D1-D6, all repaired and re-verified; final gates: 621 backend tests passed (1 unrelated skip), ruff, mypy; frontend gates verified at `b61106a`. Offline only: the Meta client was never called, so MI-6 and real billing/token bounds are unverified.

### TASK-005 · Live Meta protocol/entitlement smoke under the USD 1 ceiling (MI-6)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | rag, backend |
| Depends on | TASK-004 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/META_INTEGRATION.md |
| Version | 0.14.1 |
| Parent | FL-003 |
| Slice | FL-003-B |

**Outcome.** RAG worker runs MI-6 only after the approved USD 1 ceiling and balance/key readiness, recording the actual entitlement and tool protocol, including a harmless image-input (multimodal) check because FL-022 relies on page images. No pilot documents are needed.
**Next action.** None. Adapter follow-ups from the live findings are TASK-043; the page-size image check and real-document reading are TASK-042. The owner still needs to read the real balance change in the Meta dashboard (two live runs happened, see evidence note).
**Evidence.** Live MI-6 smoke run October 31 on `muse-spark-1.3` (Responses protocol; text, tool round trip with reasoning replay, in-flight cancel, synthetic image input, error result; `/embeddings` returns 404, so local embeddings stand). Integrated as 0.14.1 (branch `feature/task-005-live-meta-smoke`, head `e9518c6`). Independent QA: all gates and isolation, secret and evidence audits passed (681 passed, 1 skipped, 1 deselected); fail-closed refusal re-verified with the key removed. Placeholder-rate upper bound about USD 0.42 across the original and an accidental QA re-run of the live test (ledger cap USD 1.00); real rates and balance unknown. See docs/evidence/MI6_LIVE_SMOKE.md.

### TASK-009 · Native source profiles and evidence UI for the qualified subset (IN-2/6)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, backend, frontend |
| Depends on | TASK-006 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | 0.14.0 |
| Parent | FL-005 |
| Slice | FL-005-B |

**Outcome.** Ingestion owner implements selected qualified native source profiles and the evidence UI: IN-2/6 for this subset, exact record/page coverage and the wrong-folder fixture. This is a small approved subset, not full IN-8/G1 acceptance.
**Next action.** None. Follow-ups: owner decided October 31 that production/completion equipment is the target and drilling-side assemblies are not needed, so the completion-PDF work is TASK-030, TASK-042 and TASK-041 (completion string, packers and tubing are not extracted for any wellbore; the F-14 RKB-MSL 53.870 vs 54.90 DQ-3 conflict can only appear from the completion schematic); owner confirmation of units/datum for the perforation and pick tables (the Wells README states none, so depths stay `unsupported`); a vitest for the evidence panel's null-status polling. Approved subset (October 30): WITSML tubular/BHA/bore geometry (PV-25..33), LAS (PV-15/19/22), production workbook (PV-01), perforation table (PV-03), picks (PV-04), three survey PDFs (PV-10/16/20), mirrored F-5 trajectory XML. Deferred: EDM export (PV-24), grids (PV-07..09), large completion PDFs/plots, OCR (TASK-030).
**Evidence.** Integrated October 30 as version 0.14.0 (merge of `feature/task-009-native-profiles`, head `1df81f7`, migration `0005_native_profiles`). Independent QA (`fieldlens-qa`) returned the first candidate for a report-endpoint 500 on real perforation/production files plus nine further findings; all repaired and re-verified on the real subset (all 18 real files build a report; 677 backend tests, ruff, mypy, frontend gates, and the Playwright evidence spec on a lane port). Real coverage (trajectory stations / production days / perforation intervals / drilling-assembly and casing-point records): F-12 211/3056/5/14, F-14 93/3056/6/9, F-5 97/3306/5/6. The owner's two-of-three requirement is met for trajectories, production and perforation history; equipment is drilling-side only. Offline parsing, no model calls.
(Update October 31, 0.18.0: the perforation and pick depths are no longer `unsupported`; they default to meters (MD) with a warning, see TASK-046.)

### TASK-032 · Source-first issue inspector API and UI (DQ-1/2/3/4/7, DTO-negative DQ-5/6)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | frontend, backend, data |
| Depends on | TASK-009, TASK-034 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-01 |
| Sprint | Hackathon |
| Spec | specs/DATA_QUALITY.md |
| Version | none |
| Parent | FL-017 |
| Slice | FL-017-A |

**Outcome.** Frontend owner implements the scoped issue API/list/detail/evidence navigation in `backend/fieldlens/evidence/issues.py` and `frontend/src/features/evidence/quality/`: DQ-1/2/3/4/7 and DTO-negative DQ-5/6, using the shared shell and status components. Shared schema/client edits are serialized; source-first, with no graph or 3D prerequisite.
**Next action.** Dispatch after TASK-009 and TASK-034 are integrated.
**Evidence.** none yet

### TASK-011 · Project/source-scoped exact, text and vector retrieval

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | rag, backend |
| Depends on | TASK-009 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/RETRIEVAL_ASSISTANT.md |
| Version | 0.17.0 |
| Parent | FL-011 |
| Slice | FL-011-A |

**Outcome.** RAG owner implements project/source-scoped exact/text/vector retrieval in retrieval, source coverage and bounded evidence search; unresolved observations are labeled. No accepted asset graph is a prerequisite, and the embedding gate/degradation is explicit.
**Next action.** None. One-off setup for vector search: `uv run python scripts/fetch_embedding_model.py` (hash-pinned public model into `.local`); without it search runs in an explicit degraded mode (exact + full text). Follow-ups are in TASK-045.
**Evidence.** Integrated October 31 as 0.17.0 (branch `feature/task-011-source-retrieval`, head `78a88da`, migration `0007_source_retrieval`, dependency `fastembed`). Four independent QA rounds: no cross-project or eligibility leak in any round; defects found and repaired: 32-55 s cold first search (stale planner statistics; ANALYZE policy), HTTP 500 on NUL in the query, wrong `hybrid` label on invalid query vectors, no relevance signal (now `weak_evidence`), missing stemming, well-log chunks unreachable, nonexistent sidetrack suffix resolving to the parent, lone frequent words making hits strong, parent query returning sidetrack rows, a flaky ranking test. Real local embedder (int8 bge-small, MIT): about 146-195 ms per chunk, peak RSS about 780 MiB; numeric production/trajectory tables are excluded from vectors by owner policy (311 chunks embedded, 16,351 excluded on the approved subset; 18,006 chunks fully indexed in about 70-140 s). Relevance floor 0.68, margin 0.04, 20% frequency rule and 50-chunk threshold are uncalibrated. Synthetic gold only proves mechanics; no real-data recall claim (needs the G1 gold cases).

### TASK-019 · Source-context chat and evidence UI (RG-8 offline, applicable RG-3/4/5)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | rag, frontend |
| Depends on | TASK-004, TASK-011, TASK-034 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-01 |
| Sprint | Hackathon |
| Spec | specs/RETRIEVAL_ASSISTANT.md |
| Version | none |
| Parent | FL-011 |
| Slice | FL-011-B |

**Outcome.** RAG owner implements the source-context chat/evidence UI in the shell's assistant dock and evidence slots, RG-8 offline and applicable RG-3/4/5; no geometry tools or reconstruction writes from chat.
**Next action.** Dispatch after TASK-004, TASK-011 and TASK-034 are integrated.
**Evidence.** none yet

### TASK-027 · Early live source-chat verification (three cases, USD 1 allowance)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | rag, qa |
| Depends on | TASK-005, TASK-019 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-01 |
| Sprint | Hackathon |
| Spec | specs/RETRIEVAL_ASSISTANT.md |
| Version | none |
| Parent | FL-011 |
| Slice | FL-011-D |

**Outcome.** RAG owner verifies all three early live source-chat cases under a separately approved allowance of at most USD 1 and records exact citation, gap and refusal results. This is not the complete RG-6 evaluation.
**Next action.** Requires TASK-005 and TASK-019 plus a separate live-call authorization.
**Evidence.** none yet

### TASK-030 · Scanned-PDF and legacy-Word embedded-image profiles for selected evidence

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, data |
| Depends on | TASK-009 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | 0.16.3 |
| Parent | FL-005 |
| Slice | FL-005-C |

**Outcome.** (Owner decision October 31: an OCR text layer with page/box locators comes first for scanned pages, so quoted values can be verified against source text; the model then reads page images and a value is accepted only when the OCR token and the image read agree.) Ingestion owner qualifies scanned-PDF and legacy-Word embedded-image profiles for selected F-14/F-5 evidence, with original locators, a safe evidence viewer and human-checked attribute fixtures. Required for selected equipment, not optional OCR polish.
**Next action.** None. Owner decision October 31: OCR (phase B) is dropped for the demo; completion equipment is read directly from page images at a visual level (TASK-036/TASK-041). Page rendering with pypdfium2 moves into TASK-036; the OCR evaluation stays as evidence.
**Evidence.** Phase A merged as 0.16.3 (docs/evidence/TASK030_OCR_EVALUATION.md): offline OCR/rendering evaluation, agreement-rule analysis, `.doc` structure check and phase B design; independent QA passed with findings, corrected. Phase B (OCR implementation) intentionally not built.

### TASK-026 · Reconstruction proposals, validator and review UI (RC-1..9, DQ-6)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | rag, backend, frontend |
| Depends on | TASK-019, TASK-032, TASK-036, TASK-038, TASK-040 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/ASSET_RECONSTRUCTION.md |
| Version | none |
| Parent | FL-016 |
| Slice | FL-016-A |

**Outcome.** RAG owner implements reconstruction proposals, the validator and the review UI in reconstruction and the shared assistant harness: RC-1..9 offline, DQ-6 publication boundaries, real database transactions and source-backed fixtures. The issue inspector is reused, migrations are coordinated with backend and The model does not generate accepted facts. PW-6 (the published model stays pinned and labeled with its source revision while newer sources are pending/failed; moved from FL-015 by the owner October 30) is part of this task's acceptance.
**Next action.** Dispatch after TASK-019, TASK-032 and TASK-036 are integrated.
**Evidence.** none yet

### TASK-028 · Live reconstruction check on 12 gold cases (RC-10, USD 3 allowance)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | rag, qa |
| Depends on | TASK-005, TASK-026, TASK-030 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/ASSET_RECONSTRUCTION.md |
| Version | none |
| Parent | FL-016 |
| Slice | FL-016-B |

**Outcome.** RAG owner runs RC-10 on 12 independently authored gold cases and selected qualified source records under a separately approved allowance of at most USD 3, recording actual tool-dependent reconstruction, support and unresolved states.
**Next action.** Requires TASK-005, TASK-026 and TASK-030 plus a separate live-call authorization.
**Evidence.** none yet

### TASK-007 · Analytic trajectory/reference/proximity engine (TR-1/2/3)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P1 |
| Tags | geospatial, backend |
| Depends on | TASK-003 |
| Assignee | agent:fieldlens-geospatial |
| Due | 2026-10-29 |
| Sprint | Hackathon |
| Spec | specs/TRAJECTORY_VIEWER.md |
| Version | 0.6.0 |
| Parent | FL-006 |
| Slice | FL-006-A |

**Outcome.** Geospatial owner implements the TR-1/2/3 analytic trajectory/reference/proximity engine and unit tests in engineering; no renderer or pilot acceptance is claimed.
**Next action.** None; the scene (TR-4..7) is TASK-010.
**Evidence.** Independent QA; `532d517`, version 0.6.0 (TR-1/2/3 only).

### TASK-008 · Deterministic perforation state/union engine (PH-2/3/5/6/7/9)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P1 |
| Tags | geospatial, backend |
| Depends on | TASK-003 |
| Assignee | agent:fieldlens-geospatial |
| Due | 2026-10-29 |
| Sprint | Hackathon |
| Spec | specs/PERFORATION_HISTORY.md |
| Version | 0.7.0 |
| Parent | FL-008 |
| Slice | FL-008-A |

**Outcome.** Geospatial owner implements the PH-2/3/5/6/7/9 deterministic state/union engine with exact t0..t6 fixtures, unknown baselines and same-day ambiguity.
**Next action.** None; PH-6 persistence is deferred to later work (TASK-013).
**Evidence.** Independent QA; `aaf0fdd`, version 0.7.0 (engine-level; PH-6 persistence deferred).

### TASK-010 · Published-model scene/tree, local-origin buffers and evidence selection (TR-4..7)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | 3d, frontend |
| Depends on | TASK-007, TASK-026, TASK-034 |
| Assignee | agent:fieldlens-3d-motion |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/TRAJECTORY_VIEWER.md |
| Version | none |
| Parent | FL-006 |
| Slice | FL-006-B |

**Outcome.** 3D owner implements the published-model scene/tree, local-origin buffers and evidence selection, TR-4..7 on the qualified survey subset, mounted in the shell's stage and tree slots. Active facts are never read directly from upload staging.
**Next action.** Dispatch after TASK-026 and TASK-034 are integrated.
**Evidence.** none yet

### TASK-012 · Source-dimensioned procedural equipment, inspector and generic/unlocated states (EQ-1..7, DQ-5)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | 3d, frontend |
| Depends on | TASK-010, TASK-030 |
| Assignee | agent:fieldlens-3d-motion |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/EQUIPMENT_RECONSTRUCTION.md |
| Version | none |
| Parent | FL-007 |
| Slice | FL-007-A |

**Outcome.** 3D worker implements source-dimensioned procedural equipment, the inspector and catalog/generic/unlocated states and EQ-1..7/DQ-5 from qualified evidence. It demonstrates F-14/F-5 dimensional candidates and F-12's explicit limitation; no guessed depth, generated engineering values or Blender prerequisite.
**Next action.** Dispatch after TASK-010 and TASK-030 are integrated.
**Evidence.** none yet

### TASK-013 · Historical perforation state wired to real events, MD placement and time controls (PH-1/4/8)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | frontend, geospatial |
| Depends on | TASK-008, TASK-009, TASK-010 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/PERFORATION_HISTORY.md |
| Version | none |
| Parent | FL-008 |
| Slice | FL-008-B |

**Outcome.** Frontend worker wires canonical historical state to real events, MD placement/time controls/inspector and PH-1/4/8, retaining acquisition dates and context guards.
**Next action.** Dispatch after TASK-009 and TASK-010 are integrated.
**Evidence.** none yet

### TASK-014 · Seabed source projection, typed layer API and component (CX-1/3/4/5)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | geospatial, 3d |
| Depends on | TASK-009, TASK-010 |
| Assignee | agent:fieldlens-geospatial |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/CONTEXT_LAYERS.md |
| Version | none |
| Parent | FL-009 |
| Slice | FL-009-A |

**Outcome.** Geospatial worker implements seabed source projection, the typed layer API/component and CX-1/3/4/5, owning the seabed-specific files.
**Next action.** Dispatch after TASK-009 and TASK-010 are integrated.
**Evidence.** none yet

### TASK-015 · Formation depth horizons/picks, interpolation and source masks (CX-2/3/4/5)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | geospatial, 3d |
| Depends on | TASK-009, TASK-010 |
| Assignee | agent:fieldlens-geospatial |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/CONTEXT_LAYERS.md |
| Version | none |
| Parent | FL-009 |
| Slice | FL-009-B |

**Outcome.** Geospatial worker implements formation depth horizons/picks, interpolation/source masks and CX-2/3/4/5; the combined CX-6 is verified after both layers integrate.
**Next action.** Dispatch after TASK-009 and TASK-010 are integrated.
**Evidence.** none yet

### TASK-016 · Production endpoints, chart, units, periods and evidence (CH-1/3/4/6)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | charts, frontend |
| Depends on | TASK-009, TASK-034, TASK-047 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/LINKED_CHARTS.md |
| Version | none |
| Parent | FL-010 |
| Slice | FL-010-A |

**Outcome.** Frontend worker implements production endpoints/chart/units/periods/evidence with CH-1/3/4/6 on project source records, scoped by source well/wellbore identifiers and labeled unreconciled until a published model exists (owner decoupled this from reconstruction October 30). Model linking is wired in TASK-018/031; owns the production-specific files.
**Next action.** Dispatch after TASK-009 and TASK-034 are integrated.
**Evidence.** none yet

### TASK-017 · Depth-log endpoints, tracks, nulls and acquisition evidence (CH-2/3/4/6)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | charts, frontend |
| Depends on | TASK-009, TASK-034, TASK-047 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/LINKED_CHARTS.md |
| Version | none |
| Parent | FL-010 |
| Slice | FL-010-B |

**Outcome.** Frontend worker implements depth-log endpoints/tracks/nulls/acquisition evidence with CH-2/3/4/6 on project source records, scoped by source well/wellbore identifiers and labeled unreconciled until a published model exists (owner decoupled this from reconstruction October 30). Model linking is wired in TASK-018/031; owns the log-specific files.
**Next action.** Dispatch after TASK-009 and TASK-034 are integrated.
**Evidence.** none yet

### TASK-018 · Perforation overlays and shared as-of state across both chart families (CH-5/7)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | charts, frontend |
| Depends on | TASK-013, TASK-016, TASK-017 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/LINKED_CHARTS.md |
| Version | none |
| Parent | FL-010 |
| Slice | FL-010-C |

**Outcome.** Frontend worker integrates PH overlays and shared as-of state with CH-5/7 across both chart families and tests rapid context changes.
**Next action.** Dispatch after TASK-013, TASK-016 and TASK-017 are integrated.
**Evidence.** none yet

### TASK-031 · Published-graph retrieval, domain/navigation tools and full assistant (RG-1..5/7)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | rag, frontend |
| Depends on | TASK-019, TASK-012, TASK-013, TASK-014, TASK-015, TASK-018 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/RETRIEVAL_ASSISTANT.md |
| Version | none |
| Parent | FL-011 |
| Slice | FL-011-E |

**Outcome.** RAG owner extends the existing chat with published-graph retrieval, all domain/navigation tools and RG-1..5/7; the UI acknowledges applied, rejected and stale actions. The same harness and ledger are used, with no second agent backend.
**Next action.** Dispatch after all six prerequisites are integrated.
**Evidence.** none yet

### TASK-029 · Final-manifest verification of IN-8 and real-source DQ-8 inputs

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | ingestion, qa, data |
| Depends on | TASK-002, TASK-009, TASK-030 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | none |
| Parent | FL-005 |
| Slice | FL-005-D |

**Outcome.** Ingestion owner verifies IN-8 and real-source DQ-8 inputs across the final approved manifest, including expected conflicts and generic gaps as explicit outcomes. Required profiles and independent records must match; accepted limitations are not fabricated success or full coverage.
**Next action.** Dispatch after TASK-002, TASK-009 and TASK-030 are done.
**Evidence.** none yet

### TASK-020 · Fixed 32-case live gold evaluation (RG-6) under the USD 3 allowance

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | rag, qa |
| Depends on | TASK-005, TASK-029, TASK-031 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/RETRIEVAL_ASSISTANT.md |
| Version | none |
| Parent | FL-011 |
| Slice | FL-011-C |

**Outcome.** RAG worker runs the fixed 32-case live gold evaluation under the approved USD 3 allowance, recording RG-6 and authorized equipment-research coverage, not just successful text generation.
**Next action.** Requires TASK-005, TASK-029 and TASK-031 plus a separate live-call authorization.
**Evidence.** none yet

### TASK-021 · Combined browser verification with a stub provider (AC-9/RSS)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | qa, release |
| Depends on | TASK-031, TASK-037 |
| Assignee | agent:fieldlens-qa |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/DEMO_ACCEPTANCE.md |
| Version | none |
| Parent | FL-012 |
| Slice | FL-012-A |

**Outcome.** QA verifies the combined create-project, upload, reconstruction review/publication, scene/history/charts browser path with the stub provider, negative paths/accessibility and AC-9/RSS. Feature owners fix defects.
**Next action.** Dispatch after TASK-031 and TASK-037 are integrated.
**Evidence.** none yet

### TASK-022 · Real-source/live-provider verification of all project ACs and DQ-1..8

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | qa, release |
| Depends on | TASK-002, TASK-020, TASK-021, TASK-027, TASK-028, TASK-029 |
| Assignee | agent:fieldlens-qa |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/DEMO_ACCEPTANCE.md |
| Version | none |
| Parent | FL-012 |
| Slice | FL-012-B |

**Outcome.** QA verifies the real-source/live-provider path, all 12 project ACs and DQ-1..8 on the candidate SHA, showing F-12's generic/unlocated state and real conflicts, with isolated database/storage and actual usage/evidence.
**Next action.** Dispatch after all six prerequisites are done.
**Evidence.** none yet

### TASK-023 · Operator instructions, rights-safe release inventory, release candidate and recording

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | release, docs |
| Depends on | TASK-022 |
| Assignee | owner |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/DEMO_ACCEPTANCE.md |
| Version | none |
| Parent | FL-012 |
| Slice | FL-012-C |

**Outcome.** Main agent finalizes operator instructions, the rights-safe release inventory, VERSION/CHANGELOG and the candidate; the owner verifies G4, records a video of at most 180 s and explicitly authorizes publication/submission.
**Next action.** Starts after TASK-022; the owner decides publication.
**Evidence.** none yet

### TASK-024 · Optional Blender-authored source-backed asset (GLB, scale/IDs/budgets)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P2 |
| Tags | 3d |
| Depends on | TASK-012 |
| Assignee | agent:fieldlens-3d-motion |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/EQUIPMENT_RECONSTRUCTION.md |
| Version | none |
| Parent | FL-007 |
| Slice | FL-007-B |

**Outcome.** 3D worker uses the approved Blender build/skill to create one source-backed asset and verify scale/IDs/GLB/budgets from the equipment spec. Optional: skip rather than delay required features, and make no claim of a completed asset when skipped.
**Next action.** Needs explicit asset/setup approval after TASK-012; never blocks required release.
**Evidence.** none yet

### TASK-033 · Approve the UI design direction and open design decisions

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend, docs |
| Depends on | none |
| Assignee | owner |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/UI_DESIGN_SYSTEM.md |
| Version | 0.12.1 |
| Parent | FL-021 |
| Slice | FL-021-A |

**Outcome.** Owner reviews the draft UI design spec and decides the open questions (theme, palette/accent, typography and icon sources, density, layout regions, new dev dependencies) so implementation does not guess. Output is the approved spec revision.
**Next action.** None. The orchestrator-chosen component kit (Mantine) and the brand ramp are reviewed at the first browser checkpoint after TASK-034.
**Evidence.** Owner decisions of October 30 recorded in `specs/UI_DESIGN_SYSTEM.md` section 6: light theme, conservative vivid brand color, Inter, lucide-react, component kit delegated to the orchestrator (Mantine), left project sidebar with Sources/Reconstruction/Explore tabs, large screens only.

### TASK-034 · Design tokens, application shell and redesigned Projects/Sources screens (UI-1..7, UI-9..12)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend |
| Depends on | TASK-033 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-01 |
| Sprint | Hackathon |
| Spec | specs/UI_DESIGN_SYSTEM.md |
| Version | 0.21.0 |
| Parent | FL-021 |
| Slice | FL-021-A |

**Outcome.** Frontend owner implements the approved light theme on Mantine (with Inter and lucide-react), the shell (left project sidebar, per-project Sources/Reconstruction/Explore tabs, Explore tree/stage/inspector/dock slots), shared components/states and restyled Projects and Sources/upload views (including the already-supported classification edit; the remove/replace and project-delete controls are TASK-049) and the evidence views built by TASK-009, with existing behavior, tests and accessibility preserved. Measures the bundle and sets the UI-8 budget. No new product behavior and no fake controls.
**Next action.** None. Owner browser checkpoint (look, brand ramp) pending. Follow-ups: records catch-up polling has no cap/backoff and shows no notice for a partly filled list, records become readable while the document is still `running` (non-atomic publish), `transitionDuration` is 0 (no animation), below 1600 px unreviewed, the evidence-class chip reads 'Model-read, unverified' for every `model_proposal` candidate, including rule-validated ones (wording to decide), an out-of-contract evidence class can blank the inspection panel. TASK-048 (overview) and TASK-049 (remove/replace/delete controls) follow.
**Evidence.** Integrated November 1 as 0.21.0 (branch `feature/task-034-ui-shell`, head `b8621f0`; frontend only, no API or contract change). Mantine 9.7.4, Inter 5.3.0, lucide 1.66.0, dev-only axe-core 4.14.0. Integrated polish 0.21.1 (head `37e16f3`: candidates section restyled with the design kit, reviewer score 4.5/5, vitest 129, Playwright 29/29 twice). Independent QA returned the first candidate twice (long project/file names broke the sidebar and files table, job panel contradicted the live table, then a squeezed revisions table and two flaky e2e tests, one of which exposed a real stale-records bug); repaired and re-verified: vitest 122 passed, full Playwright 28/28 in three consecutive runs, lint/typecheck/contracts/build clean, initial JS 163.04 kB gzip (ceiling 250), zero external requests, axe zero violations on home and Sources, reviewer UI-10 score 4/5. UP-1 stale assertion updated (authorized). Screenshots are local only.

### TASK-035 · Approve the agentic extraction contract and open decisions

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, rag, docs |
| Depends on | none |
| Assignee | owner |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/AGENTIC_EXTRACTION.md |
| Version | 0.12.1 |
| Parent | FL-022 |
| Slice | FL-022-A |

**Outcome.** Owner reviews the draft extraction contract and decides the open questions (which ambiguity classes are in scope, acceptance policy, live-credit allowance) before any implementation.
**Next action.** None. Superseded October 30 (second answer): a model-extracted coordinate/trajectory value may serve as a labeled backup when no deterministic source exists (AX-11).
**Evidence.** Owner decisions of October 30 recorded in `specs/AGENTIC_EXTRACTION.md` section 6: question-driven model use, validators-only acceptance, deterministic coordinates/trajectories, one shared-contract change allowed, no live spend in TASK-036, all documents shareable (read-only content tools and multimodal input allowed).

### TASK-036 · Model-proposed extraction candidates with deterministic validation and review (AX-1..9, AX-12..15)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, rag, backend |
| Depends on | TASK-035, TASK-004, TASK-009, TASK-011, TASK-038, TASK-046 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-11-01 |
| Sprint | Hackathon |
| Spec | specs/AGENTIC_EXTRACTION.md |
| Version | 0.20.0 |
| Parent | FL-022 |
| Slice | FL-022-A |

**Outcome.** Ingestion owner implements question-driven candidate-claim proposals from the harness through the offline provider adapter, the allowlisted read-only content tools (span, table, page image, project search), deterministic validators, persisted candidate/accept/reject/flag states with source locators (including the AX-11 labeled coordinate fallback), writing to the TASK-038 activity log, and their display in the existing evidence/issue views (restyled later by TASK-034). One shared-contract change is allowed with a single writer. Offline stub provider only; no live spend is authorized by this task.
**Next action.** None. TASK-041 builds on it. Follow-ups (TASK-045 and TASK-041 hardening): a unit written away from its value is ignored (`15/9-F-99 Set 3000 MD ft` with claimed `m` is accepted as meters), page_read item-to-depth association, a page that names another well should override the page-1 cover rule, block-qualified well vs another block, `95/8` parsed as a fraction, glued `3000ft` over-rejected, strict JSON fence handling, no pdfium render timeout, AX-11 (coordinate fallback) deferred, image-only orientation check opt-in.
**Evidence.** Integrated November 1 as 0.20.0 (branch `feature/task-036-extraction-harness`, head `ce0200a`; migration `0010_extraction_candidates`). Offline stub provider only: no live call, no spend; stub results do not show live extraction quality. Independent QA returned the first candidate (validators accepted a value that was only a substring of the quote, ignored the unit in the quote, mis-parsed fractions/Unicode minus/decimal comma, did not check the subject against the source, skipped parsed-conflict checks, left a reservation open after a settle failure); repaired with committed tests and re-verified (backend 1061 passed, 6 skipped, 1 deselected; ruff, mypy, frontend gates clean). Measured on this host: page render at 1600 px cold median 133 ms (max 327 ms), cached about 0.015 ms; triage compute under 80 ms; stub end-to-end 12 pages 0.95 s. Real-PDF checks (`-m local_data`) cover triage and render only.

### TASK-037 · Demo UI polish and responsive/accessibility sweep on the integrated app (UI-8, UI-10)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | frontend, release |
| Depends on | TASK-034, TASK-012, TASK-018 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/UI_DESIGN_SYSTEM.md |
| Version | none |
| Parent | FL-021 |
| Slice | FL-021-B |

**Outcome.** Frontend owner runs a visual and interaction polish pass over the integrated app (consistency, empty/error/loading states, viewport behavior, motion, contrast, offline asset loading) at the demo viewports, with screenshot evidence reviewed by someone other than the implementer. No new features.
**Next action.** Dispatch after TASK-034, TASK-012 and TASK-018 are integrated; owner sign-off on the demo look is the final gate.
**Evidence.** none yet

### TASK-038 · Agent activity log persistence and API (AX-10 backend)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, rag, backend |
| Depends on | TASK-004 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/AGENTIC_EXTRACTION.md |
| Version | 0.15.0 |
| Parent | FL-022 |
| Slice | FL-022-B |

**Outcome.** Ingestion owner implements the persisted, project-scoped agent activity log (question, ordered steps, tool-call summaries, candidates, validator outcomes, usage, stop reason; no hidden reasoning) with a read API, migration and offline fixtures. One shared-contract change with a single writer (coordinated with TASK-036). The Reconstruction tab view is TASK-040.
**Next action.** None. Deferred to TASK-036 (QA-reviewed): wire `recover_interrupted` into harness startup with a test, link `cost_usd` to the BudgetLedger reservation, own the `step_key` scheme (replay ignores content), add cancel/retry endpoints only if needed, and decide whether cross-revision evidence is required.
**Evidence.** Integrated October 31 as 0.15.0 (branch `feature/task-038-agent-activity-log`, head `6f4515d`, migration `0006_agent_activity_log`). Independent QA returned the first candidate for one medium defect (evidence locator text bypassed redaction and bounds); repaired and re-verified (709 backend tests passed, 1 skipped; ruff, mypy, frontend lint/typecheck/45 tests/contracts/build; single head). Offline persistence only, no model calls and no real-data coverage claimed.

### TASK-040 · Reconstruction tab: agent activity log view (AX-10 UI)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | frontend |
| Depends on | TASK-038, TASK-034 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/AGENTIC_EXTRACTION.md |
| Version | none |
| Parent | FL-022 |
| Slice | FL-022-C |

**Outcome.** Frontend owner implements the Reconstruction tab's logical log of agentic parsing from the TASK-038 API: units listed with state, tool-call and candidate summaries, validator outcomes, usage, and links to source locations; interrupted/failed units visibly not successful; no hidden reasoning. Uses TASK-034 components.
**Next action.** Dispatch after TASK-038 and TASK-034 are integrated; independent QA follows.
**Evidence.** none yet

### TASK-039 · Source file removal with tombstone revision, and replacement (IN-9, IN-5)

| Field | Value |
|---|---|
| Type | task |
| Status | ready |
| Priority | P0 |
| Tags | backend, ingestion |
| Depends on | TASK-009 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | none |
| Parent | FL-005 |
| Slice | FL-005-C |

**Outcome.** Backend owner implements the owner-approved removal: an API that, after confirmation semantics, physically deletes a document's stored bytes and derived content (keeping shared blobs), cancels its running job, and records a tombstone source revision; derived claims become inactive and non-citable; a published model stays pinned and labeled; re-upload creates a fresh document. Replacement uses the existing new-revision path (IN-5). Project deletion (PW-9) moved to TASK-071 on 2026-11-02 and is no longer part of this task. (Original text: the same slice adds project deletion (PW-9, owner request October 31): a typed-name-confirmed API that cancels jobs, deletes unshared blobs and every project-scoped row in one transaction through a designed delete path (the immutable-revision guards stay enabled otherwise). IN-9 and PW-9 offline tests on real PostgreSQL and storage; the UI controls are TASK-049.)
**Next action.** Ready; dispatch into the first lane that frees up (TASK-034 or TASK-036 finishing), before TASK-049. Fresh preflight in its own worktree; independent QA follows.
**Evidence.** none yet

### TASK-042 · Live feasibility spike: model reading of the real completion documents

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, rag, data |
| Depends on | TASK-005, TASK-009, TASK-043 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/AGENTIC_EXTRACTION.md |
| Version | 0.16.1 |
| Parent | FL-022 |
| Slice | FL-022-E |

**Outcome.** A bounded, read-only experiment (no product code, no persistence) that sends page images and text of the seven local completion documents (PV-11..14, 17, 18, 21 for F-12, F-14 and F-5) to the model through the TASK-004 adapter and records, against a human reading of the same pages, which production/completion equipment (tubing, casing/liners, packers, pumps, bearings, depths, dimensions) it finds, cost per page, failure modes and what the validators would reject. The result decides the TASK-041 approach before any build.
**Next action.** None. Findings feed TASK-041 and TASK-030 (see docs/evidence/TASK042_COMPLETION_SPIKE.md): upright whole pages at about 1600 px with effort `low`, orientation fix and a zoomed second pass for tiny labels, text layer for native-text pages, OCR layer with locators for the scanned F-14 and F-5 documents. Open owner decisions: OCR as a prerequisite versus a two-read agreement rule for scans, a deterministic source for F-12 completion equipment (the three F-12-folder completion reports are F-11 wells), and human verification of the agent-read reference.
**Evidence.** Live spike run October 31 on `muse-spark-1.3` over the seven approved completion PDFs: 50 settled responses, USD 2.903620 at the conservative placeholder rates (real cost about one sixth, unverified), cap USD 3.00 never exceeded, effort minimal/low/medium accepted. On 14 equipment pages scored against an agent-read reference (not human-verified): tuned best-per-page 80/83 strict, uniform `low` 68/83 strict, the gap being the rotated schematic (8/21 plain, 20/21 rotated); depth values and units exact on every matched item; no invented items on control pages; digit misreads on small print. PV-11/12/13 in the F-12 folder are F-11 wells. Integrated as 0.16.1 (branch `feature/task-042-completion-spike`, head `729147c`; scripts and evidence only). Independent QA returned the first candidate (reference page error, tuned headline), repaired offline and re-verified; scorer reproduced exactly. Live-model results, not production acceptance.

### TASK-041 · Production/completion equipment candidates from completion documents

| Field | Value |
|---|---|
| Type | task |
| Status | in_progress |
| Priority | P0 |
| Tags | ingestion, rag, backend |
| Depends on | TASK-036, TASK-042, TASK-046 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/EQUIPMENT_RECONSTRUCTION.md |
| Version | 0.22.1 |
| Parent | FL-022 |
| Slice | FL-022-D |

**Outcome.** Using the TASK-036 harness, read the completion pages of F-14 and F-5 (scanned page images, and the text layer where it exists) and propose a superficial, visual-level production/completion equipment structure (casing/liner strings, tubing, packers, pumps, perforations, isolations: type, material if printed, OD/ID/length, top/bottom depth) as model-read, unverified candidates for the 3D model. Owner decision October 31: no OCR gate, speed and performance first, missed details are acceptable, values are never used in calculations; F-12 uses generic assets.
**Next action.** Owner decision: a second live run of only the 5 failed pages (F-14 p4, p30, p36; F-5 p48, p49; worst case USD 1.25 at placeholder rates; period cap USD 3 has USD 2.32 left) to confirm the repairs and read the rotated schematic; TASK-041 stays open until that real-data result exists. Follow-ups: PDF-to-wellbore link, DB CHECK against relabelling equipment rows as accepted, lane-DB guard `dbname` override, duplicate JSON keys collapse, trailing `3000 m.` over-strict, block-qualified labels, `unit_away_from_value` over-flags some quotes.
**Evidence.** Integrated November 1 as 0.22.0 (branch `feature/task-041-equipment-candidates`, head `4bd7535`; no migration, contracts additive). Offline stub provider only; no live result exists. Independent QA: first pass PASS with follow-ups (no route to accepted found across all categories, DB CHECK, API and relabel attempts), the spend-risk item (a refused page image still called the model) was fixed and re-verified; backend 1121 passed, 7 skipped, 1 deselected; stub end-to-end for the 7 planned F-14/F-5 pages 1.31 s, render 91-150 ms per page; dry-run plan: 7 provider calls, worst-case reservation USD 1.75 at placeholder rates against a USD 3 cap. First live run November 1 (one invocation, cap USD 3, enforced cap 3.00, committed USD 0.676365 at placeholder rates, 22.5 s, 9 pages planned incl. 2 control pages): 4 pages read (F-14 p29 16 items, p35 9 items; controls p13 and p50 no items), 5 failed (p30/p36 budget stop after a tool turn, p49 truncated, p4 schema invalid, p48 malformed); 25 candidates all flagged/unverified/unattached; agreement with the agent-read reference (not human verified) is category-level on 2 pages only. Repaired offline in 0.22.1 (backend 1178 passed). Not a coverage claim.

### TASK-043 · Provider adapter hardening from the live findings (effort control, tool-token estimate, cancel and liable semantics)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | rag, backend |
| Depends on | TASK-005 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/META_INTEGRATION.md |
| Version | 0.16.0 |
| Parent | FL-003 |
| Slice | FL-003-C |

**Outcome.** Offline fixes to the TASK-004 adapter driven by docs/evidence/MI6_LIVE_SMOKE.md: a per-request `reasoning.effort` control (API accepts low and minimal; default high exhausted output budgets), a per-tool-definition/round-trip input-token overhead so the reservation bound holds (245 estimated vs 552 billed), explicit and documented in-flight cancel semantics (the response still completes and bills, so account for it), and a reconcile path for reservations left `liable` by rejected requests. Default tests stay offline; no live spend.
**Next action.** None. Live checks still open (for TASK-042): that the `reasoning.effort` payload is accepted by the real API with our payload builder, that 404/405 stay unbilled (405 by analogy), and the page-size image bound; set `effort` to `low` or `minimal` for extraction calls (no default is chosen).
**Evidence.** Integrated October 31 as 0.16.0 (branch `feature/task-043-adapter-hardening`, head `7309acb`; no migration or contract change). Independent QA returned the first candidate for two medium defects (release could erase billed attempts; 4xx non-billable generalized beyond the observed 404), repaired and re-verified (735 backend tests passed, 1 skipped, 1 deselected; ruff, mypy, single head 0005). Offline only; no live behavior verified.

### TASK-044 · Offline check of the EDM export for production/completion equipment and perforation history

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, data |
| Depends on | TASK-009 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | 0.16.2 |
| Parent | FL-005 |
| Slice | FL-005-D |

**Outcome.** A bounded, read-only, offline investigation (no model calls, no spend) of the deferred 211 MB EDM export (PV-24) and any other already-present structured source for deterministic completion/production equipment (tubing, casing/liners in service, packers, pumps, bearings, depths) and perforation history for F-12, F-14 and F-5, with exact locators; recommends a streaming profile if worthwhile. Owner decision October 31: if nothing is found it is fine, and generic 3D assets cover missing equipment as long as the rest of that wellbore's data exists.
**Next action.** None. Completion/production equipment for F-14 and F-5 comes from the scanned completion documents (TASK-030 OCR layer, then TASK-041); F-12 uses generic assets per the owner policy. Optional low-value EDM uses (identity cross-checks, labelled casing/liner design context) only after units are confirmed.
**Evidence.** Offline deterministic check October 31 of the 211 MB EDM export (PV-24; streamed in about 5 s, about 38 MB peak RSS, no model calls, no spend): a drilling/well-planning database (142 element types, 21 wells, 54 wellbores) with no installed/as-built/dated completion or perforation history for F-12, F-14 or F-5, no units and no assembly-level datum (scenario and case datum links disagree: 177.165 versus 180.118); only design-variant tubing/liner/packer for F-14 A (packer depth 8350.07 versus StressCheck PackerDepth 8678.15, a source conflict). A streaming EDM profile is not worthwhile for completion or perforation history. Integrated as 0.16.2 (branch `feature/task-044-edm-completion-check`, head `2c681d4`; scripts and evidence only). Independent QA returned the first candidate (minor factual errors) and re-verified the repair; the final wording-only commit was reviewed by the orchestrator, not re-QA'd.

### TASK-045 · Retrieval follow-ups from the TASK-011 QA rounds

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P1 |
| Tags | rag, backend |
| Depends on | TASK-011 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/RETRIEVAL_ASSISTANT.md |
| Version | none |
| Parent | FL-011 |
| Slice | FL-011-F |

**Outcome.** Small retrieval improvements deferred by QA: an id-only query (for example `F-11`) returns only the vector-ranked chunk while 1,400+ numeric-table chunks carry the identifier, with no note saying so; numeric-only well names (such as 15/9-19) are not detected as sidetracks by `_SIDETRACK`; a query with an unmatched parent id (`15/9-19`) returns sidetrack rows as ok/strong; a literal `wellbore_suffix` of "None"/"null" becomes a suffix; lowercase `f-12 a` reads as the English article; production-workbook flooding for `tubing size F-12`/`F-14 tubing` (ties above 20 candidates defeat the diversity guard); production vocabulary map and slot reservation; search notes during a partially rebuilt index; failed index jobs after exhausted attempts need a visible requeue; identity: `parse_bore_label` accepts free-text trailing words as a suffix (`F-12 well` becomes a bore `15/9-F-12 WELL`), a glued form such as `15/9-F-12A` is not parsed as a well, and the perforation MISSING_UNIT message mentions only MD while TVD/TVDSS are counted; series (TASK-047): time-formatted or wrapped LAS files (drilling time logs, two small F-5 `sig1` depth logs) store no series, no monthly production series, `series_curve` accepts `min_value` NULL with `max_value` set and `series_axis.index_max` NaN, and the CPI file keeps `las_curve` summaries named after header words.
**Next action.** Dispatch only after the owner confirms the priority; the assistant/exploration tasks (TASK-019/031) must not use `evidence_strength` as a citation gate until this is done or the calibration gold set exists.
**Evidence.** none yet

### TASK-046 · Depth unit/datum defaults and deterministic well/wellbore identity

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, backend |
| Depends on | TASK-009, TASK-011 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/DATA_COMPLETENESS.md |
| Version | 0.18.0 |
| Parent | FL-005 |
| Slice | FL-005-E |

**Outcome.** Perforation, formation-pick and similar depths without a documented unit default to meters (MD) as a warning (DC-1..3), and `well`/`wellbore` rows are created deterministically from the extracted record subjects with sidetrack distinctness, parent links and evidence counts, sharing one naming rule with retrieval (DC-4..6).
**Next action.** None. Follow-ups: free-text suffix parsing (a label such as `F-12 well` must stay unresolved, filed under TASK-045), re-resolution after source removal (TASK-039), and the documented naming-based parent links (not a drilling relationship).
**Evidence.** Integrated October 31 as 0.18.0 (branch `feature/task-046-units-identity`, head `4c298b8`, migration `0008_identity_links`). Perforation and pick depths without a unit default to meters (MD) with one MISSING_UNIT warning per file (profile versions 3; 287 perforation and 964 pick attributes on the approved subset; TWT, azimuth, coordinates, blanks and flagged picks untouched; reference gaps warn without blocking); deterministic well/wellbore identity with one label rule shared with retrieval (retrieval byte-identical on the QA sample); production-workbook H/AH bores alias to the observed base wellbore with one warning; on the real subset 19 wells and 35 wellbores, 17,136 records linked, none unresolved, F-12/F-14/F-5 each one base wellbore carrying trajectory, logs, bore/equipment records, perforations, picks and production. Independent QA passed (889 passed, 4 skipped, 1 deselected; frontend clean) with low notes. Real-data results are from the opt-in run on the approved subset only.

### TASK-047 · Time-series storage and window API for logs and production

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, ingestion, charts |
| Depends on | TASK-009, TASK-011 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-10-31 |
| Sprint | Hackathon |
| Spec | specs/DATA_COMPLETENESS.md |
| Version | 0.19.0 |
| Parent | FL-005 |
| Slice | FL-005-F |

**Outcome.** LAS curve samples and production series are stored at full resolution (not only the per-curve summary), written atomically with the extraction run, and served through a windowed, min/max-preserving downsampled API and a typed service for later chart and agent tools (DC-7..11).
**Next action.** None. Charts (TASK-016/TASK-017) read through `SeriesService.get_window` / the window API. Follow-ups are filed under TASK-045: LAS files with a time-formatted index (drilling time logs such as TIME_MWD) or wrapped rows store no series (two small F-5 `sig1` depth logs are the only depth-log gap in the cohort), monthly production series are not built (daily only), and low DB-hardening residuals (`min_value` NULL with `max_value` set, `index_max` NaN pass the CHECKs).
**Evidence.** Integrated October 31 as 0.19.0 (branch `feature/task-047-series-storage`, head `c46ed0a`; migration renumbered to `0009_series_storage` on top of `0008_identity_links`). LAS samples and daily production stored at full resolution (`series_axis`/`series_curve`, float64 arrays, NaN = missing), written atomically with the extraction run and superseded/cascade-deleted with it; read-only `/series`, `/series/{id}`, `/series/{id}/window` with deterministic min/max- and gap-preserving downsampling (10,000-point window p95 about 9 ms in the service, about 27 ms over HTTP on a 100,000-sample series) and a typed `SeriesService`. Real subset: 172 of 301 LAS files store series (970,241 samples; 67 refused by the upload inspector, the rest time-indexed, wrapped or empty), independent re-read matched exactly (index and every curve, about 2.6M cells), production 7 wellbores / 15,634 days / 203,242 values exact; parse-only memory over 234 LAS files 792 MB -> 146 MB, extraction overhead under 0.5 s. Independent QA returned the first candidate for a bogus series from a wrapped-row file (repaired, scan found no other) plus low items; re-check passed (909 passed, 4 skipped, 1 deselected). Results are for the approved real files only.

### TASK-048 · Project data overview in the Sources tab (UI-13)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend |
| Depends on | TASK-034, TASK-046, TASK-047 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/UI_DESIGN_SYSTEM.md |
| Version | 0.27.0 |
| Parent | FL-021 |
| Slice | FL-021-C |

**Outcome.** Frontend owner adds the project Overview (UI-13) as the first view of the Sources tab from existing APIs only: documents by processing state/format, extraction coverage per kind, issues by severity with locators, resolved wells/wellbores with record counts, available log and production series per wellbore with units and ranges, depth-default warnings, and the honest list of what is not available yet. No new backend or contract.
**Next action.** Merged in 0.27.0 on November 1 after independent QA (partial pass, no blocking defects). Owner browser checkpoint pending. The pipeline panel (TASK-053) follows once the TASK-056/057 contracts merge. Not browser-verified by QA: series and units, the cap notice, in-page stale-project switch and real Volve data; two low wording observations.
**Evidence.** Implemented on branch `feature/task-048-project-overview` (frontend only; no backend or contract change, `check:contracts` clean). `frontend/src/features/overview/` (`api.ts`, `model.ts`, `ProjectOverview.tsx`) feeds `ProjectOverviewSlot`. Sources used: documents list (state, storage, format), per-document extraction reports (record counts per kind, stated coverage, issues with first locator; bounded to 100 reports and 500 documents with a visible notice), identity listing (wells, wellbores, record counts per kind, unresolved groups, stale-resolution warning), series list (per source wellbore label: unit and status, index range, value range, valid/sample counts; unit warnings) and a static not-yet-available list (TASK-054/056/057, reconstruction). Sections load, fail and retry independently with request IDs; answers for another project are dropped. Vitest `tests/overview.test.tsx` (6 tests: exact counts against fixtures, empty state, local failure and retry, unreadable reports, stale project, refresh and keyboard region). Gates: lint, typecheck, test (153 passed), build, check:contracts all green. Not run: Playwright against a real lane with the seeded subset and axe (needs the lane stack; left to independent QA). Known limits: no project-wide issues API exists, so issues come from per-document reports; series labels are shown as written and not mapped to resolved wellbores; record-level unit-defaulted depths are not summarised (only series unit status and MISSING_UNIT issues).

### TASK-049 · Source remove/replace and project-delete controls (IN-9, IN-5, PW-9)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P1 |
| Tags | frontend |
| Depends on | TASK-034, TASK-039 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/UI_DESIGN_SYSTEM.md |
| Version | none |
| Parent | FL-021 |
| Slice | FL-021-D |

**Outcome.** Frontend owner adds the Sources-tab remove (irreversible-deletion confirmation) and replace controls and the project-delete dialog (typed project name) on top of the TASK-039 APIs, using the shell components; no fake controls before the backend exists.
**Next action.** Dispatch after TASK-034 and TASK-039 are integrated.
**Evidence.** none yet

### TASK-050 · Per-file upload rejection reporting and red refused-file rows (IN-10)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, frontend, ingestion |
| Depends on | TASK-006, TASK-034 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | 0.23.0 |
| Parent | FL-005 |
| Slice | FL-005-G |

**Outcome.** The upload error names every refused file with its reason and the batch outcome is explicit; the UI marks refused files red (text and icon) and lets the user retry without them. Found in the owner's first manual test (November 1): a generic "unsupported file type" message gave no file name.
**Next action.** none
**Evidence.** Per-file refusal reporting (batch rejected, every refused file named) and red refused rows. Independent QA on `9e490f0`: backend 1194 passed/7 skipped, ruff, mypy strict, frontend 143 tests, contracts, build, e2e 29/29.

### TASK-051 · Extensionless and legacy-encoded text intake and Compass survey text profile (IN-11)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | ingestion, backend |
| Depends on | TASK-009 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | 0.25.0 |
| Parent | FL-005 |
| Slice | FL-005-H |

**Outcome.** Text files without an extension or in UTF-16/Windows-1252 are inspected as text with a recorded encoding, and the Volve Compass survey text export (for example `Volve F_F-12_F-12_F-12_ACTUAL`) gets a native trajectory profile preferred over the PDF text layer. The owner's first upload refused that file as an unsupported signature; the cause (likely non-UTF-8 bytes or NULs in the first 64 KiB) is unconfirmed until the file is inspected.
**Next action.** Done in 0.25.0. Known low defect D4 (an invalid date still proves day-first order for another date) is open; duplicate-source precedence is TASK-059.
**Evidence.** The real F-12 export is a Statoil survey export, not the Compass layout; `text_statoil_survey_export` shipped in 0.25.0, independently verified on `5b5aaa5` against the real F-12/F-5/F-14 ACTUAL and PLAN files (0 value mismatches in 211/119/97/137 and 93/114 stations), backend 1244 passed/7 skipped, local-data opt-in tests pass, ruff, mypy strict, contracts clean. Intake shipped in 0.23.0; `text_compass_survey_report` profile and Latin-1 acceptance fix in 0.24.0 (synthetic fixtures only; real file not yet read). Independent QA on `da43a87`: backend 1217 passed/7 skipped, ruff, mypy strict, contracts clean; adversarial profile and encoding checks passed after one repair (kana UTF-16, late-byte whole-file check).

### TASK-052 · Files table columns, expandable details and bulk labelling (UI-14)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend |
| Depends on | TASK-034 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/UI_DESIGN_SYSTEM.md |
| Version | 0.23.0 |
| Parent | FL-021 |
| Slice | FL-021-E |

**Outcome.** Separate Your labels, Suggested labels and Tags columns, SHA-256 and identifiers in an expandable detail row, multi-select rows with a bulk category action, and batch assignment at upload time.
**Next action.** none
**Evidence.** Your/Suggested labels and Tags columns, expandable details, bulk labels at upload and in the table (per-document calls). Independent QA on `9e490f0`: backend 1194 passed/7 skipped, ruff, mypy strict, frontend 143 tests, contracts, build, e2e 29/29.

### TASK-053 · Reconstruction pipeline panel, readiness checklist and explicit start (UI-15)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend, backend, agent |
| Depends on | TASK-034, TASK-048 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/UI_DESIGN_SYSTEM.md |
| Version | 0.30.0 |
| Parent | FL-016 |
| Slice | FL-016-F |

**Outcome.** The user can see what the system already did after upload (automatic verification, parsing, indexing), what is ready, what is a gap, the minimum conditions to start, and can explicitly start reconstruction, with any model-spending step shown and confirmed separately.
**Next action.** Merged in 0.30.0. Follow-ups: merge-proposal review UI (not built; needs a task), surfacing `BLOCK_NOT_STATED` after TASK-061, label-driven classification and extraction (TASK-055). Owner browser checkpoint pending.
**Evidence.** Merged in 0.30.0 after independent QA (first QA failed on a stale remaining-budget figure for confirmed runs; repaired in cfef5da and re-verified PASS in a real browser against a lane API with the stub provider). `frontend/src/features/pipeline/`, `tests/pipeline.test.tsx` (178 vitest total). Browser-verified: checklist and exposure vs API, estimate then separate confirm, double-click single POST, stale confirm 409, cancel and retry, over-budget block (409 `budget_exceeded`), stale project switch, error/empty states, axe 0 violations. Not browser-verified: failed and interrupted run states (stub cannot inject; vitest only), over-500-page range input (intake refuses 501 pages), truncation notices beyond the "counts remain exact" notice, request-id display, live provider. Known low: per-document text in a cancelled run still reads "cancelled cancelled before it started". Confirm is one call (there is no separate start endpoint).

### TASK-054 · Processing-run contract: estimate, confirm, start, state (PF-1..PF-3, PF-10)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, agent |
| Depends on | TASK-036, TASK-050 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/PROCESSING_FLOW.md |
| Version | 0.26.0 |
| Parent | FL-005 |
| Slice | FL-005-I |

**Outcome.** A persistent, project-scoped processing run for selected documents with or without labels: estimate (pages, route, tokens, USD, remaining budget) then separate confirmation, 500-page bound, cancellation, retryable failure states and honest "no native parser, processing available" document state.
**Next action.** Done in 0.26.0 with a stub provider. TASK-055 plugs the label-driven extraction step into `ProcessingStep.run_document`; the UI panel is TASK-053.
**Evidence.** Shipped in 0.26.0 (migration 0011, `backend/fieldlens/processing/`, stub provider only, no live spend, no OCR). Independent QA on `0a0c4fc`: full backend 1260 passed/7 skipped (one stale-metadata version test, environment only), ruff, mypy strict, contracts clean, 17 processing tests, hostile-amount repro fixed after one defect (D-1); a true 500-page PDF and a real ledger-spend case are not exercised.

### TASK-055 · Document classification, label proposal and label-driven extraction for non-native PDFs (PF-4, PF-5)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | agent, ingestion |
| Depends on | TASK-054, TASK-070 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/DOCUMENT_IDENTIFICATION.md |
| Version | 0.36.0 |
| Parent | FL-022 |
| Slice | FL-022-E |

**Outcome.** Documents without identity or label are classified (model route only; OCR deferred to TASK-060); the label is proposed with evidence, user labels win, and extraction runs through the label's agent step on the existing harness.
**Owner amendment 2026-11-02 (loose first slice, TASK-041 waived):** a non-native PDF is sent through the manually triggered, confirmed processing run; the model assigns a category or at least a tag description (classification failure falls back to category `others`) and must find a wellbore identity (the minimum). No identity yields a non-blocking warning, not a blocking error. Results are proposals with page/quote evidence, never accepted facts. Spec `specs/DOCUMENT_IDENTIFICATION.md` (written 2026-11-02, approved).
**Next action.** Owner-authorized bounded live run (AC-11, <= 2 documents, per-run cap; needs MODEL_API_KEY, owner-confirmed token rates and `FIELDLENS_LIVE_META=1`) is NOT yet run; the live path (`processing_provider=meta`) is unverified. Follow-ups: model tags are not tracked separately from user tags; a native suggestion equal to an earlier model suggestion is replaced with it; the cache key omits provider/model; no config-driven stub model step for a fully live e2e; a lowercase single letter or bare digit after a wellbore name still validates the shorter name; `./dev` does not isolate a lane when `FIELDLENS_DATABASE_URL` is exported.
**Evidence.** QA-055 PASS after two repair rounds (D1 token-bounded identity quote match; D2 stale unclassified tag; D3 replacing suggestions; D5 warning text; D1b/D1c unicode and suffix handling); 1428 backend tests, 243 Vitest, e2e 30 passed with only the known UI-2/UI-10 failures; offline stub provider only, no Meta call; merged `e609774`, release 0.36.0.

### TASK-056 · Per-wellbore, per-category data exposure API and readiness gate (PF-6, PF-8)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend |
| Depends on | TASK-046, TASK-047 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/PROCESSING_FLOW.md |
| Version | 0.28.0 |
| Parent | FL-016 |
| Slice | FL-016-G |

**Outcome.** Read-only API grouping records per wellbore and category with locators, validation state, gaps and conflicts, plus the deterministic start gate (validated trajectory present; surface location only warns).
**Next action.** Merged in 0.28.0. The exposure/gate UI is TASK-053; block-less labels count directly after TASK-061 (D9).
**Evidence.** Merged in 0.28.0 after independent QA (first QA failed on silent caps; repaired and re-verified PASS): `specs/PROCESSING_FLOW.md` section 8; `test_wellbore_exposure.py`, `test_exposure_caps.py`, opt-in `test_local_data_exposure.py`. QA: full suite 1268 passed, ruff/format/mypy strict/check:contracts green; exact totals and truncation flags verified with 130 findings and 5100 candidates; azimuth [0,360]. Not run: browser, live model. Known: Statoil files alone give NO_WELLBORE_IDENTIFIED until TASK-061.

### TASK-057 · AI identity-merge proposals and review (PF-7)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, frontend, agent |
| Depends on | TASK-046 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/PROCESSING_FLOW.md |
| Version | 0.29.0 |
| Parent | FL-016 |
| Slice | FL-016-H |

**Outcome.** A model step proposes that differently named or spelled sources are the same well/wellbore with alias evidence quotes; deterministic guards block impossible merges; the user accepts or rejects each; nothing merges silently.
**Next action.** Merged in 0.29.0 (backend and API). Review UI is a follow-up task after TASK-053; TASK-061 adds block-less label eligibility. No live run without orchestrator authorization (D7).
**Evidence.** Merged in 0.29.0 after independent QA (first QA failed on ruff import order and wellbore-kind revert ids; repaired in 1beb63a and re-verified PASS): `specs/MERGE_PROPOSALS.md` (guards G1-G7, MP-1..MP-9), `backend/tests/merge_proposals/`. QA: full suite 1288 passed, ruff/format/mypy strict/check:contracts green, concurrent accept yields one merge, label-kind and wellbore-kind revert id-exact, single Alembic head 0012. Stub provider only; no live model call. Known: G5 planned/as-built check is lexical only; cross-designator merges forbidden in v1; migration 0012 columns for revert hints added in place (0012 was unreleased).

### TASK-058 · Unlocated local display origin (0, 0) and its exclusion from georeferenced results (PF-9)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | backend, geospatial |
| Depends on | TASK-056 |
| Assignee | agent:fieldlens-geospatial |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/PROCESSING_FLOW.md |
| Version | none |
| Parent | FL-017 |
| Slice | FL-017-C |

**Outcome.** A wellbore without a sourced surface location is flagged unlocated, uses a labelled local origin with no CRS or datum, shows a warning, and is excluded from cross-well distance, terrain alignment and closest-approach results with the exclusion stated.
**Next action.** Define the marker and the exclusion hook in DATA_QUALITY.md alongside the contract.
**Evidence.** none yet

### TASK-059 · PDF-versus-text duplicate-source precedence and conflict report (IN-11)

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P1 |
| Tags | backend, ingestion |
| Depends on | TASK-051 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/INGESTION.md |
| Version | none |
| Parent | FL-005 |
| Slice | FL-005-J |

**Outcome.** When a Compass PDF and its text export describe the same wellbore, the text export is preferred and per-attribute disagreements beyond tolerance are reported as a conflict.
**Next action.** Needs cross-document matching on well key plus wellbore name, a precedence flag on the extraction run and locator pairing.
**Evidence.** none yet

### TASK-061 · Block-less well labels (Statoil exports) as unresolved identities eligible for merge proposals

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, agent |
| Depends on | TASK-056, TASK-057 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/PROCESSING_FLOW.md |
| Version | 0.31.0 |
| Parent | FL-016 |
| Slice | FL-016-I |

**Outcome.** Owner decision (2026-11-01 16:39): a label such as `F-12` or `F-5` is a valid wellbore name exactly as written. When it differs from a fully qualified name (`15/9-F-12`) it is a separate wellbore until the merge process unifies them; detecting "several names, one entity" and unifying their data is the job of the reconstruction/merge step (TASK-057), not of the resolver. Today the deterministic resolver resolves an unqualified label only when another source names it with the block, so a project with only the Statoil exports yields `NO_WELLBORE_IDENTIFIED` (found by the TASK-056 real-record test). Change: unqualified labels become wellbore identities named as written (block and well key recorded as not stated, no invented block), carry their records, count for the exposure and the start gate directly (with a "block not stated" warning), and are eligible merge-proposal members/targets with guards unchanged (an unqualified label never silently merges into a qualified one).
**Next action.** Merged in 0.31.0. Follow-ups: the UI must show `BLOCK_NOT_STATED` and present several pending proposals for one block-less wellbore as mutually exclusive (review UI task, not yet created).
**Evidence.** Merged in 0.31.0 after independent QA PASS at e4620e7: full suite 1302 passed, ruff/format/mypy strict/check:contracts green, no migration (head 0012). Real data (opt-in `test_local_data_exposure.py`, passed): F-12 and F-5 Statoil exports alone give two block-less wellbores with validated trajectories, an open gate with `BLOCK_NOT_STATED` and `SURVEY_STATUS_UNSTATED`, located; adding the perforation table gives four wellbores and candidate pairs exactly F-12/15-9-F-12 and F-5/15-9-F-5, `identity_merge` empty. Synthetic adversarial (stub provider): prefix collisions, variants, two projects, two blocks, accept/revert id-exact, idempotent re-resolve. Deliberate behaviour change: the tail-join is removed (a lone F-12 beside one qualified well no longer joins silently). Not verified: stub provider on real data, F-14 on real perforation data, frontend on this branch, live model. Low residual: an underscore block spelling in a quote (`15_9-F-12`) could count as naming block-less F-12 (not tested).

### TASK-062 · PDF extraction reports "Failed (nothing is trusted)" on re-processing

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, ingestion |
| Depends on | none |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/PROCESSING_FLOW.md |
| Version | 0.30.0 |
| Parent | FL-016 |
| Slice | FL-016-J |

**Outcome.** Owner report (2026-11-01 17:12): re-processing an uploaded PDF shows the extraction status "Failed (nothing is trusted)". Diagnose which real Volve PDFs fail and why, then make the status honest (no native parser means "processing available", not failed) and fix genuine bugs. No classification (TASK-055) and no OCR (TASK-060).
**Next action.** Closed as diagnosis only; no code change.
**Evidence.** Diagnosis on 0.26.0: all 2,474 real Volve PDFs through the real upload and extraction path on a throwaway DB: 0 failed (2,369 unsupported with no native parser, 49 Compass survey reports succeeded/partial, 54 in-batch duplicates not stored, 2 over the 128 MiB upload limit: `Discovery_report.pdf` and its copy). The owner's report matches stale 0.24 state (inferred, 0.24 was not run). Latent risk, not reproduced: a PDF that matches the Compass survey detector but lacks a "TVD Reference" page would be stored as failed (`profile_mismatch`). If old failed rows persist, an explicit retry re-queues them.

### TASK-063 · Slim Sources tab and Reconstruction tab with per-wellbore processing (UI-16)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend |
| Depends on | TASK-053, TASK-056, TASK-061 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/RECONSTRUCTION_TAB.md |
| Version | 0.32.0 |
| Parent | FL-016 |
| Slice | FL-016-K |

**Outcome.** Owner feedback (2026-11-01 22:29): the Overview and pipeline panel bloat the Sources tab. Sources returns to header, tabs, upload, source revision and revision files (with per-file re-run). A Reconstruction tab lists identified wells and wellbores, ready ones first and highlighted, with a Sources column (files per wellbore) instead of Present/Validation, a per-wellbore Process action and a Process-all-ready action over the existing estimate and separate confirm flow.
**Next action.** Owner checkpoint in the browser (confirm what Process should do). Follow-ups: merge-proposal review UI; files list refresh after a 409 re-run; Process cannot cover no-profile documents until TASK-055 links records to a wellbore.
**Evidence.** Implementation `84a79b6` + repairs `c8fefc4`, `ac43e82`, merged. Independent QA (agent `58273c59`): first pass PASS with 4 Low defects (repaired); second pass FAIL (Process never enabled with real data, regression of the repair; fixed); third pass PASS in a real browser against the real API (stub provider): Sources slim, ready-first list with Ready badge, F-12 Block not stated, one estimate POST, separate confirm (keyboard), estimate reuse, native-only rows disabled with reason, axe 0 violations, cancel/retry. 189 vitest tests, lint, typecheck, build, check:contracts pass. Not verified: failed/interrupted run states, the different-document-set estimate in a browser (vitest only), live provider.

### TASK-064 · "Extraction failed (source_missing): stored original is not readable" on re-run extraction

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, ingestion |
| Depends on | none |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/PROCESSING_FLOW.md |
| Version | 0.31.1 |
| Parent | FL-016 |
| Slice | FL-016-L |

**Outcome.** Owner report (2026-11-01 22:29, running 0.30/0.31 on his own DB): `COMPLETION_REPORT_2.PDF` re-run extraction still fails with `source_missing: stored original is not readable` although storage shows hash-verified. TASK-062 only covered fresh uploads, so this is a different failure: the stored original is not found at extraction time (likely the storage root or paths resolved differently between the process that stored the file and the one extracting, e.g. another checkout/worktree or a changed `.local` root, or a stale path in the DB). Diagnose and fix so re-run works, or so the failure is honest and recoverable (e.g. re-upload prompt), without touching the owner's data.
**Next action.** Owner: start the app from the checkout whose `.local/fieldlens/storage` holds the file (or re-upload it) and press Re-run extraction. Low follow-ups: refresh the files list after a 409 (frontend), plain POST without `retry` skips verification.
**Evidence.** Root cause (code-supported, not reproduced across two real checkouts): the storage root is per checkout (`Settings.storage_root` = `REPO_ROOT/.local/fieldlens/storage`) while the DB is shared, and nothing re-verified storage after upload. Fix `09940b8` (merged); QA `5090da60` PASS: throwaway-root repro (409 with request id, no path leak, recovery restores stored, tampered bytes never succeed), 1304 backend tests passed/8 skipped, ruff, mypy strict, ledger ok.

### TASK-065 · Merge-proposal review UI (accept, reject, revert) in the Reconstruction tab

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P0 |
| Tags | frontend |
| Depends on | TASK-057, TASK-063 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/MERGE_PROPOSALS.md |
| Version | none |
| Parent | FL-016 |
| Slice | FL-016-M |

**Outcome.** The merge-proposal API (0.29.0) has no UI. Reconstruction tab shows pending proposals per wellbore (e.g. `F-12` with `15/9-F-12`) with the evidence quote, guards and warnings; accept, reject and revert are explicit user actions; several pending proposals for one block-less wellbore are presented as mutually exclusive; accepted merges update the list and sources. Also: refresh the files list after a 409 on re-run extraction (TASK-064 follow-up).
**Next action.** Spec amendment for the review UI, owner approval, then a lane.
**Evidence.** none yet

### TASK-066 · New completion PDFs still fail with `source_missing` while storage reads hash-verified

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, ingestion |
| Depends on | TASK-064 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-02 |
| Sprint | Hackathon |
| Spec | specs/RECONSTRUCTION_RUN.md |
| Version | 0.33.0 |
| Parent | FL-016 |
| Slice | FL-016-N |

**Outcome.** Owner report (2026-11-01 23:44): a freshly uploaded `15-9-F-11 B_Completion log.pdf` (label Completion equipment) still shows "Extraction failed (source_missing): stored original is not readable" with Stored (hash-verified), although the document list shows its page count. Find the real cause using the real files and the real runtime (read-only inspection of the owner's runtime and storage metadata, no document contents, no writes) and fix it; the TASK-064 storage-root hypothesis is not sufficient. A PDF either extracts or reports a specific honest reason.
**Next action.** Root-identity marker follow-up is TASK-070; owner restarts with `./dev restart` and re-runs extraction on affected files.
**Evidence.** Guard so a wrong-storage-root process no longer claims verification, extraction or processing work (`root_guard.py`); QA-066 PASS with Medium findings (no protection on a fresh DB, global sample) tracked as TASK-070. Release 0.33.0 (`9f60267`).

### TASK-067 · Reconstruction table: records merged into Sources, Document processing pane removed (UI-17)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend |
| Depends on | TASK-063 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/RECONSTRUCTION_RUN.md |
| Version | 0.33.0 |
| Parent | FL-016 |
| Slice | FL-016-O |

**Outcome.** Owner feedback (2026-11-01 23:44): drop the "Records per category" column and show each category once in the Sources column with its record count; remove the Document processing pane and the stub run list from the UI (it shows "Processed" with no data and no spend); the Action column no longer says "Nothing to process" (the start action arrives with TASK-069; until then show nothing misleading).
**Next action.** None.
**Evidence.** Records merged into Sources headings, Document processing pane removed; QA-067 PASS in a real browser (2 Low nits fixed in TASK-069). Release 0.33.0 (`7f4f329`).

### TASK-068 · Per-wellbore reconstruction run API: estimate, confirm, stages S1..S4 (RR-1..RR-5)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend |
| Depends on | TASK-054, TASK-056, TASK-057 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/RECONSTRUCTION_RUN.md |
| Version | 0.33.0 |
| Parent | FL-016 |
| Slice | FL-016-P |

**Outcome.** A persisted reconstruction run per ready wellbore (bulk start for all ready), estimate then separate confirm, cancel, retry, idempotent duplicate start, stages S1 gather and S4 assemble deterministic, S2 extract and S3 identify reported `not_available` until their agent steps exist (the run is `partial`, never `succeeded`), USD 5 cap and no live call by default.
**Next action.** Agent extract/identify stages arrive with TASK-055.
**Evidence.** Reconstruction run API with migration 0013; QA-068 PASS, 1323 backend tests, no live call path. Release 0.33.0 (`da23082`).

### TASK-069 · Reconstruct buttons, bulk start and run detail in the Reconstruction tab (RR-6, RR-8)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend |
| Depends on | TASK-067, TASK-068 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/RECONSTRUCTION_RUN.md |
| Version | 0.33.0 |
| Parent | FL-016 |
| Slice | FL-016-Q |

**Outcome.** Reconstruct per ready wellbore and Reconstruct all ready wellbores with estimate, separate confirm and per-stage progress; honest labels for stub and not-available stages.
**Next action.** Merge-proposal review UI is TASK-065; live agent stages TASK-055.
**Evidence.** Per-wellbore and bulk Reconstruct with estimate/confirm, run state and draft detail; QA-069 PASS in a real browser (axe clean on the three tabs), 3 Low defects repaired in `aa68ac7`, 195 vitest. Release 0.33.0.

### TASK-070 · Storage integrity: root identity marker, recoverable failed files, no "quarantine"

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend |
| Depends on | TASK-066 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/STORAGE_INTEGRITY.md |
| Version | 0.34.0 |
| Parent | FL-016 |
| Slice | FL-016-R |

**Outcome.** Replace the 8-most-recent heuristic of the TASK-066 guard with a persisted root-identity marker (DB row and `<root>/.fieldlens-root-id`) that every blob-reading worker compares before claiming work. Closes the QA-066 gaps: no protection before the first stored original, stall after an intentional wipe, global rather than project-scoped sample.
Owner report 2026-11-02: 0.33.0 did not fix PDF `source_missing`; the cause was a stale pre-guard worktree server. Scope is widened (spec approved 2026-11-02): files are only Stored or Failed, "quarantined" disappears from API/UI, Retry and Re-upload repair a failed file, startup heal pass, failure attribution (process identity, `application_name`) and a `./dev` warning for other processes on the same DB. Migration `0014`, proposed 0.34.0.
**Next action.** None. Unblocks TASK-055. Follow-ups: heal runs once per process start (later failures use Retry/re-upload).
**Evidence.** QA-070 PASS after one repair round (heal on all-failed incident shape, UI stale alert, dev-tool false warning); merged `9d46c94`, release 0.34.0. QA-066 report (PASS with Medium findings), 2026-11-02; incident analysis 2026-11-02.

### TASK-060 · OCR versus model page-read benchmark for scanned-document classification

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P2 |
| Tags | agent, ingestion |
| Depends on | TASK-055 |
| Assignee | agent:fieldlens-ingestion |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/PROCESSING_FLOW.md |
| Version | none |
| Parent | FL-022 |
| Slice | FL-022-F |

**Outcome.** Measure cost, time and classification agreement of OCR against the model page read on the same pages, and enable OCR as the classification first pass only if it is demonstrably cheaper and faster (PROCESSING_FLOW D2, D8).
**Next action.** Deferred by the owner on November 1; do not start before TASK-055 and without separate authorization.
**Evidence.** none yet

## Journal

Everything below is the unchanged pre-conversion narrative (including the original
work-items table and finalized priorities), kept as history. Where it conflicts with the
item blocks above, the item blocks are authoritative for current status.

## Owner decisions, October 31 (fourth pass)

- **Dispatch.** Owner approved the extraction harness (TASK-036, AX-12..15), the visual-level equipment extraction (TASK-041, EQ-8..11) and the first proper UI (TASK-034 shell, project management and sources/upload; TASK-048 overview) so incremental work can be tested in the browser. Project deletion is added (PW-9, TASK-039; UI in TASK-049) because leftover projects had to be removed by hand. TASK-034 no longer waits for TASK-039.

## Owner decisions, October 31 (third pass)

- **Data completeness first.** Before agents aggregate anything: depth defaults and deterministic identity (TASK-046) and time-series storage (TASK-047), specified in specs/DATA_COMPLETENESS.md.
- **Depth units.** Meters (MD) are the default for depths without a unit; a warning, never a blocker.
- **OCR dropped; equipment is visual-level.** Casing, tubing, pumps, perforations, isolations and similar are read directly from page images with a superficial goal (type, material, sizes, structure); model-read, unverified, never used in calculations; speed and performance first. TASK-030 phase B cancelled (TASK-030 closed as done with phase A), page rendering moves to TASK-036.

## Owner decisions, October 31 (second pass)

- **Scans need OCR first.** An OCR text layer with page/box locators precedes model reading for scanned documents (TASK-030); a number is accepted only when the OCR token and the image read agree.
- **F-12 equipment.** The EDM export is checked offline for deterministic completion data (TASK-044); if none is found, generic 3D assets cover missing equipment as long as the other F-12 data is available. The three completion reports in the F-12 folder describe F-11 wells and are not used for F-12.
- **Demo data-quality policy.** No user correction flow is planned; minor non-structural inconsistencies are recorded as warnings and auto-resolved by a documented deterministic rule, structural ones still block affected outputs (DATA_QUALITY amendment). Owner then classified DQ-3 (F-14 reference elevation) and DQ-4 (F-12 perforation interval) as minor: warning plus deterministic auto-resolution.
- **Vector indexing policy (TASK-011).** Skip vectors for pure numeric tables (they dominate the production workbook, 97% of chunks); embed everything else completely; exact identifiers and full-text still cover the numeric tables.
- **No human verification of the spike reference** for now; QA's audit stands and gold fixtures come later (TASK-002).

## Owner decisions, October 31

- **Equipment scope.** Production/completion equipment (pumps, tubing, casing and liners in service, bearings,
  packers: everything that constitutes the wellbore during production) is the visualization target.
  Development/drilling equipment (BHA, bits, drilling assemblies) is not to be visualized or used.
  TASK-009's 0.14.0 equipment output is drilling-side only, so equipment extraction restarts from the
  completion documents (TASK-030 profiles, TASK-042 feasibility spike, TASK-041 extraction).
- **Agentic extraction first.** No model call has ever been made (database: 0 provider attempts, 0 spend
  reservations; the offline adapter, TASK-004, is the only agent code). The live smoke (TASK-005) is authorized
  at USD 1 with synthetic prompts only. TASK-039 and TASK-034 move behind the extraction path.
- **Parallel lanes.** Two parallel per-task worktrees (the October 30 amendment) for TASK-005 and TASK-038;
  TASK-011 follows in the RAG lane.
- **Cleanup.** Six QA test projects (QA9 A, QA9 B, three QA9b A, QA9b probe) were deleted from
  `fieldlens_app` in one transaction (the four append-only guard triggers were disabled inside it and
  verified re-enabled); the project `Test` was kept. A pre-cleanup dump is in the session scratchpad.
  The application has no project-delete feature.
- Added TASK-041 and TASK-042 (proposed, awaiting spec amendment and an allowance); TASK-011 and TASK-030
  are ready; FL-003 and FL-022 are in progress.

## Owner realignment, October 30

Owner review of the Taiga board produced these decisions (ledger edits and specs in the same change set;
documentation only, no application change, not yet integrated or versioned):

- TASK-001 closed (0.12.1): DA-7 preflight is recorded per dispatch rather than as one all-profile sweep.
  FL-001 stays open for the remaining profile activations.
- FL-002/TASK-002 renamed and reframed as demo dataset qualification and gold fixtures (test ground
  truth, not upload); FL-005 no longer depends on FL-002; TASK-029 keeps the real tie.
- FL-015 closed at 0.8.0 with no open tasks; PW-6 moved to the TASK-026 acceptance.
- New FL-021 (demo-grade shell and design system, TASK-033/034/037; the prototype UI is unstyled) and FL-022
  (model-proposed extraction with deterministic validation, TASK-035/036). Both specs were drafts when added.
  Later UI tasks (TASK-010/016/017/019/032) now depend on TASK-034; TASK-026 depends on TASK-036; TASK-021 on TASK-037.
- Charts TASK-016/017 decoupled from TASK-026 (source-record scope, labeled unreconciled until a model exists).

### Owner decisions on both specs, October 30 (second pass)

- UI_DESIGN_SYSTEM approved: light theme, conservative vivid (cobalt) brand, Inter, lucide-react, component kit
  delegated to the orchestrator and decided as Mantine, large screens only. Navigation: left sidebar manages
  projects; a project opens to top tabs Sources (files), Reconstruction (log of agentic parsing) and Explore (3D
  model, charts, chat). TASK-033 done; FL-021 and TASK-034 ready (dispatch first).
- AGENTIC_EXTRACTION approved: question-driven model use, validators-only acceptance, deterministic coordinates and
  trajectories, one shared-contract change, no live spend in TASK-036, all documents shareable so the model may get
  content, read-only tools and page images. TASK-035 done; FL-022 ready.
- New TASK-038 (activity log and Reconstruction view; TASK-036 and TASK-026 depend on it), TASK-039 (source
  removal/replacement as new revisions; awaiting owner confirmation of the semantics), TASK-011 added as a
  prerequisite of TASK-036, and a multimodal image-input check added to the TASK-005 live smoke.

### Owner decisions and re-sequencing, October 30 (third pass)

- Source removal (IN-9, TASK-039): the stored bytes are physically deleted to free disk; a tombstone revision
  keeps the history; derived claims become inactive; re-upload creates a fresh document. Replacement is a new revision.
- Coordinates (AX-11): a model-extracted coordinate/trajectory value may be used as a labeled backup when no
  reliable deterministic source exists; explicit CRS/datum/references are still required and never assumed, and a
  deterministic source always supersedes the fallback.
- Priority: upload and parsing first, UI after. Order: TASK-009 (native profiles) -> TASK-039 (removal) ->
  TASK-011/TASK-004/TASK-030 -> TASK-034 shell (restyles the evidence and Sources screens) -> later UI tasks.
  TASK-038 is now backend only; the Reconstruction view is TASK-040 (after TASK-034), so TASK-036 no longer waits
  for the UI. TASK-034 moved to due 2026-11-01. Other due dates are not yet re-baselined; do that after TASK-009
  has a measured duration.

## Status and ownership

States: `proposed`, `specifying`, `ready`, `in_progress`, `testing`,
`integration_pending`, `done`; exceptional `blocked` / `cancelled`.
`Ready` requires an approved feature spec and satisfied prerequisites. `Done`
requires the integrated commit, version and acceptance evidence, not just coding.
Owner is the project owner for approval; an execution agent is unassigned until
delegated. [Custom profiles](../.github/agents/README.md) are now defined; actual
host activation/tool verification is required per assignment. Backend editing
worked for initial implementation but is missing again in the repair worker;
QA browser/test tools worked. The first foundation worktree
was created after the owner's October 28 implementation approval. It is now
inactive and preserved; the serial-checkout allocation below supersedes it.
The repaired foundation was tested at `95da2b7` and integrated into `master`
at `1293f55` as 0.4.0, under an explicit one-time direct-verification exception.

The confirmed workflow [architecture](ARCHITECTURE.md), [feature specs](specs/README.md)
and [32-task execution plan](../plan/architecture-fieldlens-1.md) define the
implementation baseline. The [first detailed packets](../plan/feature-foundation-workspace-1.md)
were integrated in `9d630e3` and approved for implementation by the owner at
11:19 EDT on October 28. The backend editing-tool blocker recurred during repair;
the owner authorized direct repairs and accepted their checks for this foundation
only. Future features still require independently verified acceptance.
The task plan's explicit **Depends on** column is the scheduling DAG;
parent dependencies below describe complete-feature prerequisites, not permission
to block every independent sub-slice. Documentation links do not imply approval.

## Work items

**Current planning authority (October 28):** the owner selected F-12/F-14/F-5,
accepted evidence-safe generic F-12 equipment and visible discrepancies, and
confirmed hybrid categories, explicit reconstruction/review/publication and
128 MiB/file, 512 MiB/batch, 200-file limits. G0 workflow/cohort choices are resolved.
The first three detailed packets are approved and committed. Backend tool exposure
remains an unresolved per-assignment gate; the foundation exception is not proof
of a general host fix.
At 14:47 EDT the owner approved one feature at a time on its own branch in
`/home/slimco/code/FieldLens`, with subagents launched from the main session.
No new worktrees or concurrent writers; model/tool preflight is still required.
G1 remains engineering/manifest qualification, not a requirement to find F-12's
missing tally before writing a project form. Foundation implementation has run;
no paid Meta call has started. Owner clarification at 17:12 EDT requires a
different agent to test every logical feature, re-verify fixes and complete the
authorized commit/merge cycle before the next feature.
The planning package was integrated by the owner in `9d630e3`, version 0.3.3.
Historical checkpoint text below records earlier states; this notice and the
current table supersede its access/design holds.

| ID | Outcome / scope | Status | Prerequisites | Spec / next action |
|---|---|---|---|---|
| FL-000 | Adopt perforation requirements and versioned parallel-development governance | done | None | Integrated by owner in `e8b156a`, version 0.1.0; verification below |
| FL-001 | Agree custom development-agent roles, serial branch delegation and resource boundaries | in_progress | FL-000 | TASK-025 backend native editing smoke passes; host resolves Sonnet 5.5. CLI ignores YAML effort, so worker medium is selected explicitly. Owner accepts main Astra/high for this continuation. Remaining profiles still require per-assignment activation; no blanket host fix claimed |
| FL-002 | Approve compact demo data/rights manifest, including dated perforation/state evidence | in_progress | None | Owner selected F-12/F-14/F-5 and accepted generic/unlocated F-12 limitations. [Data spec](specs/DATA_FEASIBILITY.md): final hashed profiles/windows/reference/state/rights fixtures remain TASK-002/029; G1 not passed. No automatic F-11 B replacement or further tally-search blocker |
| FL-003 | Verify Meta entitlement/protocols and agree shared budget controls | specifying | FL-004 | [Meta spec](specs/META_INTEGRATION.md): offline adapter/ledger then separate opt-in live smoke; no G1 dependency |
| FL-004 | Establish runnable stack, database/migrations and common identity/evidence/time contracts | done | FL-014 | Tested repair `95da2b7` integrated into master at `1293f55`, version 0.4.0. 124 backend, 4 UI and 3 CLI E2E tests plus quality gates pass. Owner explicitly approved a one-time direct-verification exception; [evidence](specs/FOUNDATION.md#direct-repair-verification-october-28) |
| FL-005 | Upload project sources into traceable, persistent, restart-safe source revisions | in_progress | FL-004, FL-002 | [Ingestion](specs/INGESTION.md): TASK-006 upload/storage/jobs/source UI done and independently accepted (`fb275f4`, 0.8.0; IN-1/3/4/5/7 except the 500-page PDF and parse-time XML/ZIP checks deferred to TASK-009); native profiles/evidence (TASK-009), scanned/Word profiles and final manifest acceptance remain |
| FL-006 | Inspect published-model trajectories with evidence and deterministic closest approach | in_progress | FL-005, FL-016 | [Trajectory/viewer](specs/TRAJECTORY_VIEWER.md): TASK-007 analytic engine done and independently accepted (TR-1/2/3, `532d517`, 0.6.0); reconstructed model scene (TASK-010, TR-4..7) remains |
| FL-007 | Reconstruct equipment with catalog/generic fallbacks and source-aware placement | specifying | FL-006 | [Equipment](specs/EQUIPMENT_RECONSTRUCTION.md): procedural installed-evidence slice; optional Blender later; DF-9 still required |
| FL-008 | Inspect dated perforation intervals, state transitions and total/open perforated length | in_progress | FL-005, FL-006 | [History](specs/PERFORATION_HISTORY.md): TASK-008 engine done and independently accepted (PH-2/3/5/7/9, engine-level PH-6; `aaf0fdd`, 0.7.0); PH-6 persistence, PH-1/4/8 and real event/scene integration (TASK-013) remain |
| FL-009 | Display aligned terrain/bathymetry and reservoir/formation context | specifying | FL-006 | [Context](specs/CONTEXT_LAYERS.md): independent seabed and formation slices; both mandatory |
| FL-010 | Link production and depth logs to asset/time selection and perforation overlays | specifying | FL-005, FL-016, FL-008 | [Charts](specs/LINKED_CHARTS.md): production/log views need model context, not finished 3D; overlays follow history |
| FL-011 | Deliver early source chat, then evidence-backed model/graph/tool exploration | specifying | FL-003, FL-005, FL-006, FL-007, FL-008, FL-010, FL-016 | [Retrieval/assistant](specs/RETRIEVAL_ASSISTANT.md): TASK-011/019/027 source chat precedes reconstruction/3D; full domain tools and 32-case evaluation follow |
| FL-012 | Verify complete fresh-upload -> scene/history -> charts -> cited-answer demo | specifying | FL-002, FL-009, FL-011 | [Demo acceptance](specs/DEMO_ACCEPTANCE.md): offline combined checks, real/live verification, then authorized release/recording |
| FL-013 | Curate offline Blender equipment-authoring skill and export handoff | done | None | Integrated by owner in `88b177e`, version 0.3.0; skill/workflow only, installation and asset creation deferred |
| FL-014 | Finalize project-centric architecture, primary reconstruction agent and UI-verifiable orchestration plan | done | None for planning | Owner integrated the 32-task DAG/specifications/first packets in `9d630e3`, version 0.3.3, and authorized first-packet implementation October 28. Document checks recorded below; no application verification implied |
| FL-015 | Create/reopen isolated projects with categorized, incremental sources | in_progress | FL-004 | TASK-025 done: independently accepted repair `2af22aa` integrated into `master` at `3e748d9`, version 0.5.0. [Evidence](specs/PROJECT_WORKSPACE.md#task-025-scoped-implementation-and-acceptance). TASK-006 (upload UI/API, `fb275f4`, 0.8.0) then delivered the upload-related PW criteria; aggregate feature not yet done (data-qualification criteria remain) |
| FL-016 | Reconstruct composite entities/relationships/configurations with evidence and reviewed model publication | specifying | FL-004 | [Reconstruction](specs/ASSET_RECONSTRUCTION.md): review policy confirmed; TASK-026 consumes early chat and TASK-032 issues, not full FL-011. Gold fixtures/live allowance remain separate gates |
| FL-017 | Inspect source-linked warnings/errors and the exact effect of missing/conflicting data | specifying | FL-004, FL-005 | [Data quality](specs/DATA_QUALITY.md): TASK-032 source-first issue inspector; FL-016/007 wire publication/generic boundaries; TASK-022 verifies all DQ criteria. No manual override/fact editor or new telemetry service |
| FL-018 | Single Compose project and one root `.env` loaded automatically by code (replaces per-lane `db.env`/override files) | done | FL-004 | [Dev environment](specs/DEV_ENVIRONMENT.md): owner-approved October 28; version 0.5.1; implementation `2bc4129`, independent QA PASS AC-1..8 (219 backend, 15 UI, 9 E2E). Fresh `fieldlens`/`fieldlens_app` names, old volumes untouched. Follow-ups: validate hand-edited password charset, name `scripts/init_env.py` in the readiness message, anchor `frontend_dist` |
| FL-019 | One-command local stack `./dev` (Postgres, migrations, API, optional Vite, tests, lane-aware) | done | FL-018 | [Dev tooling](specs/DEV_TOOLING.md): owner-approved October 29; version 0.10.0 (`feature/fl-019-a-dev-script`, independent QA PASS after 3 rounds, 450 backend tests). Limits: lane Vite proxies to 8101; `./dev test e2e` fixed to 8101 |
| FL-020 | Telegram notifications, machine-checkable backlog ledger and one-way Taiga sync (sprint `Hackathon`) | in_progress | FL-018 | [Tracking](specs/TRACKING.md): owner-approved October 29; **slice A notify.py done, version 0.9.0** (`feature/fl-020-a-notify`, independent QA PASS after 2 repairs, 396 backend tests); slices A notify, B ledger/check, C Taiga sync. Open: Taiga project is public (decide private vs `TAIGA_ALLOW_PUBLIC`), dedicated bot before enabling inbox |

**Scheduling gate for implementation across all rows:** FL-001 agent configuration
must be integrated and the selected profile/model/tools verified in the host;
the workflow's resource allocation must also be ready before implementation
delegation. Main-agent planning/specification and source inspection can proceed
before that gate; FL-002/FL-003 do not depend on each other.

### Finalized priorities and next dispatch

| Priority / checkpoint | Tasks | Dispatch condition / owner verification |
|---|---|---|
| P0: first persisted UI | TASK-001 -> TASK-003 -> TASK-025 -> TASK-006 | Foundation, project lifecycle and TASK-006 upload/storage/jobs/source UI integrated (0.8.0). TASK-009 native profiles/evidence is next, with fresh per-assignment preflight; owner browser checkpoint A before broadening |
| P0: independent evidence qualification | TASK-002 | Main-agent bounded source work or separately verified ingestion assignment; no fabricated G1 completion |
| P0: early agent risk | TASK-004 -> TASK-005; TASK-009/011/019/027 | Offline adapter parallel after foundation; live caps and source subsets separately authorized; checkpoint B before full scene |
| P0: visible quality and reconstruction | TASK-009 -> TASK-032; TASK-019/032 -> TASK-026; TASK-030/028 | Source issues before 3D; reviewed partial model; live reconstruction remains distinct from stubs |
| Required enrichment | TASK-007/008/010/012..018/031 | Numeric engines can start after foundation; remaining tasks follow DAG. History, both charts, seabed and formations are all mandatory |
| Required acceptance/release | TASK-029/020/021/022/023 | Full manifest, live evaluations, combined browser/performance and owner release permission |
| Optional only | TASK-024 | Blender after evidence-backed equipment and explicit asset/setup approval; never blocks required release |

These are priorities, not permission to bypass dependencies. Future packets
freeze their source mappings and exact contracts before dispatch; only the first
three runtime packets have step-by-step handoffs now. Known-command validation
routes to Terra; substantial implementation to the relevant domain specialist.

### TASK-025 completed lifecycle integration

October 28 continuation confirms TASK-003 is done at `1293f55` (0.4.0);
current integration base is `b4a02b2`. Two bounded backend preflights confirmed
the checkout and native create/edit/read/delete capability. Host events resolve
`claude-sonnet-5.5`; medium is explicitly selected in task arguments because
CLI 1.0.65 ignores profile `reasoning-effort`. Lower-level provider effort
telemetry is unavailable. The owner accepts main Astra/high for this continuation.
No paid Meta calls were made.

The approved lifecycle slice has one backend owner and a dedicated PostgreSQL
Compose project/volume/role, with a separate browser helper. See the project
spec allocation for ports, credentials location, ownership, bounds and checks.
Preserve the unrelated dirty Copilot-instructions file and old foundation
worktree. These preflights did not themselves prove project acceptance.

Backend implementation `37772d3` passed its checks; independent QA found one
invalid-text defect (NUL produced 503/500). Backend repair `2af22aa` rejects NUL
and lone surrogates with typed 422 responses before database access. A separate
QA invocation re-verified the repair and scoped PW-1/2/5/8 plus SC-2/4: 193 backend,
15 UI and 9 real API/PostgreSQL browser tests passed, with independent raw-JSON
and migration preservation probes. The versioned candidate was fast-forwarded
from unchanged `master` base `b4a02b2` to `3e748d9e939a007fb62c36f211680b41d33d1fd1`,
version 0.5.0. Final combined checks passed through
the host-resolved Terra worker with explicit low effort: 193 backend, 15 UI and
9 E2E tests plus lint/format/type/build/contracts and whitespace checks.
Installed package metadata is 0.5.0 after an explicit editable-package reinstall.
TASK-025 is done. TASK-006 upload/storage/jobs is next; full workspace and
data-qualification criteria remain incomplete. Task API/browser/database helpers
are stopped; ignored task credentials and database volume are preserved.
The unrelated Copilot-instructions edit and inactive worktree remain untouched.
No push, tag, publication or paid provider call occurred.

### Parallel lane allocation, October 29

The owner approved (15:31-15:34 EDT) three concurrent lanes in separate worktrees,
superseding the 14:47 EDT one-checkout rule for this batch only. TASK-004 is excluded.
Base `73d4de2` (+ this allocation commit), target `master`, no push. Worktrees live under
`/home/slimco/code/FieldLens/.local/worktrees/<lane>` (gitignored, inside the repo). Each has
its own `.env` copy whose `POSTGRES_DB` names a lane database on the shared
`fieldlens-postgres` server; tests still derive and drop `fieldlens_app_test_<8 hex>` siblings.
**Cleanup duty:** after all lanes merge, drop `fieldlens_t006/t007/t008`, remove the lane
worktrees/branches (non-forced) and lane storage, leaving only `fieldlens_app` for manual testing.
Workers never edit VERSION, CHANGELOG, BACKLOG or agent configuration.

| Lane | Task | Branch | Owner / QA | Owned paths | Resources |
|---|---|---|---|---|---|
| A | TASK-006 (FL-005-A): IN-1/3/4/5/7, PW-3/4/6/7 | `feature/fl-005-a-upload-jobs` | `fieldlens-backend` (API/jobs/UI), then separate `fieldlens-qa` | `backend/fieldlens/{ingestion,jobs,evidence}/`, upload DTOs/registry/generated client/migrations/app composition, `frontend/src/features/uploads/` (or the project source list), tests | DB `fieldlens_t006`, API 8101, Vite 5174, browser 9323 |
| B | TASK-007 (FL-006-A): TR-1/2/3 | `feature/fl-006-a-trajectory-engine` | `fieldlens-geospatial`, then separate `fieldlens-qa` | `backend/fieldlens/engineering/trajectory/`, `backend/tests/engineering/trajectory/`, `numpy` in `pyproject.toml`/`uv.lock` | DB `fieldlens_t007`; no ports |
| C | TASK-008 (FL-008-A): PH-2/3/5/6/7/9 (engine level) | `feature/fl-008-a-perforation-engine` | `fieldlens-geospatial`, then separate `fieldlens-qa` | `backend/fieldlens/engineering/perforation/`, `backend/tests/engineering/perforation/`; no dependency, contract, migration or app changes | DB `fieldlens_t008`; no ports |

Lanes B/C each create `backend/fieldlens/engineering/__init__.py` with the identical single
line `"""Deterministic engineering computations."""` so the merge is conflict-free. Only lane A
may change shared contracts, registry, migrations, `app.py` and `generated.ts`. Synthetic
fixtures only; zero provider calls. Merge order: B, C, then A (rebased on the latest `master`),
each with a serially allocated version bump.

**Outcome (October 29):** B merged as 0.6.0 (`f8f77d2`), C as 0.7.0 (`ff1ab04`), A as 0.8.0
(`5a6d2fd`; backend `34e0c6d` + UI `fb275f4`, merged with master). Cleanup done: databases and
roles `fieldlens_t006/7/8` dropped, lane worktrees and lane branches removed (non-forced),
`.local/worktrees` and e2e storage removed. Only `fieldlens_app` (plus `postgres`) remains
on the server, migrated to `0003_upload_jobs`. The old `fl-004-a-foundation` worktree no longer
appears in `git worktree list`. The `feature/fl-004-a-foundation*`, `fl-015-a-projects` and
`fl-018-dev-environment` branches pre-date this batch and were left untouched.

## Completed integration record

| Field | FL-000 |
|---|---|
| Owner / executing agent | Project owner / main agent, documentation-only |
| Base commit / current branch | `2772cff` / `master` |
| Worktree | Existing primary worktree; no feature implementation delegated |
| Integrated version | `0.1.0` initial documentation baseline |
| Required checks | Relative links, backlog ID/dependency integrity, version/changelog consistency, perforated-length example arithmetic, documentation whitespace |
| Verification evidence | 2026-10-27: 94 local Markdown/HTML references checked; 13 unique IDs with valid states/acyclic dependencies; bootstrap version agreement; all 7 synthetic state/length rows and ft/m round trips checked; 7 skill metadata headers unchanged from the previously validated baseline. `git diff --check` passed. No application tests apply |
| Integrated commit | `e8b156a8e306bd5af993b9b6108ceea6c8810aaa`, confirmed on `master` 2026-10-27; committed by owner after the documentation task |
| Next action | None for FL-000; implementation of the documented product features remains separate |

## Integrated configuration awaiting activation

| Field | FL-001 |
|---|---|
| Owner / executing agent | Project owner / main agent, approved agent-configuration bootstrap |
| Base commit / current branch | `e8b156a8e306bd5af993b9b6108ceea6c8810aaa` / `master` |
| Worktree | Existing primary worktree; no application implementation delegated |
| Approval | Owner approved 10 specialists plus orchestrator; Astra xhigh, Terra low, Sonnet medium, Sol high on 2026-10-27 |
| Integrated version | `0.2.0`, development-agent configuration |
| Required checks | YAML/schema, 11 profiles/model tiers, tool/role boundaries, routing cases, links, version consistency, whitespace and host activation |
| Verification evidence | 2026-10-27: 11 YAML profiles/model tiers/tool boundaries, 12 routing cases, 143 local links, 13 backlog IDs/acyclic dependencies and version metadata passed static checks. VS Code reported no agent-file diagnostics; `git diff --check` passed. Actual model/effort/tool activation not yet run |
| Integrated commit | `35ed5d2`, confirmed on `master` 2026-10-27; committed by owner after the configuration task |
| Next action | Confirm selected-profile/model/effort/tool activation before real delegation; do not mark DA-7 passed from Git evidence alone |

## Completed skill integration record

| Field | FL-013 |
|---|---|
| Owner / executing agent | Project owner / main agent, approved skill configuration only |
| Base commit / current branch | `35ed5d2` / `master` |
| Worktree | Existing primary worktree; owner subsequently committed the skill and approved ignore-rule correction |
| Approval | Owner approved Blender skill/workflow only on 2026-10-27; setup and actual assets deferred |
| Integrated version | `0.3.0`, new offline authoring skill |
| Required checks | BA-1 through BA-4: skill metadata/links, unchanged agent model tiers, authoring/export/failure guidance, scoped changes and release consistency |
| Verification evidence | 2026-10-27: BA-1 through BA-4 metadata/content/scope checks passed; 8 skill headers, 11 unchanged agent model tiers, 2 new routing cases, 158 local links, 14 backlog IDs/dependencies and version records checked. `git diff --check` passed; skill files are Git-visible. No Blender installation/asset/export/render checks performed |
| Integrated commit | `88b177e`, confirmed on `master` 2026-10-27; committed by owner after the skill task |
| Next action | None for FL-013; choose/pin Blender and run real export/consumer checks only in a separately approved asset task |

FL-013 is preparation-only and does not depend on running Blender or activating
FL-001. Actual asset execution uses the normal scheduling gate and an approved
FL-007 equipment slice; this skill does not silently add a Blender dependency to
all equipment reconstruction.

## Data-first planning checkpoint

**Owner hold, 2026-10-27:** do not advance architecture/specification changes or
application implementation until all essential data for the intended project is
accessible and its required coverage has been checked. Acquisition, access
diagnosis and evidence-coverage verification may continue. This overrides earlier
permission in the plan to advance source-independent slices while G1 is blocked.
Partial mirrored files and metadata inventories do not release this hold.

At the initial discovery checkpoint, FL-002/FL-014 were both blocked. Discovery inspected public documentation,
license clauses, SODIR identities and a checksum-verified metadata catalog. The
expanded 33-file pilot candidate list has no acquired pilot bytes/hashes. No application
tests or provider calls were produced. The later architecture package below
completes FL-014's document deliverables without claiming pilot acceptance.

Owner confirms no prepared data, indie/public-repo/three-minute-video requirements,
local WSL/container execution, and a ready Meta key with public-data processing
permission. Official sample access requires owner action; no account, terms
acceptance, cloud resources or paid model usage were initiated. Proposed cohort
and acquisition limits remain unapproved. The owner subsequently signed in; the
installed catalog exposes only `information_schema`, while the advertised volume
returns missing-schema 404. Provider details return ownership 403. No upgrade,
reinstall or access-policy change was attempted.

The equipment follow-up inspected 3 public mirrored WITSML files (7,776 bytes),
8 components and 4 bore sections. Dimensions are present, but drilling assembly
labels, missing installation context and unresolved MD/TVD references prevent
using them as verified pilot completion state. The report adds EDM/WITSML priority
and proposed DF-9; FL-002 is not closed by this structural sample check.
Further public-source searches found secondary report extracts, not the missing
original completion PDF. A downstream "Completion Report" label conflicts with
its drilling-report header. The equipment-source assessment is complete with a
conditional verdict; source access and pilot acceptance remain blocked. The
report records the privileged catalog/share checks needed without assuming a
paid upgrade or changing permissions.

Initial static checks passed: 22 unique candidate paths matched catalog file rows; unknown
bytes/hashes remain blank; 86 local documentation links, 15 unique backlog IDs
with acyclic prerequisites, candidate version agreement and `git diff --check`.
After the equipment follow-up, checks passed for 33 exact candidate paths,
95 local links, all 15 backlog IDs/dependencies, DF-1 through DF-9, version
agreement, the three source hashes and `git diff --check`.

Documentation handoff candidate: `0.3.1` (patch; no API/schema behavior change).
Subsequently integrated by the owner in `4ae7f7b`; the data audit remains blocked.

## Historical architecture package handoff (October 27)

FL-014 now has a selected modular-monolith stack/process model, typed shared
contracts, complete feature specifications, requirement-to-test traceability,
24 explicit scheduled tasks and bounded parallel worktree/resource assignments.
Design documents are complete, while package/runtime, pilot and live-model
qualification remain future execution tests. No application code or feature
approval is inferred.

The plan removes the unnecessary full-data/full-provider prerequisite from
foundation and synthetic engineering/history/adapter slices. Native pilot import
and full-demo acceptance still require real evidence. Source-first inspection
findings inform the architecture rather than becoming fabricated source mappings.

The owner integrated this initial package in `4ae7f7b`, then reopened its
requirements. FL-014 is now `blocked` on the owner's essential-data gate: address data acquisition,
project/categorized uploads, composite-asset reconstruction, the Meta harness and
UI-verifiable increments one by one. The old DAG is not authorization to start
implementation before those design changes are agreed.

Documentation validation on 2026-10-27 passed: 185 local Markdown links;
24 unique tasks with an acyclic dependency graph and six phase goals; 15 valid
acyclic backlog parents; 10 new feature/API spec structures with 84 unique
acceptance criteria across the new and retained data/history specs; all 10 project
ACs traced; independent source-free lanes and optional-asset exclusion checked.
All 13 new design documents passed table/fence/whitespace checks; fixture arithmetic,
EST deadline offset, pending version consistency and `git diff --check` passed.
This validates the documents, not the planned application tests.

## Historical acquisition follow-up and architecture reconsideration

The pinned public production workbook and daily-report conversion are now local,
outside Git, with hashes and source provenance. The workbook has 15,634 daily
rows across seven labels. The report corpus has 1,759 unique records, including
402 under F-12/F-14/F-5. Selected records show production-completion operations
and actual perforation firing; they also demonstrate an F-14 report discussing
F-12 equipment. Cross-document subject attribution is therefore a real source
requirement, not just a hypothetical architecture concern.

These findings narrow the source gap but do not close FL-002: original access,
full geometry, units/datum reconciliation, complete history and sample approval
remain open. Points 2-5 of the owner's reconsideration are not yet resolved.
At that checkpoint the documentation handoff candidate was `0.3.2`, patch;
no application implementation, paid API call or accepted pilot is claimed.

Further acquisition added four mirrored F-5 actual-trajectory section XMLs and
their mapping file (542,300 bytes). Hash/unit/station checks passed, but overlapping
samples differ and physical references remain unverified. Verified acquired files
and provenance now have durable copies under Git-ignored `data/volve/source-audit/`;
session originals were preserved. The current listing's 90-day installation
policy and the May 27 installation make expired access a concrete hypothesis.
No authorization to reinstall was received and no account changes were made.
The [essential-data coverage table](VOLVE_DATA_DISCOVERY.md#7-f-5-trajectory-acquisition-and-essential-data-coverage)
remains incomplete; neither FL-002 nor the owner hold is released.

The subsequent October 27 recovery attempt is also blocked at browser login:
the existing workspace displays "Signed in to a different account", including
when its original workspace-scoped URL is used. Correct-account sign-in is now
a prerequisite to testing the expiry hypothesis; reinstall authorization still
has not been received. No account or catalog modification was performed.

### Owner-supplied local dataset: superseding access checkpoint

The owner subsequently shared a working volume in another workspace and supplied
the local official download. A complete metadata walk found 33,678 files,
48,121,671,122 bytes and all 33 candidates. The [content audit](VOLVE_DATA_DISCOVERY.md#8-owner-supplied-local-data-content-audit)
verified actual survey records, formation/depth surfaces, a seabed block, log
curves, production and original operational evidence. It also found mislabeled
completion documents, undated pilot interval rows and mixed DEPTH/TIME blocks
inside the nominal seabed file. Earlier access/reinstall questions are no longer
the reason for holding local work. FL-002 is `in_progress`, not done; the
engineering manifest and owner acceptance remain open, and FL-014 stays on hold.

The focused completion audit confirms an F-14 AS INSTALLED schematic with actual
safety-valve, PBR and packer OD/length/MD. Its reference/date conflicts are explicit.
The exact remaining F-12 source lead is the **29-01-2008 As Installed completion
tally**, referenced in 2016 plug logs but not located in inspected documents.
F-5's correct completion Word report exists; its embedded schematic images remain
unverified. Do not equate these extraction/qualification tasks with missing
seismic or an inaccessible official release.

## Assignment record for each active feature

October 28 planning handoff: new FL-015/016 specs, source/model context contracts,
early evidence/chat/reconstruction UI checkpoints and 31-task DAG. Integrated by
the owner in `a4bf9ee`, version 0.3.2. No new feature is ready/done, no
implementation branch is assigned, and no paid model call is implied.

Documentation checks passed on October 28: 26 Markdown files, 188 local
links/headings, table/fence structure, 31 unique tasks and six goals with an acyclic
DAG, 17 backlog items with acyclic parent prerequisites, and all 12 project ACs
traced. Early source/chat/reconstruction and chart paths do not wait for 3D;
all mandatory tasks reach release and optional Blender does not block it.
The 18 new PW/RC criteria are binary-testable; these are specification checks,
not executed application tests or evidence of live agent performance.

### Focused target follow-up after the 0.3.2 integration

Owner-requested source inspection resumed on October 28. F-5's embedded Existing
completion table now provides visually checked valve/packer/sealstem/muleshoe
dimensions and MD. The F-12 tally remains unlocated after an expanded bounded
search; F-11 B's genuine final report contains a dimensioned table marked Plan.
Actual perforation records exist for all three proposed targets. F-14's six
initial intervals and F-5's first five match the static table exactly; F-5's
2016 additions and F-12's contradictory 2014 summary show why historical
reconciliation is still required.

Evidence and checks are in the [equipment follow-up](EQUIPMENT_DATA_FEASIBILITY.md#10-target-qualification-and-history-follow-up-october-28)
and ignored hashed audit sidecar. FL-002 remains `in_progress`; neither a complete
third equipment tally nor final G1/owner cohort acceptance is claimed.
Documentation-only handoff candidate: **0.3.3**, pending integration. No runtime
API/schema change, commit, push or application implementation is part of this task.

### Cohort confirmation and implementation-planning handoff

The owner then selected F-12/F-14/F-5, accepted the documented F-12 generic
limitation and requested warning/error visibility. A structured clarification
confirmed hybrid labels, review/publication and upload byte/file limits.
The backlog now includes FL-017, a 32-task DAG and detailed foundation/project/
upload packets with ownership, resource isolation, tests and stop conditions.
No G1/G2/G3/G5 result, active worktree, runtime or live call is implied.
This extends the same unintegrated **0.3.3** documentation patch; do not allocate
another version merely because the planning work spans multiple turns.

Documentation checks passed: 23 Markdown files, 208 local links/headings, table/
fence structure, the acyclic 32-task/18-item graphs, all 12 project acceptance
rows, DQ-1..8/EQ-7 traceability and 19 initial packet steps. All mandatory tasks
reach the release gate; optional Blender is not a prerequisite. Early project/
upload work is independent of final G1 and live Meta checks. Whitespace validation
passed. These are document checks, not application, parser or provider tests.

### First-packet execution approval and activation blocker

The owner authorized the first three implementation handoffs on October 28 at
11:19 EDT. Approved specification base:
`9d630e32af898cdc9292451b5258f9c2f9a1a06d` (owner-integrated 0.3.3).

- Foundation branch: `feature/fl-004-a-foundation`.
- Worktree: `/home/slimco/code/FieldLens-worktrees/fl-004-a-foundation`;
  created at the exact approved base and verified clean after activation.
- Reserved lane: API `8101`, Vite `5174`, DB service `127.0.0.1:55432`.
  Ports were free; no application/database service was started. Planned database
  `fieldlens_fl004a_w1` and task-scoped roles are not yet provisioned.
- Host checks: Python 3.12 via uv 0.11.20; Node 20.11.1/npm 10.2.4.
  Node 24 remains approved user-managed foundation setup, not an installed runtime.
  Docker client 26.1.3/server 29.8.2 and Compose 5.6.0 respond.
  Host reports 7.6 GiB RAM and 162 GiB filesystem space available.
- Runtime evidence confirms main `gpt-6-astra/xhigh` and both activation calls
  `claude-sonnet-5.5/medium`; the required profile is discovered.
- **DA-7 BLOCKED:** the backend worker cannot access `apply_patch`, `create` or
  `edit`. Its focused tool search found no general file editor. Shell-write
  workarounds and model substitutions were not authorized or attempted.
  No application implementation handoff was issued.
- Initial synchronous activation cannot receive follow-up messages. The narrower
  background capability probe is idle:
  `1bee9e93-5d7f-4f58-a94a-3d2f62a5c4eb`. Resume only after editing tools are exposed;
  verify a create/delete smoke in the assigned worktree before authorizing code.
- SDK-reported development usage: initial probe 75,359 total tokens / 3 tool calls;
  focused probe 73,796 / 1. These aggregate counts are not billed-cost estimates;
  no cache/billing breakdown was captured. Meta application calls/spend: none.

The owner/host must restore worker file-edit capabilities. Keep the clean worktree;
do not fan out more workers or mark TASK-001/003 complete. Projects/uploads remain
dependent on verified foundation integration. No credentials or attached secret
snapshot were read.

Read-only diagnosis after the owner's follow-up: Astra is this main orchestration
chat, not an implementation worker. Both worker probes used Sonnet. A Git worktree
does not create another WSL installation or Copilot/MCP environment. Parent and
worker tool search used the same client tool registry (247 available client tools);
MCP/extension tools were discovered, so this is not a blanket loss of all tools.
The backend profile has no `tools` restriction, host `modelCapabilityOverrides`
is empty, and the installed host's default native-tool allowlist includes
`create`, `edit` and `apply_patch`. Runtime version: `1.0.23-preview.5`.
The observed failure is therefore at worker editing-tool exposure, not missing
worktree packages or a verified user-disabled editor. The exact SDK registration/
model-filtering cause is not yet isolated. No host configuration was changed;
adding arbitrary profile allowlists or switching implementation to Astra is not
an established fix.

At the owner's 12:03 EDT request, explicitly declared
`tools: ["*", "edit", "create", "apply_patch"]` in the backend profile in both
checkouts. The wildcard preserves the intended complete tool set. A fresh task
invocation (`explicit-tools-smoke`, Sonnet 5.5/medium) still had no file editors,
but the decisive host record at 16:04:57 UTC reported `tools: null`, not the
updated declaration. Therefore this invocation did not validate the explicit
configuration; stale/unrefreshed profile configuration remains a concrete blocker.
The experimental declaration is retained for a fresh-session test. The worktree
now has only that intentional profile edit; no smoke file/application code exists.
Probe usage: SDK-reported 36,137 total tokens, zero tool calls.

Quick upstream checks found [agent hot-reload issue 3106](https://github.com/github/copilot-cli/issues/3106),
[child MCP scoping issue 5191](https://github.com/github/copilot-cli/issues/5191)
and [built-in-tool regression 5243](https://github.com/github/copilot-cli/issues/5243).
The latter names SDK 1.0.23-preview.5, but its same-turn exit-plan condition does
not match this probe; none proves the precise underlying editing defect here.
Next: fresh Copilot conversation, confirm the explicit list in host metadata,
then repeat the bounded editing smoke. Do not equate another cached invocation
with a valid explicit-configuration test.

### Fresh-session restart attempt, October 28

The owner requested resuming the handoff in a fresh conversation at 13:06 EDT.
One bounded `fieldlens-backend` preflight (`foundation-restart-preflight`) ran
against the existing foundation worktree; no implementation was dispatched.

- Host events confirm `claude-sonnet-5.5/medium`, selected from the agent
  definition default. The worker executed `bash` and tool search; this is not
  a loss of all tools. Its `view` call required a narrower range, so the worker
  did not complete reading the worker contract.
- The worker still reported no `apply_patch`, `create` or `edit`. One focused
  search found no general plain-text editor. The create/read/delete smoke was
  not run; no smoke file was created and no shell-write workaround was used.
- The explicit tool declaration remains in both checkouts. The inspected
  fresh-session configuration event records model/effort but no tool list, so
  activation of that declaration remains unverified, not proven fixed.
- Parent verification confirmed branch `feature/fl-004-a-foundation`, approved
  HEAD `9d630e32af898cdc9292451b5258f9c2f9a1a06d`, only the existing backend-profile
  modification, and absence of the smoke file. All primary-worktree changes
  from the previous session were preserved.
- The new session's start event records `gpt-6-astra/medium`, not the required
  `xhigh`. The earlier session's Astra/xhigh evidence does not establish this
  session's configuration; reconfirm the main-session selection before dispatch.
- Probe usage: SDK-reported 75,378 total tokens, 3 tool calls, 10,106 ms.
  No monetary cost or cache breakdown is inferred. No installs, services,
  application code, commits or Meta calls were made.

DA-7 and FL-004 remain blocked. Next: restore actual worker editing-tool exposure,
confirm the required main-session effort and effective worker tool configuration,
then complete one bounded create/read/delete smoke and the worker-contract read
before dispatching the approved foundation packet. Do not repeat unchanged
probes or start dependent project/upload workers.

### Owner-approved serial checkout handoff, October 28

At 14:47 EDT the owner replaced parallel worktree execution with one feature at
a time, each on its own branch, using subagents launched from the main
orchestrator session. This is an approved scheduling amendment, not evidence
that changing checkout location fixes host tool exposure.

- Active checkout: `/home/slimco/code/FieldLens`.
- Active branch: `feature/fl-004-a-foundation-serial`, created from
  `9d630e32af898cdc9292451b5258f9c2f9a1a06d`; integration target remains `master`.
- The existing `/home/slimco/code/FieldLens-worktrees/fl-004-a-foundation`
  allocation is inactive and preserved, including its profile edit. No removal,
  reset, stash or forced branch reuse is authorized.
- All eight pre-existing modified files were preserved on the new branch.
  The backend profile now declares `[vscode, execute, read, edit, search, web]`;
  this owner-supplied setting is preserved, not treated as verified tool exposure.
- One active writer, including the orchestrator; no branch switches while
  workers/checks/helpers are running. No worker edits global release/backlog
  metadata or another checkout. Keep task-scoped databases, ports and output roots.
- Approved order remains foundation -> project lifecycle -> uploads/jobs, with
  integration and acceptance gates between features. Independent DAG tasks are
  queued, not additional parallel workers.
- The governing workflow, agent contract and implementation packets now reflect
  this amendment. Changes are pending, not committed/integrated; no final version
  or foundation acceptance result is claimed.
- Next: one bounded same-checkout backend editing smoke, verify actual
  model/effort/tools, then dispatch only if DA-7 and the foundation prerequisites
  pass. On failure retain the allocation and report the exact blocker.

Serial preflight result at 14:50 EDT: **DA-7 still blocked**. Host metadata
confirms main `gpt-6-astra/xhigh` at 14:47 and worker `claude-sonnet-5.5/medium`
from its profile default. The worker successfully read the bounded contract and
ran the branch/base/status check in the shared checkout. Its exposed tools
included read/execute/search-by-file, but no plain-text editor or tool-discovery
function. The create/read/delete smoke was therefore not run; no file was created
and no shell-write workaround used. Parent verification confirmed unchanged dirty
paths, absent smoke file and untouched legacy-worktree profile modification.
Changing checkout location did not restore editing capability in this probe.

Probe usage: SDK-reported 18,112 total tokens, 2 tool calls, 11,111 ms; no billed
cost estimate or Meta application usage. Documentation checks passed:
`git diff --check`, 192 local file links across 16 changed Markdown files,
11 profile required-header/body-size checks, and a targeted scan for obsolete
parallel-dispatch directives. These are not application or full YAML/schema tests.
No implementation, commit, version bump or service startup was performed.
Next: owner decision on an explicit patch-return handoff (worker authors changes,
orchestrator applies them with its editor) versus pausing until worker tools are
repaired. That alternative is not yet approved and does not silently waive DA-7.

The owner questioned patch-return token overhead and requested configuration
diagnosis instead; patch-return remains unapproved. Read-only inspection found
no model tool overrides in either WSL or Windows agent-host configuration
(`modelCapabilityOverrides: {}`). The installed host's native allowlist contains
`view`, `bash`, `create`, `edit` and `apply_patch`. Repository-local VS Code
settings and repository Copilot/Claude permission-settings files are absent;
the inspected user settings do not explain the missing editors. The current
backend profile includes the documented Copilot `edit` alias. This narrows the
unresolved failure to effective tool exposure rather than proving a filesystem
or worktree-permission issue; runtime/model-specific filtering remains a
hypothesis, not an established root cause. No settings or permissions were changed.

### Foundation implementation and independent acceptance

- Recreated `fieldlens-backend` without an explicit tools list: runtime exposed
  create/edit/discovery and implementation writes succeeded. Host events confirm
  Sonnet 5.5/medium on the recreated-profile probe and implementation launch.
  Global `ai-team-dev` and local `fieldlens-task` comparisons also exposed editing
  tools. Stale profile caching is a hypothesis, not a proven root cause.
- Main-session model switched to Sonnet/medium for diagnosis/initial dispatch;
  host metadata confirms return to Astra/xhigh at 16:59 and 17:12 EDT.
- Implementation candidate is `3c1d2b285fc8588d32407977d4f27bf921f0d51f` on
  `feature/fl-004-a-foundation-serial`; master remains `9d630e3`.
  Worker-reported checks and main-agent exploratory checks are not independent
  acceptance. The original handoff omitted required documentation and did not
  complete the delivery cycle.
- Independent `fieldlens-qa` invocation `79267169-ed0c-402f-9867-025fbdb90fe3`
  used host-confirmed Sonnet 5.5/medium and a clean frozen candidate. Verdict:
  **FAIL**. Existing 84 backend and 3 UI tests, lint/type/build/contracts and
  independent real migration/readiness/Retry checks passed; SC-2/SC-5 and required
  documentation failed, with further boundary/focus/version defects. The full
  [remediation list](specs/FOUNDATION.md#independent-qa-and-bounded-repair-allocation)
  owns D1-D11/B1. No feature or checkpoint is marked verified.
- Native Playwright browser installation returned explicit Ubuntu 20.04 support
  errors on two attempts. VS Code integrated-browser checks work. Repair the
  required CLI gate with the version-matched, test-only browser container;
  do not call either route equivalent to an unrun test.
- QA left the candidate clean, stopped its helper APIs/Vite and dropped its
  test databases. The owner preview remains on 8101 with the allocated foundation
  PostgreSQL service on loopback 55432. Stop branch-bound helpers before merge.
- The QA handoff reports 6,963 seconds elapsed, exceeding the requested
  35-minute checkpoint. Future repair/re-verification turns must return at their
  bound; the excess is not an accepted new time allocation. Development usage
  cost is unavailable here; no Meta application spend is claimed.
- Next: same backend owner repairs this slice, then the same independent QA
  verifies the new frozen candidate. Finalize one minor version only after gates
  pass, commit/merge into master, verify integration and reconcile this ledger.
  No push, next feature or worktree switch is authorized by a passing subset.
- Schedule: October 28's projects/uploads checkpoint A has not been reached.
  Foundation is a prerequisite, not a substitute; retain the gate and rebaseline
  scheduling after this acceptance cycle rather than claim unmeasured slack.
- Repair worker `05eb0074-fd9b-4bdf-b353-025224b93969` selected backend
  Sonnet 5.5/medium at base `923b1bf`, but exposed neither `apply_patch`, `create`
  nor `edit`. One bounded inventory/discovery follow-up confirmed the absence.
  No application writes, image pulls or tests ran. The original implementation
  handle was no longer available, so this was a fresh same-profile repair worker.
  Tool exposure remains session/invocation-dependent; its root cause is unproven.
  Main stopped the 8101 preview before repair; the foundation DB remains running.
  Current blocker: restore native editors or authorize a temporary known-working
  agent/model route. No fallback or merge has been performed.
- At the owner's request, the backend profile was deleted and recreated without
  a `tools` field, retaining its name/model/effort/body. A fresh invocation still
  exposed no `apply_patch`, `create` or `edit` and stopped before any smoke write.
  Recreating the file is therefore not a reliable unblock in this session.
- Owner then switched the main model and instructed it to fix the foundation
  directly, without any subagents. The main implemented regression tests first:
  29 contract/isolation counterexamples and Retry-focus initially failed.
  Repairs now pass 124 backend, 4 UI and 3 actual Playwright CLI E2E tests plus
  affected checks. No new subagent was invoked for these repairs.
- Docker Desktop's host network was not WSL loopback. The reproducible browser
  setup now publishes only 127.0.0.1:9323 and tunnels only loopback destinations;
  the Noble image matches Playwright 1.64.1. Native Ubuntu 20.04 installation is
  not retried and integrated-browser success is not substituted for the CLI.
- VERSION is 0.4.0 on the repair candidate; master is still 0.3.3. Required code
  and operational gaps are repaired, but the main's direct checks are not a
  separate-agent PASS. Resolve the acceptance exception before merge; do not
  invent an independent verdict or mark the feature done early.
- The owner selected `merge-direct-exception`: accept direct verification for
  TASK-003 only and merge 0.4.0 now; retain independent QA for future features.
  Tested repair commit `95da2b74df949e080cb4cc57dd7a2f5cb7df9783` has a clean
  tree and passing full relevant checks. API/Vite/browser helper listeners are
  stopped before the branch switch; the allocated persistent DB remains healthy.
- **Integration confirmed:** `master` fast-forwarded from
  `9d630e32af898cdc9292451b5258f9c2f9a1a06d` to
  `1293f554e6371f5e38a27de697361d678f5850a9`. Tested repair
  `95da2b74df949e080cb4cc57dd7a2f5cb7df9783` is an ancestor, and backend,
  frontend, scripts, infra, manifests/locks and VERSION are byte-identical to
  that tested candidate. Only acceptance/release documentation followed testing.
  Version is 0.4.0; this ledger reconciliation is part of the same integration,
  not a second release/bump. No push/tag or next feature/worktree was started.

Add a record when scheduling, not speculative branches or fake test results:

```text
ID / approved spec / scope:
Status / blocked reason / resume state:
Prerequisite IDs and integrated hashes:
Configured agent / base commit / branch / absolute checkout:
Complexity-risk rationale / model and effort / actual host-selection evidence:
Owned files and shared contracts:
Database/ports/Compose project / budget reservation:
Acceptance checks and evidence location:
Time/tool/attempt bounds / elapsed time / exposed usage:
Proposed bump / compatibility rationale / release note:
Tested commit / integrated commit / final version:
Next action / cleanup status:
```

Keep cancelled or superseded items with rationale. Newly discovered scope is a
new item or an owner-approved spec revision, not a hidden addition to another
agent's work. Record verified test evidence in the feature spec; link it here.

### TASK-071 · Project deletion with all records and documents (PW-9)

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P1 |
| Tags | backend, frontend |
| Depends on | none |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/PROJECT_DELETION.md |
| Version | 0.35.0 |
| Parent | FL-016 |
| Slice | FL-016-D |

**Outcome.** Typed-name-confirmed `DELETE /api/v1/projects/{id}`: cancels in-flight work, deletes the project's stored files and every project-scoped row through a crash-resumable purge (immutability guards stay enabled, allowed only for the purged project), keeps the spend ledger, and a sidebar dialog with counts, progress and retry. Completeness test over every table with `project_id`. Migration `0015`.
**Next action.** None. Follow-ups: running extraction runs are marked superseded and waited on, not cancelled mid-run; a genuinely running job was not caught mid-run in QA.
**Evidence.** QA-071 PASS after two repair rounds (nav e2e regression, dialog trap, focus, failed wording, shell.spec assertion) and an integration pass on top of 0.34.0 (migration 0015 re-chained onto 0014; purge honors the storage-root identity guard; 1357 backend tests, 216 Vitest, e2e 29 passed with only the known UI-2/UI-10 failures); merged `2e6fe9b`, release 0.35.0.

### TASK-072 · Re-processable, observable model processing; inline project delete; provider configuration visibility

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, frontend |
| Depends on | TASK-055, TASK-071 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/MODEL_PROCESSING_OUTCOME.md |
| Version | 0.37.0 |
| Parent | FL-022 |
| Slice | FL-022-F |

**Outcome.** Owner manual check of 0.36.0 (2026-11-02): inline project delete icon; model re-process available in every state (forced fresh read through estimate -> confirm, cache reuse opt-in); run history, provider/model, tokens/USD and the raw model reply visible per document; a stub run is labeled as such; a misconfigured live provider is reported (409 `provider_misconfigured`) instead of silently stubbed; unprefixed `PROCESSING_*` keys in `.env` are warned about and the prefixed names documented. Migration `0017`.
**Next action.** Follow-ups D1-D3 are tracked in TASK-073. Live Meta processing remains unverified (needs owner authorization).
**Evidence.** Independent QA (fieldlens-qa) PASS on candidate `46565d8`: backend 1450 passed, ruff/mypy/contracts clean, Vitest 269, build ok, e2e 32 passed with only the known UI-2/UI-10 `shell.spec.ts:285` failures at 1920/2560; /ready 200 on fresh process; purge complete; inline delete verified at 1280/390 px; e2e and default tests pinned to stub. Stub/mocked only; no live Meta call.

### TASK-073 · Model processing panel polish (QA follow-ups D1-D3 from TASK-072)

| Field | Value |
|---|---|
| Type | task |
| Status | ready |
| Priority | P1 |
| Tags | backend, frontend |
| Depends on | TASK-072 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/MODEL_PROCESSING_OUTCOME.md |
| Version | none |
| Parent | FL-022 |
| Slice | FL-022-G |

**Outcome.** (D1) An abandoned re-process estimate must not regress the panel to "Not started": derive processing status from the latest started run. (D2) A stub run must not display a "Cost (actual)" figure; show it as illustrative or hide it. (D3) With a misconfigured provider, the chip/headline must not say "model processing available" while the action is disabled.
**Next action.** Owner-approved scope pending; small single lane.
**Evidence.** none yet

### TASK-074 · Live processing blocked by unconfirmed budget balance, with the cause hidden

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, frontend |
| Depends on | TASK-072 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-03 |
| Sprint | Hackathon |
| Spec | specs/MODEL_PROCESSING_OUTCOME.md |
| Version | 0.37.1 |
| Parent | FL-022 |
| Slice | FL-022-H |

**Outcome.** Owner live test of 0.37.0 (2026-11-02): every Process with model run failed `provider_error: provider_unavailable` with no usable cause. Root cause: the `processing-live` budget period has `starting_balance_usd` NULL (balance confirmation is an owner ledger action that nothing offered), so `BudgetLedger.reserve` raises `ProviderUnavailable("starting balance is not confirmed")` before any call; `map_failure` then drops the reason. Owner decision: no owner step; the user's manual confirm in the UI is the spend authorization. Fix: (1) the `processing-live` period balance is auto-confirmed (= ledger cap) when the live runtime is built, also repairing a NULL-balance period; other periods untouched; (2) failure message/outcome and one server log line carry the safe ledger reason; (3) `FIELDLENS_PROCESSING_RUN_CAP_USD` is optional; total cap (5 USD), per-call reservation and page limits remain.
**Next action.** Low-severity gap: an unrecorded pricing revision surfaces as an IntegrityError step error rather than the stated reason (only reachable by manual row deletion). Owner restart required.
**Evidence.** Independent QA PASS on `bb0a4f8`: backend 1458 passed, ruff/mypy/contracts clean, npm gates clean, vitest 269 (one unrelated flaky `sources-slim` test seen once); concurrency and idempotency checked. Fake-provider only; no live Meta call, no e2e or browser run.

### TASK-075 · Model processing: user-chosen pages, estimate from real text, no spend gates

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend, frontend |
| Depends on | TASK-074 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/MODEL_PROCESSING_OUTCOME.md |
| Version | 0.39.0 |
| Parent | FL-022 |
| Slice | FL-022-I |

**Outcome.** The estimate is computed from the selected pages' real text with the runner's bound, the user picks the page count (default min(5,total)), large selections run in chunks, and no total/run cap or remaining budget applies to a confirmed manual run (spec section 8). A retry gets reservation headroom (bound x attempts) and a recovered retry never fails the run on cost.
**Next action.** Known gaps: `pages_done` counts a failed chunk (cosmetic); the reconstruction dialog's remaining-budget row is removed by TASK-076; the 10 pages/call value needs a bounded live check.
**Evidence.** Independent QA (two passes) PE-1..PE-7 PASS; D1-D3 and N1 fixed and covered by tests (processing/assistant/contracts 313 passed after the last fix; earlier full suite 1515 passed with one stale-venv version test); ruff, mypy strict, frontend lint/typecheck/vitest/contracts/build clean. No e2e run for the document dialog beyond the earlier model-processing spec (2/2). Fake provider only; no live Meta.

### TASK-076 · Reconstruction stages S2 read / S3 match wellbores, merge UI and plain-language modal

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | rag, backend, frontend |
| Depends on | TASK-055, TASK-057 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/WELLBORE_ASSET_GENERATION.md |
| Version | 0.40.0 |
| Parent | FL-023 |
| Slice | FL-023-A |

**Outcome.** Wires the document read and the TASK-057 merge guards into reconstruction so aliases of one wellbore become one file group (revertible), adds the merge review UI (absorbs TASK-065) and rewrites the stage modal.
**Next action.** Live S2/S3 need one bounded authorized live run (never run against real Meta yet); S5 stays "not available yet" until TASK-079. Known: dialog chip still says "Stub: no model is called" (wording differs from run label); a cancelled S3 does not store the first paid call's proposals.
**Evidence.** Independent QA: AG-1 (backend), AG-2, AG-3 hook rollback, concurrency/scope PASS; D1 (S3 re-spend), D2 (S2/S3 never live), D3 (e2e wait) fixed and re-verified (S3 0 new calls on unchanged reruns, 4 concurrent runs 1 call, cancel honoured). Implementer full backend suite 1534 passed, ruff, mypy strict, frontend 278 vitest, lint/typecheck/contracts/build, single e2e reconstruction-merge PASS. Fake providers only; no live Meta.

### TASK-077 · VisualAssetSpec contract, validator, persistence and stub designer

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | backend |
| Depends on | TASK-041 |
| Assignee | agent:fieldlens-backend |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/WELLBORE_ASSET_GENERATION.md |
| Version | 0.38.0 |
| Parent | FL-023 |
| Slice | FL-023-B |

**Outcome.** Typed declarative asset spec (registered primitive kinds incl. surface facilities, MD/unlocated/surface placement, mandatory labels, evidence, illustrative label), server validation, per-wellbore revision history (latest valid is current, no accept step), migration 0019, fixtures, stub designer.
**Next action.** Wire `service.invalidate_current` into TASK-076 merge/revert; live designer is TASK-079.
**Evidence.** Independent QA PASS at 4ca5f2b (three low defects found and fixed, re-verified); backend 1506 passed with 4 env-induced processing failures from the exported Meta variables (not touched by this lane); ruff, mypy strict, check:contracts clean. Stub designer only; no live Meta.

### TASK-078 · R3F foundation, primitive library and single-wellbore 3D view

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend, 3d |
| Depends on | TASK-077 |
| Assignee | agent:fieldlens-3d-motion |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/WELLBORE_ASSET_GENERATION.md |
| Version | 0.41.0 |
| Parent | FL-023 |
| Slice | FL-023-C |

**Outcome.** First 3D in the app: trajectory tube, parametric primitives from a spec, picking with evidence inspector, draft preview, keyboard list, disposal discipline.
**Next action.** Real survey trajectory is not wired (vertical placeholder labelled "trajectory unavailable"); field view (3+ wellbores, AG-8 measurement) is TASK-080; only SwiftShader frame stats measured, no hardware GPU, heap or tab-switch leak measurement yet.
**Evidence.** Independent QA (two passes, Node 24): lint/typecheck/vitest 304/build/check:contracts PASS; no WebGLRenderer in main chunk (lazy 968 kB Viewer3D); single scene-render e2e 3/3 (rich 2.1 ms mean, 139 draws, 67k tris on SwiftShader); AG-6, AG-7 PASS; default view opens on the wellhead with surface equipment, 5x exaggeration for deep wells, 'Fit whole well' toggle (QA defect D1 fixed and re-verified); keyboard roving focus/Enter select verified. Fixtures only; no live provider.

### TASK-079 · S5 live asset designer with bounded visual-reference research

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | rag, backend |
| Depends on | TASK-076, TASK-077 |
| Assignee | agent:fieldlens-rag |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/WELLBORE_ASSET_GENERATION.md |
| Version | 0.43.0 |
| Parent | FL-023 |
| Slice | FL-023-D |

**Outcome.** Agent stage that fills the spec from candidates and records; optional allowlisted web visual-reference tool; estimate and run history; fake provider by default.
**Next action.** S5 has never run against real Meta (needs the owner's authorization for one bounded live run); no real web-search backend is shipped (the research tool is OFF by default, pluggable, fakes only); the 20 s fetch budget is not configurable; a model-chosen kind can change a part's placement class (no numbers); a new run key repeats a paid call by design (confirmed run is the authorization).
**Evidence.** Independent QA (two passes): SSRF probe battery (about 55 URLs: private/loopback/metadata, IPv4-mapped, NAT64/6to4/Teredo/IPv4-compatible, numeric forms, redirects, rebinding, oversize, content type) all rejected after the D1 fix; slow-drip total time budget and in-flight cancel enforced (D2); prompt-injection and model-output abuse PASS (invented/duplicate refs, unknown kinds, evidence rules, no located part without a printed MD interval); refusal/truncation/malformed/provider failure leave the current spec untouched; supersede history and merge-hook invalidation PASS; MD-range check PASS; D3-D6 fixed. 440 backend tests (assetspec, reconstruction, merge_proposals, processing, contracts, foundation), ruff, mypy strict, frontend 304 vitest/lint/typecheck/contracts/build PASS. Fake providers only; no live Meta or web.

### TASK-080 · Field (multi-wellbore) 3D view with LOD and instancing

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P0 |
| Tags | frontend, 3d |
| Depends on | TASK-078 |
| Assignee | agent:fieldlens-3d-motion |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/WELLBORE_ASSET_GENERATION.md |
| Version | 0.42.0 |
| Parent | FL-023 |
| Slice | FL-023-E |

**Outcome.** All project wellbores in one scene, shared materials/instancing, fly-to and linked selection; measured frame time.
**Next action.** Positions are a labelled schematic grid (no validated coordinate API yet); each wellbore spec is fetched separately (fine for about 12 wells); browser Back does not return to the field view (in-app button does); unlocated components are not drawn in the field view; software-GL frame times only, no hardware GPU numbers.
**Evidence.** Independent QA (two passes): lint/typecheck/vitest 329/check:contracts/build PASS; no WebGL in main chunk, FieldViewer3D lazy (18 kB); AG-8 on software GL: 3 and 12 wellbores -> 7-8 draw calls, p95 0.3 ms, geometries/textures back to baseline after tab switch, no live WebGL contexts (probe canvases released); single field-view e2e PASS; QA defects M1 overview framing, M2 focused view, L1 empty-state wording, L2 probe release fixed and re-verified. Fixtures only.

### TASK-081 · Independent QA and bounded live acceptance of FL-023

| Field | Value |
|---|---|
| Type | task |
| Status | in_progress |
| Priority | P0 |
| Tags | qa |
| Depends on | TASK-079, TASK-080 |
| Assignee | agent:fieldlens-qa |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/WELLBORE_ASSET_GENERATION.md |
| Version | none |
| Parent | FL-023 |
| Slice | FL-023-F |

**Outcome.** Independent acceptance of AG-1..AG-10 and an owner-authorized live Meta run, reported separately from stubs.
**Next action.** Stub/fake-provider acceptance of 0.43.0 is done; the live Meta run needs the owner's authorization (proposal: one most-complete wellbore, a PDF of at most 5 pages, estimated USD 0.05-0.30, allowance cap about USD 1.00, isolated lane, never the app database). Defects D1-D5 are in TASK-082; D6 is TASK-083.
**Evidence.** Master 0.43.0 integrated QA (2026-11-03): backend 1585 passed, ruff/mypy strict clean, alembic single head with a clean downgrade/upgrade round trip, frontend vitest 329 and build clean, full Playwright 37 passed / 2 failed (stale shell.spec UI-2/UI-10 assertions, D4); cross-feature walk with the stub provider and synthetic fixtures PASS. Not verified: any live provider behaviour.

### TASK-082 · 0.43.0 final-QA polish: badge contrast, canvas role, focus return, stale e2e assertions, e2e storage root

| Field | Value |
|---|---|
| Type | task |
| Status | done |
| Priority | P1 |
| Tags | frontend, qa |
| Depends on | TASK-081 |
| Assignee | agent:fieldlens-frontend |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/WELLBORE_ASSET_GENERATION.md |
| Version | 0.43.1 |
| Parent | FL-023 |
| Slice | FL-023-G |

**Outcome.** Fixes the reproduced integrated-QA defects: illustrative badge contrast (D1), scene canvas role (D2), focus return after back-to-field and merge Accept/Reject/Revert (D3), stale shell.spec assertions (D4) and the e2e runner's stale storage root (D5).
**Next action.** None.
**Evidence.** Independent QA (two rounds; the first failed D5 as configured and a ruff format check, both repaired in 07e332b): frontend lint, typecheck, check:contracts, build and vitest 332 pass; ruff, format and mypy strict clean; tooling tests 170 pass; D1 contrast 7.48:1 (axe clean on the wellbore viewer and field view); D2 role="group"; D3 focus returns to the wellbore list item after back-to-field, and to Revert/proposal row after Accept/Reject/Revert; D4 shell.spec UI-2/UI-10 pass at 1920 and 2560; D5 reproduced with FIELDLENS_STORAGE_ROOT set and stale unmarked files, clean start, stale dir untouched, no temp leftovers; shell, field-view, scene-render, reconstruction-merge e2e 20/20. Note: one non-reproducible vitest flake in project-delete/sources-slim under load.

### TASK-083 · Real survey trajectory in the 3D views

| Field | Value |
|---|---|
| Type | task |
| Status | proposed |
| Priority | P1 |
| Tags | backend, geospatial, frontend |
| Depends on | TASK-078, TASK-080 |
| Assignee | agent:fieldlens-geospatial |
| Due | 2026-11-04 |
| Sprint | Hackathon |
| Spec | specs/WELLBORE_ASSET_GENERATION.md |
| Version | none |
| Parent | FL-023 |
| Slice | FL-023-H |

**Outcome.** The wellbore and field views draw the wellbore's real validated survey (deterministic min-curvature local offsets with CRS/datum and depth reference preserved) instead of the labelled vertical placeholder, through a read-only project-scoped route.
**Next action.** Needs a feature spec (route contract, CRS and datum handling, planned vs as-built, units, local render origin, field-view positions from validated coordinates) and owner approval; the engineering/trajectory module already exists.
**Evidence.** Found by integrated QA (D6): `trajectoryFor()` reads only a test hook, so every wellbore shows the labelled vertical placeholder even when trajectory stations exist.
