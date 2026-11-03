# Execution plan: Explore enrichment (formations, charts, camera, assistant)

Planned 2026-11-03 18:30 EST by the orchestrator. Spec: [EXPLORE_ENRICHMENT](../docs/specs/EXPLORE_ENRICHMENT.md)
(approved 2026-11-03 18:47 EST with decisions D1-D7: no assistant spend cap, horizons skipped, priorities production charts > assistant/avatar > smooth camera > basic formations). Base: `master` @ `0462ad0` (0.52.1),
Alembic head `0019`. Deadline: Nov 4 2026 21:00 EST (about 26 h). This plan allocates work; it starts nothing.

## 1. Findings that shape the plan

- Formation picks are already parsed (`formation_pick` records, `profiles/dat_tables.py`) but nothing reads them: no API,
  no scene layer. Volve horizon XYZ grids (Hugin top/base, seabed) are in the candidate list but have no profile.
- Production and LAS series are stored and served (`/series`, `/series/{id}/window`, min/max downsampling); **ECharts is not
  in `frontend/package.json`** and there is no chart UI. Perforation history has an engine but no API.
- Pressure-test/lab-test/DDR events have no parser (only daily average downhole pressure/temperature in production).
- Camera: one 0.75 s lerp in `Viewer3D.tsx`/`FieldViewer3D.tsx` (`frame.go`/`flyTo`); no fly-over.
- Assistant: harness (WorkUnit, BudgetLedger, provider/fake) exists; **no chat route, tools, tables or UI**; Explore has an empty
  `dock` region ready to host it; retrieval search/coverage routes exist; source links open PDFs (TASK-088).
- Ledger lag: TASK-010/012/013/015-019/031 are still `proposed` although their code exists or is superseded by TASK-078..093.
  Reconcile after the owner approves (not edited here).
- Session note: this orchestration session reports Claude Sonnet 5.5, not the registry's GPT-6 Astra/xhigh. No substitution is
  assumed; confirm host profile/model/effort for each worker before launch (TASK-001 preflight rule).

## 2. Waves and dependency order

```
wave 0 (<=1.5 h, parallel)   TASK-094 contracts+deps freeze    TASK-095 scene seams
                                   |                                |
wave 1 (parallel lanes)   B 097 formation API ----> C 098 formation layers (3D)      [needs 095, 094]
                          A 096 camera transitions + fly-over                          [needs 095]
                          D1 100 chart API ---------> D2 102 charts UI                 [needs 094, 095]
                          E1 103 chat backend ------> E2 104 chat UI + avatar          [needs 094, 095]
                          stretch: 099 horizon import, 101 events/lab spike
wave 2 (serial)          105 integration: chat tools for formations/charts, link wiring, Explore layout
                         106 independent QA per feature + combined browser acceptance; repair loop
release                  serial version/changelog per merge; Nov 4 17:00 freeze
```

Frontends start against fixtures and the frozen `generated.ts`; they do not wait for their backend lane. Merge order (each
rebases on the new tip and re-runs checks): 094, 095, 097, 096, 100, 098, 102, 103, 104, 105.

## 3. Wave 0 — freeze shared surfaces (orchestrator-serialized files)

| Task | Owner profile | Worktree / branch | Delivers |
|---|---|---|---|
| TASK-094 | fieldlens-backend | `task-094-contracts` / `feature/task-094-contracts` | DTO-only contracts `context_layers.py`, `charts.py`, `chat.py` (AppLink, AnswerBlock, ChartSpec, FormationLayerSet, WellboreChartSet, FieldChartSet) + `registry.py` + `generate:contracts`; echarts added to `frontend/package.json`/lockfile; no behavior |
| TASK-095 | fieldlens-3d-motion | `task-095-scene-seams` / `feature/task-095-scene-seams` | `layers` slot in `Viewer3D`/`FieldViewer3D` (children mounted inside the Canvas, receive frame/exaggeration/cutaway), `ExploreCommands` bus (`focusWellbore/Element/Formation`, `openSource`, `openChart`), `flyOver/stopFlyOver` command stubs, Explore layout regions (Stage 3D/Charts/Split, dock) with empty slots |

After merge, lanes may not edit the registry, `generated.ts`, `package.json`/lockfile or the Alembic head; they request a
contract amendment from the orchestrator (serial). Pre-assigned migrations: `0020` chat (E1), `0021` horizon surfaces
(TASK-099), `0022` reserved for an events profile if TASK-101 finds data.

## 4. Lanes (one writer per worktree under `/home/slimco/code/FieldLens-worktrees/<lane>`, own `./dev` lane)

| Lane / task | Profile | Branch | Owned files (exclusive) | Depends on | Spec IDs |
|---|---|---|---|---|---|
| A / 096 camera | fieldlens-3d-motion | `feature/task-096-camera` | `scene/cameraRig.ts`, `cameraPath.ts`, `flyOverPlan.ts`, `FlyOverControls.tsx`, camera sections of `Viewer3D.tsx`/`FieldViewer3D.tsx`, tests | 095 | CM-1..6 |
| B / 097 formation API | fieldlens-geospatial | `feature/task-097-formation-api` | `backend/fieldlens/context/{formations.py,routes.py}`, `backend/tests/context/` | 094 | FO-1,2,3,5,6 (backend) |
| C / 098 formation layers | fieldlens-3d-motion | `feature/task-098-formation-layers` | `frontend/src/features/context/formations/**`, tests | 094, 095 (fixtures until 097 merges) | FO-3..6 |
| D1 / 100 chart API | fieldlens-backend | `feature/task-100-chart-api` | `backend/fieldlens/charts/**`, perforation-history read route, `backend/tests/charts/` | 094 | XC-1..4 (backend) |
| D2 / 102 charts UI | fieldlens-frontend | `feature/task-102-charts-ui` | `frontend/src/features/charts/**` (exports `ChartBlock`), tests | 094, 095 | XC-1..7 |
| E1 / 103 chat backend | fieldlens-rag | `feature/task-103-chat-backend` | `backend/fieldlens/chat/**`, migration `0020`, `backend/tests/chat/` | 094 | AV-1,2,3,6,8 |
| E2 / 104 chat UI | fieldlens-frontend | `feature/task-104-chat-ui` | `frontend/src/features/assistant/**` (panel, avatar, block renderers), tests | 094, 095 (`ChartBlock` from 102 in wave 2) | AV-4,5,7 |
| stretch 099 | fieldlens-geospatial | `feature/task-099-horizons` | `profiles/horizon_xyz.py`, migration `0021`, `context/horizons.py` | 097 merged | FO-7 |
| stretch 101 | fieldlens-ingestion | `feature/task-101-events-spike` | spike note + optional profile | none | D2 |

`scene/` shared files not owned by A are read-only for the others; scene registration of the formation layer and the
dock/stage wiring are applied by the integration task (105), as CONTEXT_LAYERS requires. The charts lane's perforation
endpoint reuses `engineering/perforation`; it does not edit it.

## 5. Lane packet (given to every implementer)

Scope and spec IDs above; the frozen contracts; owned paths; checks to run
(`uv run ruff check && ruff format --check && mypy` plus lane pytest dir; `npm --prefix frontend run lint|typecheck|test|check:contracts|build`);
forbidden: editing outside owned paths, global release metadata, other worktrees, live Meta calls, delegating. First step:
verify the dev project data the lane depends on (picks, production workbook, trajectories for F-12/F-14/F-5) and report absence
as an empty-state requirement rather than synthesizing data. Handoff: commits on branch, doc updates, proposed
changelog line/minor bump, evidence split into mock/replay/real.

## 6. Verification and integration

- Independent `fieldlens-qa` per feature (never the implementer): FO (with B+C merged), XC (D1+D2), CM (A), AV (E1+E2 + 105 tools);
  then one combined browser flow: project -> wellbore -> formations visible with source link -> Fly over -> charts (wellbore and
  field) -> assistant question returns cited chart + link that flies the camera/open the PDF. Failures return to the implementer.
- `fieldlens-task` (low-risk): fixtures, Playwright command wiring, changelog/doc mechanical edits.
- Resources: one `./dev` lane each (DB, storage, ports); at most 6 simultaneous writers on this WSL host to keep
  Postgres/Vite load acceptable; QA and Playwright run after writers stop. No live Meta except AV-9 (<=USD 1, owner approval).
- Versions: serial minors from 0.53.0, one bump per integration; Telegram notice per transition via `scripts/notify.py`.

## 7. Timeline (EST) and cut line

| Window | Work |
|---|---|
| Nov 3 evening | Owner approval of spec/defaults; create worktrees; wave 0 (094, 095) merged |
| Nov 3 night - Nov 4 06:00 | Wave 1 lanes A, B, C, D1, D2, E1 (+E2); merge as each passes lane checks |
| Nov 4 06:00-11:00 | Independent QA per feature; repairs; 105 integration |
| Nov 4 11:00-16:00 | Combined browser acceptance, repair loop, stretch items only if P0 is green |
| Nov 4 17:00 | Feature freeze; release version/changelog/backlog reconciliation |
| Nov 4 17:00-20:00 | Existing demo acceptance/recording tasks on the integrated build; 1 h buffer before 21:00 |

If a lane slips, cut in this order: avatar polish, AV-9, FO-7, events profile, field correlation chart, T3 interpolation
(keep T1+T2), chart-to-scene hover linking. Never cut: labels of illustrative/unreconciled data, evidence links, empty states.

## 8. Risks

Viewer file contention (A vs C) -> seams in 095 and single integration point in 105. Picks may lack datum or use sidetrack
names that do not resolve (FO-1 conflicts) -> shown, not hidden. Pressure/lab events may not exist in sources -> truthful empty
state. Chat cost and truncation on real Meta unmeasured -> fake provider default, per-turn caps. Seven parallel lanes on one
host -> concurrency cap and staggered QA. Spec approval is the only gate before wave 0.
