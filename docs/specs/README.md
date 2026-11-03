# Feature specifications and requirement traceability

Updated 2026-10-28. The owner confirmed the cohort/fallback and project/
reconstruction workflow defaults. Detailed packets/contracts still receive review
and a committed base before dispatch. **No application feature is implemented or
verified merely by appearing here.** Preparation approvals retain their status.
See [architecture](../ARCHITECTURE.md), [backlog](../BACKLOG.md) and the
[implementation sequence](../../plan/architecture-fieldlens-1.md).

## Feature index

| Backlog | Specification | Bounded increments / current execution gate |
|---|---|---|
| FL-001 | [Development agents](DEVELOPMENT_AGENTS.md) | Configuration integrated; actual host activation still unverified |
| FL-002 | [Data feasibility](DATA_FEASIBILITY.md) | Demo dataset qualification (hashes/rights/gold fixtures for F-12/F-14/F-5); no longer gates FL-005; owner-selected cohort and F-12 generic limitation approved; final manifest/reference qualification in progress, not passed |
| FL-003 | [Meta integration](META_INTEGRATION.md) | A: offline adapter/ledger; B: opt-in live protocol/entitlement |
| FL-004 | [Foundation](FOUNDATION.md), [shared contracts](SHARED_CONTRACTS.md) | A: locked runtimes, migrations, API/types, shell; no G1/G2 dependency |
| FL-005 | [Ingestion](INGESTION.md) | A: project upload/jobs; B: early native evidence; C: required selected scan/Word profiles; D: final IN-8 manifest qualification |
| FL-005 / FL-016 / FL-022 | [Processing flow](PROCESSING_FLOW.md) | Stage order and gates from upload to reconstruction start: document processing without a label, data exposure, AI identity merge, minimum conditions |
| FL-006 | [Trajectory/viewer](TRAJECTORY_VIEWER.md) | A: deterministic engineering; B: imported scene/selection/evidence |
| FL-007 | [Equipment](EQUIPMENT_RECONSTRUCTION.md) | A: F-14/F-5 source-dimensioned candidates plus evidence-safe F-12 generic/unlocated case; B: optional approved Blender asset |
| FL-008 | [Perforation history](PERFORATION_HISTORY.md) | A: deterministic state; B: real events/placement/inspector |
| FL-009 | [Context layers](CONTEXT_LAYERS.md) | A: seabed; B: formations; both mandatory |
| FL-010 | [Linked charts](LINKED_CHARTS.md) | A: production; B: logs; C: shared temporal overlays |
| FL-011 | [Retrieval/assistant](RETRIEVAL_ASSISTANT.md) | A/B: source retrieval/chat; D: early live chat; E: full model/domain tools; C: full live evaluation |
| FL-012 | [Demo acceptance](DEMO_ACCEPTANCE.md) | A: offline combined checks; B: real/live acceptance; C: release/recording |
| FL-013 | [Blender skill](../../.github/skills/fieldlens-blender-assets/SKILL.md) | Skill integrated; installation/assets not approved by the skill |
| FL-014 | [Architecture](../ARCHITECTURE.md), [execution plan](../../plan/architecture-fieldlens-1.md) | Confirmed workflow baseline; [first detailed packets](../../plan/feature-foundation-workspace-1.md) pending review/commit/preflight |
| FL-015 | [Project workspace](PROJECT_WORKSPACE.md) | A: project lifecycle/category/navigation contract; upload integration completes PW-3/4/6/7 through FL-005-A |
| FL-016 | [Composite-asset reconstruction](ASSET_RECONSTRUCTION.md) | A: persistent candidates/support/review/publication UI; B: independent live reconstruction gold evaluation |
| FL-017 | [Data quality](DATA_QUALITY.md) | A: source-first warning/error inspector; consumers add review/generic boundaries; real-source/combined checks complete acceptance |
| FL-018 | [Dev environment](DEV_ENVIRONMENT.md) | Single Compose project and root `.env` auto-loaded by code; no app behavior change |
| FL-019 | [Dev tooling](DEV_TOOLING.md) | `./dev` one-command stack: Postgres, migrations, API/Vite, tests, lane-aware |
| FL-020 | [Tracking](TRACKING.md) | Telegram notify, backlog ledger format, one-way Taiga sync |
| FL-021 | [UI design system](UI_DESIGN_SYSTEM.md) | Approved October 30 (light theme, Mantine, left project sidebar + Sources/Reconstruction/Explore tabs); A: shell and redesigned Projects/Sources; B: demo polish; C: source removal/replacement (TASK-039, semantics pending) |
| FL-022 | [Agentic extraction](AGENTIC_EXTRACTION.md) | Approved October 30; question-driven model-proposed candidates with read-only tools, deterministic validation and an activity log (TASK-036, TASK-038) |
| FL-024..027 | [Explore enrichment](EXPLORE_ENRICHMENT.md) | Approved November 3: formations in 3D, wellbore/field charts, fly-over/smooth camera, project assistant; [plan](../../plan/feature-explore-enrichment-1.md) |

## Project requirement -> acceptance -> verification

IDs in the first column refer to [project acceptance](../PROJECT_SPEC.md).
Test names/commands are planned until the foundation and feature owners create
them. A checkbox or mocked run cannot replace the required evidence class.

| Requirement | Feature criteria | Required verification evidence |
|---|---|---|
| AC-1: source manifest/coverage | DF-1 through DF-9, IN-8, DM-2 | Approved hashes/rights/references/history matrix and independent real fixtures |
| AC-2: fresh repeatable reconstruction | FN-2/5, IN-1/4/5, PW-3/6, RC-5/6/8, DM-1 | PostgreSQL restart/correction tests; fresh project/upload -> reconstruction review/publication -> scene |
| AC-3: real trajectories/identity | SC-2, TR-1/2/3/4/7 | Analytic fixtures plus independent source coordinates and selection |
| AC-4: equipment/history truth | EQ-1 through EQ-7, PH-1 through PH-9, DQ-5/8 | Three evidence classes, real installed assembly, labelled F-12 generic/unlocated case and exact temporal/union fixtures |
| AC-5: mandatory context | CX-1 through CX-6 | Seabed and formation source alignment, gaps/units and combined browser view |
| AC-6: both charts and history | CH-1 through CH-7, PH-8 | Source values/units, temporal overlays, stale-context interaction tests |
| AC-7: grounded Meta tools | MI-1/6, RG-1 through RG-8 | Early three-case source chat, final 32-case gold set, numeric/tool/citation checks and action acknowledgment |
| AC-8: partial/conflicting/failure states | DQ-1 through DQ-8, IN-3/4/5/6, SC-3/4, PH-5/9, EQ-4, CX-3/4, CH-4, RG-5, DM-4 | Source-linked issues, real F-14 reference/F-12 interval discrepancies, blocked outputs, interruption and stale/cancelled request fixtures |
| AC-9: measured responsiveness | TR-6, EQ-5, CX-5, CH-6, DM-3 | Combined 1080p frame timings, local read p95 during import, recorded RSS |
| AC-10: safety and zero-cost defaults | FN-3/6, IN-3, MI-2/3/4/5, RG-4/7, DM-5 | No-network default tests, scope checks, budget races and sanitized release inventory |
| AC-11: project and categorized sources | PW-1 through PW-8, SC-2/4, IN-1/7 | Two-project persistent browser flow, direct-ID/graph/retrieval isolation, category/content conflict and exact upload-boundary tests |
| AC-12: primary reconstruction agent | RC-1 through RC-10, DM-1/2 | Candidate/diff/source UI before 3D, semantic support and publication tests, independent 12-case live Meta reconstruction set |

## Acceptance rules

- Criterion IDs are stable and unique within their declared prefix.
- A feature spec's approved revision is recorded before feature implementation dispatch.
- A real-data gate is not closed by schema-valid synthetic data or public metadata.
- A qualified early subset can verify its checkpoint without full final G1;
  record its hashes/rights/profile/expected outputs and limits. It cannot verify
  uninspected files or the final three-well history. No backend-only milestone
  replaces the checkpoint's browser walkthrough.
- Live Meta and optional live catalog checks are separately authorized and billed.
- Each worker records exact tests, tested SHA, fixture/index/provider versions,
  failures and proposed release notes. Main agent alone records integrated status.
- Design changes reopen affected contracts/tests; source discoveries update the
  matching adapter spec rather than inventing canonical values.
