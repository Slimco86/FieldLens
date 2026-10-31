# FieldLens

**From historical engineering records to an explorable, evidence-backed oilfield.**

Users create a project and upload related engineering records. A Meta-powered
agent will identify composite entities, establish source-backed relationships and
dated configurations, and present a reconstructed asset model for inspection.
Deterministic services derive trajectories/equipment and align geological context;
linked 3D, production/log charts and conversation expose the same evidence.
Parsing and RAG support reconstruction, rather than a chatbot being added after
the scene is built.
Historical perforation events will support date-specific interval/state inspection,
including MD/TVD placement, perforated length, production/injection, shut-in and
reperforation history without conflating wellbore and individual interval status.

The owner-selected demonstration targets **F-12, F-14 and F-5**.
That cohort is not a product limit. The defining capability is reconstruction
from uploaded evidence, not a pre-authored 3D scene with a chatbot attached.

## Current state

The local foundation and project lifecycle are implemented: a loopback FastAPI
service, PostgreSQL migrations, typed/generated contracts and an accessible React
workspace. Create, edit, reopen and switch between persistent projects; reload
restores the selected existing project, and project switching rejects stale data.
Sources/Reconstruction/Explore explain their prerequisites without fabricated
assets. The lifecycle slice passed independent QA after its validation repair;
uploads/jobs are next. This is not yet the complete oilfield application.
The owner confirmed hybrid project uploads, explicit reconstruction review/
publication and upload limits on October 28. F-12 generic/unlocated equipment
and real discrepancies are intentional, visibly labelled demo cases.
The owner approved the first three implementation packets and then switched
development to one feature branch at a time in this checkout. The old foundation
worktree is preserved inactive; worker editing-tool exposure has varied by invocation;
see the [activation record](docs/BACKLOG.md#first-packet-execution-approval-and-activation-blocker).
Local source access is established; final pilot qualification, package compatibility
and account-specific API access remain execution gates, not implementation claims.

Deadline: **November 4, 2026, 9 PM Eastern Time**. API credit budget: **USD 150**.
The demo runs locally on the development WSL machine.
Owner-confirmed submission: **indie track**, **public repository**, and a
**three-minute recorded demo**. Containerized local execution is also acceptable.

The **0.3.3** planning package was integrated in `9d630e3`.
**0.5.0 adds the project workspace** to foundation 0.4.0; delivery evidence is in the backlog.
See [VERSION](VERSION) and [CHANGELOG](CHANGELOG.md).

## Run the foundation locally

Requirements: Python 3.12 via uv, Node **24.22.2** (pinned in
[.node-version](.node-version)), npm and responsive Docker/Compose. No OS upgrade or
global runtime replacement is required. `./dev` finds Node itself: `FIELDLENS_NODE_BIN`
(a bin directory), then `node` on `PATH` if it is exactly the pinned version, then
`.local/fieldlens/*/tools/node-v24.22.2-linux-x64/bin` in this or the main checkout.
No `PATH` export is needed. Install the frontend dependencies once with
`npm --prefix frontend ci` (or pass `--install` to `up`). Run from any directory inside the
checkout; the spec is [DEV_TOOLING](docs/specs/DEV_TOOLING.md).

```bash
./dev env-check        # verify prerequisites; changes nothing
./dev up               # postgres, migrations, frontend build if stale, API; prints URL/DB/version
./dev up --dev         # additionally Vite on http://127.0.0.1:5174/ (proxies /api to 8101)
./dev status           # what runs (key names/presence only, never secret values)
./dev logs api -f      # or `logs vite`; logs live in .local/run/ (truncated at 5 MiB)
./dev restart          # down + up
./dev down             # stops only the API/Vite it recorded; postgres keeps running
./dev down --db        # also stops the postgres service (volume kept)
./dev reset-data       # erase the configured DB (typed confirmation; refuses while the API runs)
```

`./dev` with no arguments prints the usage. A second `./dev up` changes nothing. One Compose
project (`fieldlens`) owns every local container and one untracked root `.env` holds all
local settings; `./dev up` runs `scripts/init_env.py` for you but fails with that command
if `.env` is missing. Open **http://127.0.0.1:8101/** and expect `Workspace` and
`Local services ready.`

**Linked worktrees are lanes.** In a `git worktree` the directory name becomes the lane:
database `fieldlens_<lane>` (created through the postgres container), API/Vite ports
`8101/5174` plus a per-lane offset, storage `.local/fieldlens/storage-<lane>` and state in
that worktree's `.local/run`. A derived `.env` (mode 0600) is written into the worktree from an
allowlist only (`POSTGRES_USER`/`PASSWORD`/`HOST`/`PORT`, `FIELDLENS_DB_PORT`) plus the lane's
database URL, storage, `FIELDLENS_PORT` and `FIELDLENS_ALLOWED_HOSTS`/`_ORIGINS` for the lane's
ports (the API otherwise answers 403 on offset ports); the main checkout's database, ports and
storage are never touched. Drop a finished lane with `./dev down --drop-lane` (typed
confirmation). If a lane `up` fails after creating its database, the database is kept and the
exact `down --drop-lane` command is printed. Known limitation: `frontend/vite.config.ts` hardcodes
the `/api` proxy to port 8101 (no env hook), so Vite in a lane proxies to the main API; use the
lane API port directly. `up`/`down`/`restart`/`reset-data` take an exclusive lock
(`.local/run/up.lock`); a concurrent one exits 1 with "another ./dev operation is running".

**What `./dev up` does** (the manual equivalent, useful when debugging; run from the repository
root with Node 24 first on `PATH`, for example
`export PATH="$PWD/.local/fieldlens/fl-004-a-foundation/tools/node-v24.22.2-linux-x64/bin:$PATH"`):

```bash
uv sync --frozen                       # only when uv.lock/pyproject/VERSION changed
uv run python scripts/init_env.py      # creates .env (mode 0600) or appends only missing keys
docker compose up -d --wait postgres   # PostgreSQL 17 + pgvector (container fieldlens-postgres)
uv run alembic -c backend/alembic.ini upgrade head
npm --prefix frontend run build        # only when sources/lockfile/config/VERSION changed;
                                       # ./dev builds into a temp dir and swaps it atomically
uv run uvicorn fieldlens.app:create_app --factory --host 127.0.0.1 --port 8101
```

Stopping manually: Ctrl+C for a foreground server, `docker compose stop postgres` for the
database. Never run `docker compose down -v` unless you intend to delete the database volume;
`./dev` never does.

The bootstrap generates the database password once, never overwrites or prints values,
and keeps every existing line (such as `MODEL_API_KEY`) unchanged; scripts and tests only
load `FIELDLENS_*`/`POSTGRES_*` keys, and the application settings additionally adopt
exactly `MODEL_API_KEY` as the provider secret. [.env.example](.env.example)
documents each key (role `fieldlens`, database `fieldlens_app`, port 55432, storage under
`.local/fieldlens/storage`, volume `fieldlens_pgdata`). Real environment variables
override `.env`. PostgreSQL fixes credentials when the volume is first initialized, so a
changed password needs a new volume (a deliberate, manual step). The names are new: the
earlier `fl004a`/`fl015a` containers/volumes are intentionally left untouched and unused.

Open **http://127.0.0.1:8101/**. Expect `Workspace` and `Local services ready.`
Use the project list to create two projects, edit their descriptions and reopen
them after reload or API restart. Existing foundation databases use the same
startup commands: `upgrade head` applies `0002_project_lifecycle` without
rewriting valid project rows.
`/health` reports the installed package version derived from VERSION; `/ready`
checks PostgreSQL, migration head and pgvector. After editing VERSION, run
`uv sync --frozen --reinstall-package fieldlens` to refresh installed package
metadata; a plain frozen sync can retain the cached editable package version.

For frontend development, keep the API running and run
`npm --prefix frontend run dev` in another Node 24 terminal; open
http://127.0.0.1:5174/. Stop either foreground server with Ctrl+C. Stop only the
foundation database, without deleting its volume (use `docker compose down` to also
remove the containers; never add `-v` unless you intend to delete the data):

```bash
docker compose stop postgres
```

Refresh the still-running API page to see `Local services unavailable`. Start
the DB with the `up -d --wait` command above, then activate Retry by keyboard.
Focus stays on the main region during retry and after recovery. Upload,
reconstruction and charts are subsequent packets; their prerequisites are visible
inside each project.

## Progress notifications (Telegram)

Optional; keys `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` live in the untracked `.env` (put no
comment after a secret value on the same line). Spec: [tracking](docs/specs/TRACKING.md).

```bash
uv run python scripts/notify.py --event progress --ref FL-020 "short status"   # 🔵/🟢/⚪ status
uv run python scripts/notify.py --event decision_needed --ref FL-020 "Pick A or B"  # 🔴 ACTION NEEDED
uv run python scripts/notify.py --dry-run "text"      # print only; --best-effort never fails the caller
```

### Backlog ledger and Taiga mirror

`docs/BACKLOG.md` is the source of truth (one block per feature/task). Keys `TAIGA_USERNAME`,
`TAIGA_PASSWORD`, optional `TAIGA_PROJECT_SLUG`/`TAIGA_URL`, and `TAIGA_ALLOW_PUBLIC=1` (required
while the Taiga project is public) go in `.env`.

```bash
uv run python scripts/track.py check                 # validate the ledger
uv run python scripts/track.py list --status in_progress
uv run python scripts/track.py plan                  # read-only diff against Taiga
uv run python scripts/track.py sync --apply --notify # push; second run must report writes=0
```

## Tests

`./dev test [backend|frontend|e2e|all]` runs exactly the documented gates below and exits
non-zero if any fails, with a pass/fail count (no Node `PATH` export needed). `e2e` starts only
the `browser` Compose service, runs `scripts/run_e2e.py` and removes only that container by
service name afterwards; stop a running API first (`./dev down`), the runner needs port 8101.
The test database is derived from `.env` as a unique `fieldlens_app_test_<8 hex>` sibling on
the same server (never the application database); set `FIELDLENS_TEST_DATABASE_URL` only to
override it. The manual gates, with Node 24 first on `PATH`:

```bash
uv run pytest backend/tests
uv run ruff check backend scripts
uv run ruff format --check backend scripts
uv run mypy backend/fieldlens scripts
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run check:contracts
npm --prefix frontend run build
```

Missing database configuration (run `uv run python scripts/init_env.py`), unsafe test
URLs, connection-query overrides and ambient
`PGHOSTADDR`/`PGSERVICE`/`PGSERVICEFILE` overrides fail explicitly. DB-less tests use
`Settings(_env_file=None)` and never read `.env`.
Tests create/drop uniquely named sibling databases and deny external Python
socket connections. Browser tests permit only local page requests.
No default test makes a Meta/provider call.

**Provider adapter (`backend/fieldlens/assistant/`, offline only).** The suite
`uv run pytest backend/tests/assistant -m "not live_meta"` runs the stub, recorded-replay and
payload/parse layers against fixture Responses payloads and a throwaway PostgreSQL budget
ledger; it spends nothing and the `MetaProvider` client is constructed but never called. The key
is the single variable `MODEL_API_KEY` (server environment or the root `.env`; no
`FIELDLENS_` alias; default tests force it blank and derived lane `.env` files never carry it, so
live runs use the root `.env`); without it the provider
raises `provider_unavailable` before any request. The ledger needs an owner-confirmed starting
balance and a registered pricing revision before it reserves anything; limits (4 attempts, 6 tool
calls, 90 s, 4,096 output tokens, USD 0.50 reserved, USD 150 ceiling) may only be lowered by
`FIELDLENS_PROVIDER_*`/`FIELDLENS_BUDGET_*` settings, except `FIELDLENS_PROVIDER_MAX_TOOL_CALLS`,
which is configurable (default 6, maximum 64). Live checks (`live_meta`, MI-6/TASK-005) are
excluded and need explicit owner authorization.

**Agent activity log (`backend/fieldlens/activity/`, TASK-038, AX-10 backend).** `uv run pytest
backend/tests/activity` covers the persisted work-unit log, its read API
(`GET /api/v1/projects/{id}/agent-units[/{unit_id}]`), redaction/size bounds, fenced recovery and
migration 0006 on throwaway PostgreSQL databases; offline, no provider calls. The harness writes
through `fieldlens.activity.ActivityLog`; the log is display/audit only, not an engineering source.

**Source retrieval (`backend/fieldlens/retrieval/`, TASK-011, FL-011-A).** `uv run pytest
backend/tests/retrieval` covers chunking, exact-ID/full-text/vector fusion, scope and eligibility,
degraded embedding states, index jobs and migration 0007 on throwaway PostgreSQL databases with an
offline fake embedder (no network, no provider call; `FIELDLENS_EMBEDDING_PROVIDER=none` is forced
for every default run so an installed real model is never loaded). Read API:
`GET /api/v1/projects/{id}/retrieval/search?q=...` and `.../retrieval/coverage`. The gold set is
synthetic and proves mechanics only. Meta has no embeddings endpoint, so the real embedder is the
pinned local `BAAI/bge-small-en-v1.5` (int8 ONNX, FastEmbed, CPU). Its one-off, hash-pinned download
is an explicit setup step, never part of tests or the app: `uv run python
scripts/fetch_embedding_model.py` (to `.local/fieldlens/models`, gitignored). Without the model the
service reports `degraded` (exact + full text) rather than hybrid. Opt-in checks (excluded by
default): `uv run pytest backend/tests/retrieval/test_local_embedder.py -m local_embedder -s`
(real model latency/RSS/similarity) and, with `FIELDLENS_LOCAL_DATA_ROOT` set, `uv run pytest
backend/tests/retrieval/test_local_data_retrieval.py -m local_data -s` (real-subset chunking and
exact-ID lookup, first-search latency, worst real-tokenizer wordpiece count).
New dependency note: FastEmbed 0.9.1 (Apache-2.0) brings py-rust-stemmers 0.1.8, which has no
license metadata field but ships a `LICENSE` file in the wheel (MIT, Copyright 2024 qdrant; verified
in the installed package, not assumed). A vector-only hit is `strong` only above an uncalibrated floor (0.68) and a margin over the candidate median; otherwise the result is `weak_evidence` (see the spec status note). Numeric tables (production/trajectory series) are excluded
from embedding by policy and stay exact/full-text searchable; coverage states it.

Opt-in local-data check (skipped when unset; read-only, nothing is copied into the repo):

```bash
FIELDLENS_LOCAL_DATA_ROOT=/mnt/c/Users/<you>/Downloads/Hackathon_Data \
  uv run pytest backend/tests/test_local_data_profiles.py -m local_data -s
```

It runs every native profile on the approved Volve subset and prints the per-wellbore
coverage matrix (trajectory stations / production days / perforation intervals with
unsupported depths / drilling-assembly and casing-point records for F-12, F-14, F-5). It also
runs the report builder on every real file. Completion strings, packers and tubing are not
extracted (deferred completion PDFs) and are reported as a gap per wellbore.

### Playwright on this Ubuntu 20.04 / Docker Desktop host

Playwright 1.64.1 no longer installs its Chromium build on Ubuntu 20.04.
Use the matching, digest-pinned Noble **test-only browser**; the application and
Node 24 runner still execute on WSL. This also works without Docker host networking:

```bash
docker compose --profile test up -d --wait    # adds only the browser to the running postgres
npm --prefix frontend run test:e2e -- tests/e2e/readiness.spec.ts
docker compose --profile test down            # stops/removes both containers; the volume stays
```

The runner takes the endpoint (`ws://127.0.0.1:9323/`) and network setting (`<loopback>`)
from `.env` (`FIELDLENS_PW_CONNECT_WS_ENDPOINT`, `FIELDLENS_PW_EXPOSE_NETWORK`) and
passes them to Playwright as `PW_TEST_CONNECT_*`; no exports are needed. To keep the
database running, stop only the browser with `docker compose stop browser`.

Port 9323 is published only on host loopback. The container listens on its private
interface; the Playwright tunnel exposes only the runner's loopback destinations.
It runs as `pwuser`, with a 1 GiB memory cap and read-only frontend dependencies,
without application secrets, source documents or privileged capabilities.
The image occupies approximately 2.52 GB on disk and remains cached after cleanup.

Stop any manual API on 8101 before E2E. The runner refuses an occupied port,
creates/migrates its own unique DB, serves the built UI, then stops its own API
and drops that DB even on test failure. One browser worker runs three scenarios:
live ready; intercepted network failure/loading and keyboard recovery; **real test
database removal, repeated 503 and recovery after recreation**. No test-only API
route is added to the product.

Project lifecycle specs (`project-lifecycle`, `project-navigation`) run against that
same real API/PostgreSQL. A test requests a **true API process restart** with
`run_e2e.py --api-restart`: a file handshake in the runner's private control directory
(`FIELDLENS_E2E_CONTROL_DIR`), not an application endpoint. The runner stops and
restarts its own uvicorn against the same database, so the session token is regenerated.
Run everything with `npm --prefix frontend run test:e2e`, or one file as shown above.
`FIELDLENS_STORAGE_ROOT` (from `.env`) relocates the runner's `e2e` scratch directory.
Native-browser hosts may omit the container and delete the two `FIELDLENS_PW_*` keys
from `.env` after installing the matching browser (the runner then sets no `PW_TEST_*`).

Verified versions and requirement-to-test evidence are recorded in
[FOUNDATION](docs/specs/FOUNDATION.md). Generated client changes must come from
`npm --prefix frontend run generate:contracts`; `check:contracts` never rewrites it.

## Development documents

- [Copilot instructions](.github/copilot-instructions.md): always-on project rules.
- [Project specification](docs/PROJECT_SPEC.md): required outcomes, exclusions,
  acceptance criteria, and explicitly owned open questions.
- [Application architecture](docs/ARCHITECTURE.md): module/process boundaries,
  selected stack, data flow, engineering authority, UI and resource budgets.
- [Feature specs and traceability](docs/specs/README.md): complete feature
  breakdown and project requirement-to-test mapping.
- [Shared contracts](docs/specs/SHARED_CONTRACTS.md): identity, evidence,
  revision/time, API, errors, caches and validated actions.
- [Project workspace](docs/specs/PROJECT_WORKSPACE.md): source categories,
  incremental uploads, isolation and source/model revision boundaries.
- [Composite reconstruction](docs/specs/ASSET_RECONSTRUCTION.md): primary agent
  workflow, evidence-linked entities/relationships, review and live evaluation.
- [Data quality](docs/specs/DATA_QUALITY.md): evidence-linked warnings/errors,
  generic limitations and affected-output blocking without hiding valid records.
- [Implementation sequence](plan/architecture-fieldlens-1.md): 32 explicit tasks,
  dependency DAG, serial feature ownership and deadline checkpoints.
- [First implementation packets](plan/feature-foundation-workspace-1.md):
  foundation -> project lifecycle -> uploads/jobs, with planned files, tests,
  isolated resources, handoffs and stop conditions.
- [Technical baseline](docs/TECHNICAL_BASELINE.md): agreed stack, rationale,
  engineering conventions, and observed local tooling.
- [Source assessment](docs/SOURCE_ASSESSMENT.md): conversation analysis,
  verified claims, data candidates, and feasibility gates.
- [Volve data discovery](docs/VOLVE_DATA_DISCOVERY.md): selected F-12/F-14/F-5
  cohort, exact candidate-file list, official access steps, rights and known gaps.
- [Data-feasibility spec](docs/specs/DATA_FEASIBILITY.md): draft bounded sample
  audit; metadata discovery is not engineering-data verification.
- [Equipment-data feasibility](docs/EQUIPMENT_DATA_FEASIBILITY.md): actual
  dimensioned XML probes, additional source assessment, and the remaining
  installed-completion go/no-go gate.
- [Feature specification template](docs/specs/FEATURE_TEMPLATE.md): use before
  each implementation increment.
- [Visual reference gallery](docs/design/README.md): the conversation wireframe
  and original FieldLens UX reference sheets, with provenance and design lessons.
- [Curated development skills](docs/DEVELOPMENT_SKILLS.md): selected local skills
  for frontend, 3D assets, geospatial validation, ingestion and equipment research.
- [Blender equipment skill](.github/skills/fieldlens-blender-assets/SKILL.md):
  offline modeling, reviewed bpy scripts and validated GLB export; installation
  and actual assets are deferred, and simple tubes remain procedural in Three.js.
- [Perforation history spec](docs/specs/PERFORATION_HISTORY.md): draft event/state,
  depth, perforated-length and temporal acceptance contracts.
- [Development workflow](docs/DEVELOPMENT_WORKFLOW.md): one checkout and feature at a time,
  ownership, testing, integration and version/changelog policy.
- [Development agents](.github/agents/README.md): ten specialists, the main
  orchestrator, model/effort routing and activation instructions.
- [Agent configuration spec](docs/specs/DEVELOPMENT_AGENTS.md): approved scope,
  acceptance and static versus runtime verification.
- [Backlog](docs/BACKLOG.md): persistent feature IDs, prerequisites and delivery state.

## Delivery workflow

The main agent plans and orchestrates; implementation subagents launch from that
session and work sequentially in the current checkout, one feature branch and
one writer at a time, on approved dependency-ready specs. No new worktrees.
Only the orchestrator switches branches after workers/checks/helpers stop.
Each integration requires
tests, related documentation, and an assessed major/minor/patch update before merge.
After integration, the orchestrator reconciles the backlog. Select
**fieldlens-orchestrator** in the Copilot harness after refreshing agent discovery;
verify **GPT-6 Astra / xhigh** in the host. Workers use Terra low, Sonnet medium
or Sol high according to the task. Repository profiles do not switch an existing
chat or switch branches; verify the chosen worker/model/tools before execution.

**Next step:** implement project lifecycle after confirming worker tool access
and the next allocation. Deliver
browser-visible projects/uploads, source inspection
and early chat, reconstruction review, and finally the linked scene/history/context/
charts. Each real-data increment needs its qualified subset; full demo acceptance
still requires the final manifest and live evaluations.
The owner supplied the local data, including inspected F-14/F-5 dimensions.
F-12's missing tally does not block synthetic project/upload work; generic values
never become engineering measurements. Remaining extraction/profile and
reference/history qualification is recorded, not solved by planning.
Both chart families and all contextual layers
remain mandatory. No dataset ingestion or paid infrastructure is included in this foundation.
