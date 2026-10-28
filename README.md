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

The first foundation is implemented: a loopback FastAPI service, PostgreSQL
migrations, typed/generated contracts and an accessible React readiness shell.
QA's contract, focus, isolation, version and browser-tooling findings have been
repaired and directly retested. Independent re-verification/integration is still
pending; this is not a released or complete oilfield application.
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
**0.4.0 is the foundation release candidate**, not yet merged into `master`.
See [VERSION](VERSION) and [CHANGELOG](CHANGELOG.md).

## Run the foundation locally

Requirements: Python 3.12 via uv, Node **24.22.2** (pinned in
[.node-version](.node-version)), npm, and responsive Docker/Compose.
No OS upgrade or global runtime replacement is required. Use your existing
Node version manager. On the development WSL host, the already-installed runtime
can be selected with:

```bash
export PATH="$PWD/.local/fieldlens/fl-004-a-foundation/tools/node-v24.22.2-linux-x64/bin:$PATH"
uv sync --frozen
npm --prefix frontend ci
```

Run all following commands from the repository root. For a fresh checkout only,
create the local credential file once (never regenerate it for an existing DB volume):

```bash
umask 077
mkdir -p .local/fieldlens/fl-004-a-foundation
if [ ! -e .local/fieldlens/fl-004-a-foundation/db.env ]; then
  FIELDLENS_DB_PASSWORD="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  printf 'FIELDLENS_DB_PASSWORD=%s\n' "$FIELDLENS_DB_PASSWORD" > .local/fieldlens/fl-004-a-foundation/db.env
fi
set -a
. .local/fieldlens/fl-004-a-foundation/db.env
set +a
export FIELDLENS_DATABASE_URL="postgresql+psycopg://fieldlens_fl004a:${FIELDLENS_DB_PASSWORD}@127.0.0.1:55432/fieldlens_fl004a_w1"
export FIELDLENS_STORAGE_ROOT="$PWD/.local/fieldlens/fl-004-a-foundation/storage"

docker compose --env-file .local/fieldlens/fl-004-a-foundation/db.env -f infra/compose.yaml up -d --wait
uv run alembic -c backend/alembic.ini upgrade head
npm --prefix frontend run build
uv run uvicorn fieldlens.app:create_app --factory --host 127.0.0.1 --port 8101
```

Open **http://127.0.0.1:8101/**. Expect `Workspace` and `Local services ready.`
`/health` reports the installed package version derived from VERSION; `/ready`
checks PostgreSQL, migration head and pgvector. After editing VERSION, run
`uv sync --frozen` to refresh installed package metadata.

For frontend development, keep the API running and run
`npm --prefix frontend run dev` in another Node 24 terminal; open
http://127.0.0.1:5174/. Stop either foreground server with Ctrl+C. Stop only the
foundation database, without deleting its volume:

```bash
docker compose --env-file .local/fieldlens/fl-004-a-foundation/db.env -f infra/compose.yaml stop postgres
```

Refresh the still-running API page to see `Local services unavailable`. Start
the DB with the `up -d --wait` command above, then activate Retry by keyboard.
Focus stays on the main region during retry and after recovery. Project creation,
upload, reconstruction and charts are subsequent packets, not missing controls
in this foundation's scope.

## Tests

Load the credential file and select Node 24 as above. Never use the application
database or a demo database for tests:

```bash
export FIELDLENS_TEST_DATABASE_URL="postgresql+psycopg://fieldlens_fl004a:${FIELDLENS_DB_PASSWORD}@127.0.0.1:55432/fieldlens_fl004a_w1_test_$(uv run python -c 'import secrets; print(secrets.token_hex(4))')"
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

Missing/unsafe test URLs, connection-query overrides and ambient
`PGHOSTADDR`/`PGSERVICE`/`PGSERVICEFILE` overrides fail explicitly.
Tests create/drop uniquely named sibling databases and deny external Python
socket connections. Browser tests permit only local page requests.
No default test makes a Meta/provider call.

### Playwright on this Ubuntu 20.04 / Docker Desktop host

Playwright 1.64.1 no longer installs its Chromium build on Ubuntu 20.04.
Use the matching, digest-pinned Noble **test-only browser**; the application and
Node 24 runner still execute on WSL. This also works without Docker host networking:

```bash
docker compose -f infra/compose.browser.yaml up -d --wait
export PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:9323/
export PW_TEST_CONNECT_EXPOSE_NETWORK='<loopback>'
npm --prefix frontend run test:e2e -- tests/e2e/readiness.spec.ts
docker compose -f infra/compose.browser.yaml down
```

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
route is added to the product. Native-browser hosts may omit the container and
the two `PW_TEST_*` variables after installing the matching browser.

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

**Next step:** close the foundation acceptance/integration gate on
`feature/fl-004-a-foundation-serial`, then implement project lifecycle. Deliver
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
