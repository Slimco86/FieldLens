# Feature specifications and requirement traceability

Updated 2026-10-27. The architecture/specification package is complete for owner
review. **No new application feature is approved, implemented or verified merely
by appearing here.** Existing preparation approvals retain their recorded status.
See [architecture](../ARCHITECTURE.md), [backlog](../BACKLOG.md) and the
[implementation sequence](../../plan/architecture-fieldlens-1.md).

## Feature index

| Backlog | Specification | Bounded increments / current execution gate |
|---|---|---|
| FL-001 | [Development agents](DEVELOPMENT_AGENTS.md) | Configuration integrated; actual host activation still unverified |
| FL-002 | [Data feasibility](DATA_FEASIBILITY.md) | Access, source/rights/coverage and independent real fixtures; blocked on pilot access/approval |
| FL-003 | [Meta integration](META_INTEGRATION.md) | A: offline adapter/ledger; B: opt-in live protocol/entitlement |
| FL-004 | [Foundation](FOUNDATION.md), [shared contracts](SHARED_CONTRACTS.md) | A: locked runtimes, migrations, API/types, shell; no G1/G2 dependency |
| FL-005 | [Ingestion](INGESTION.md) | A: upload/jobs/evidence; B: approved native profiles and pilot normalization |
| FL-006 | [Trajectory/viewer](TRAJECTORY_VIEWER.md) | A: deterministic engineering; B: imported scene/selection/evidence |
| FL-007 | [Equipment](EQUIPMENT_RECONSTRUCTION.md) | A: source-aware procedural equipment; B: optional source-approved Blender asset |
| FL-008 | [Perforation history](PERFORATION_HISTORY.md) | A: deterministic state; B: real events/placement/inspector |
| FL-009 | [Context layers](CONTEXT_LAYERS.md) | A: seabed; B: formations; both mandatory |
| FL-010 | [Linked charts](LINKED_CHARTS.md) | A: production; B: logs; C: shared temporal overlays |
| FL-011 | [Retrieval/assistant](RETRIEVAL_ASSISTANT.md) | A: hybrid/graph retrieval; B: offline bounded agent/UI; C: live evaluation |
| FL-012 | [Demo acceptance](DEMO_ACCEPTANCE.md) | A: offline combined checks; B: real/live acceptance; C: release/recording |
| FL-013 | [Blender skill](../../.github/skills/fieldlens-blender-assets/SKILL.md) | Skill integrated; installation/assets not approved by the skill |
| FL-014 | [Architecture](../ARCHITECTURE.md), [execution plan](../../plan/architecture-fieldlens-1.md) | Documentation complete; integration and feature approval remain separate |

## Project requirement -> acceptance -> verification

IDs in the first column refer to [project acceptance](../PROJECT_SPEC.md).
Test names/commands are planned until the foundation and feature owners create
them. A checkbox or mocked run cannot replace the required evidence class.

| Requirement | Feature criteria | Required verification evidence |
|---|---|---|
| AC-1: source manifest/coverage | DF-1 through DF-9, IN-8, DM-2 | Approved hashes/rights/references/history matrix and independent real fixtures |
| AC-2: fresh repeatable reconstruction | FN-2/5, IN-1/4/5, DM-1 | PostgreSQL idempotency/restart/correction tests and fresh browser upload |
| AC-3: real trajectories/identity | SC-2, TR-1/2/3/4/7 | Analytic fixtures plus independent source coordinates and selection |
| AC-4: equipment/history truth | EQ-1 through EQ-6, PH-1 through PH-9 | Three evidence classes, real installed assembly, exact temporal/union fixtures |
| AC-5: mandatory context | CX-1 through CX-6 | Seabed and formation source alignment, gaps/units and combined browser view |
| AC-6: both charts and history | CH-1 through CH-7, PH-8 | Source values/units, temporal overlays, stale-context interaction tests |
| AC-7: grounded Meta tools | MI-1/6, RG-1 through RG-7 | 32-case gold set, numeric/tool/citation checks, action acknowledgment and live run |
| AC-8: partial/conflicting/failure states | IN-3/4/5/6, SC-3/4, PH-5/9, EQ-4, CX-3/4, CH-4, RG-5, DM-4 | Hostile/partial source, interruption and stale/cancelled request fixtures |
| AC-9: measured responsiveness | TR-6, EQ-5, CX-5, CH-6, DM-3 | Combined 1080p frame timings, local read p95 during import, recorded RSS |
| AC-10: safety and zero-cost defaults | FN-3/6, IN-3, MI-2/3/4/5, RG-4/7, DM-5 | No-network default tests, scope checks, budget races and sanitized release inventory |

## Acceptance rules

- Criterion IDs are stable and unique within their declared prefix.
- A feature spec's approved revision is recorded before worktree creation.
- A real-data gate is not closed by schema-valid synthetic data or public metadata.
- Live Meta and optional live catalog checks are separately authorized and billed.
- Each worker records exact tests, tested SHA, fixture/index/provider versions,
  failures and proposed release notes. Main agent alone records integrated status.
- Design changes reopen affected contracts/tests; source discoveries update the
  matching adapter spec rather than inventing canonical values.
