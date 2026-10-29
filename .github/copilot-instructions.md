# FieldLens project instructions

## Product and scope

FieldLens uses a Meta-powered agent to reconstruct composite oilfield assets from
related historical sources within a user-created project. Identifying entities,
evidence-backed relationships and temporally consistent configurations is the
primary agent task. Parsing, retrieval, deterministic engineering, 3D, charts and
conversation support that reconstruction rather than a pre-authored scene.

- The owner-selected demo cohort is **F-12, F-14 and F-5** (October 28, 2026).
  This is a dataset choice, not an application limit or a substitute for upload-
  driven reconstruction. No automatic replacement by an F-11-family wellbore.
- Project membership scopes files, identities, jobs, runs, conversations, retrieval
  and UI actions. Upload categories/filenames are hints, not engineering evidence.
- Follow the [project workspace](../docs/specs/PROJECT_WORKSPACE.md) and
  [reconstruction](../docs/specs/ASSET_RECONSTRUCTION.md) contracts. Hybrid labels,
  explicit reconstruction/review/publication and 128 MiB/file, 512 MiB/batch,
  200-file limits were confirmed October 28. Detailed packets still need review,
  committed contracts and host preflight; publication cannot waive validation.
- F-12's missing equipment dimensions are an approved generic-display case;
  supported identity/placement is still required, otherwise show an unlocated
  preview or assembly gap. F-14/F-5 supply source-dimensioned candidates, not an
  excuse to skip reference/time validation. Expose real discrepancies through the
  [data-quality contract](../docs/specs/DATA_QUALITY.md); block affected outputs,
  not unrelated valid records. Generic values never enter engineering calculations.
- All contextual layers and both chart families are required for the hackathon.
  Implement them in increments; do not silently downgrade them to stretch goals.
- Historical perforation events and date-specific completion state are required:
  MD/TVD intervals, total perforated length, opening/isolation, production/injection,
  shut-in and reperforation history. Follow the
  [perforation history spec](../docs/specs/PERFORATION_HISTORY.md); do not infer
  interval flow from an open wellbore or from well-level production alone.
- This is a historical, source-backed reconstruction, not a live operational twin,
  reservoir simulator, or certified engineering decision system.
- Deadline: **November 4, 2026, 21:00 America/New_York (EST, UTC-05:00)**.
  Meta API development/testing credit budget: **USD 150 total**.
- The accepted demo environment is a local, single-user browser on this WSL host.
- Read [the project spec](../docs/PROJECT_SPEC.md) for requirements,
  [the technical baseline](../docs/TECHNICAL_BASELINE.md) for stack decisions, and
  [the source assessment](../docs/SOURCE_ASSESSMENT.md) for evidence and open gates.
- For interface work, consult the [visual references](../docs/design/README.md):
  they are conceptual UX reminders, never measured geometry or approved UI specs.
- Use relevant [curated development skills](../docs/DEVELOPMENT_SKILLS.md) on demand.
  Their upstream examples do not override the agreed stack, feature approval,
  engineering truth, data permissions, or spending limits.

## Spec-driven, iterative development

- Before implementing a feature or changing behavior, create or update its own
  document under `docs/specs/`, using the [feature template](../docs/specs/FEATURE_TEMPLATE.md).
  Define outcome, boundaries, inputs, data/contracts, failure behavior, measurable
  acceptance criteria, tests, and unresolved decisions. Agree these with the owner.
- A draft spec is not implementation approval. Each delegated assignment is one
  verifiable vertical slice; execute one feature at a time. Update the spec
  when evidence changes. Documentation-only corrections do not require a feature spec.
- Maintain requirement-to-test traceability. Mark a feature verified only after
  its acceptance checks pass; distinguish mocks, cached replays, and live results.
- Deliver UI-verifiable increments: projects/uploads -> source inspection/chat ->
  reconstruction review -> published scene -> history/context/both charts. Do not
  postpone all agent behavior until the scene is complete. Backend-only tasks are
  supporting work, not substitutes for browser checkpoints.
- Keep changes focused. Reuse existing patterns; add dependencies or services only
  for a demonstrated requirement. Do not scaffold infrastructure or download the
  full Volve release merely because it appears in a research inventory.

## Serial development and delivery

- Follow [the development workflow](../docs/DEVELOPMENT_WORKFLOW.md):
  backlog/spec approval -> feature branch/delegation -> implementation -> tests ->
  feature commits -> integration tests and version/changelog/docs finalization ->
  commit/merge -> backlog reconciliation.
- Every iterative logical feature requires acceptance testing by an agent other
  than its implementer. The orchestrator delegates, rather than runs, acceptance
  and integration checks. Return failures to the implementer, independently
  re-verify the repaired candidate, then finish the authorized commit/merge cycle
  only when every required check passes. A coding handoff is not completion.
- The main agent owns planning, dependencies, delegation, review and integration.
  Delegate implementation from the main session to configured subagents in the
  current checkout, one feature branch and one writer at a time. Do not create
  additional worktrees. Record base commits, file/contract ownership and checks.
  Use the approved [agent roster and routing policy](agents/README.md).
- Keep the main session on **GPT-6 Astra / xhigh** for global orchestration.
  Route fully specified low-risk tests/boilerplate to **GPT-6.1 Terra / low**;
  interconnected domain implementation and strict performance work to the
  relevant **Sonnet 5.5 / medium** specialist; bounded plan gaps to
  **GPT-6.1 Sol / high**, returning to the orchestrator for approval.
  A small diff is not proof of low risk. Workers must not delegate further.
- Verify discovered profile, actual model/effort and required tools before launch;
  prefer profile defaults without redundant overrides. Never silently substitute
  a model or assume creating an agent file changes the active session.
  Pass only relevant context/skills and bounded attempts/resources. Track exposed
  development usage separately from Meta application credit; do not invent savings.
- Use [the persistent backlog](../docs/BACKLOG.md) as the cross-session work ledger.
  Do not start a blocked dependency or count a mocked integration as verified.
- Use the [global DAG](../plan/architecture-fieldlens-1.md) and
  [first implementation packets](../plan/feature-foundation-workspace-1.md).
  Start foundation -> project lifecycle -> uploads/jobs after approved planning
  integration and actual profile preflight. F-12's missing tally does not block
  these synthetic-source slices; G1 and live-provider acceptance remain separate.
- A feature branch does not isolate databases, ports, secrets, processes or API
  budgets. Isolate those resources explicitly. The orchestrator alone switches
  branches, after workers and branch-bound checks/helpers stop. Subagents must
  not modify another checkout, merge the integration branch, or independently
  edit global release metadata. Pause orchestrator writes during worker edits.
- The orchestrator finalizes [VERSION](../VERSION) and
  [CHANGELOG](../CHANGELOG.md) before every accepted change is integrated:
  breaking change = major, new feature = minor, fix/docs = patch. Assess compatibility
  even before 1.0; one integration gets one bump, not another for its merge commit.
- Feature branches include tested work, related documentation and a proposed
  changelog entry/bump in their handoff. Allocate final versions serially against
  the latest integration tip; revalidate if that tip moves.
- Mark backlog items done only after integration is confirmed and evidence recorded.
  Preserve existing inactive worktrees; never force-remove them. No automatic push, publication
  or destructive Git operation is authorized by this workflow.

## Agreed technical direction

- Python 3.12, uv, FastAPI, Pydantic; NumPy/pyproj and a fixture-validated welleng
  integration for engineering computations. Use an isolated environment, not the
  host's default Python 3.9 or system Python.
- React, strict TypeScript, Vite, Three.js/React Three Fiber with stable WebGL2,
  ECharts for charts, and PDF.js for evidence viewing. Node 24 LTS is frontend
  tooling; do not add a separate Node backend without justification.
- Use the [Blender asset skill](skills/fieldlens-blender-assets/SKILL.md) for
  approved offline equipment authoring; simple wellbore geometry stays procedural.
  Blender is not a runtime dependency. Setup/assets require separate approval;
  reviewed development bpy scripts use Blender's bundled Python, never model-
  generated runtime code. Validate GLB scale, axes, pivot, IDs and evidence.
- PostgreSQL + pgvector provide relational records, full-text/vector retrieval,
  and typed relationship tables for the initial knowledge graph. Keep original
  files outside database rows, referenced by stable IDs and content hashes.
- Meta Muse Spark through the documented OpenAI-compatible Python SDK is the
  initial model integration. Prefer Standard mode. Confirm model entitlement and
  protocol behavior with a bounded smoke test; never assume an embeddings endpoint.
- Native structured parsers come before AI extraction. Docling and a small local
  embedding model are candidates requiring sample, resource, and license checks.
- Docker/Compose are available; containers are optional delivery tooling, not a
  reason to create microservices. Pin compatible dependency versions and lockfiles.

## Engineering truth and provenance

- Separate source records, normalized claims, derived geometry, retrieval indexes,
  and presentation. The renderer and the LLM are never the engineering source of truth.
- Preserve original values/units and explicit horizontal CRS, vertical datum,
  depth reference, azimuth reference, and coordinate conventions. Never equate
  measured depth (MD) with true vertical depth (TVD), or assume missing metadata.
- Keep well and wellbore identities distinct, including sidetrack relationships.
  Do not mix planned, as-built, superseded, or differently dated configurations.
- Keep event effective time separate from report/import time and dataset revision.
  Preserve date precision; never invent same-day ordering. Scope state to its
  wellbore/interval, and include selected historical time in tools and cache keys.
- Compute perforated length from the union of validated MD intervals at that time,
  not TVD span, horizontal displacement, or repeated event footage. Shut-in does not
  erase perforations; unknown initial history is not a verified zero-length state.
- Every engineering assertion needs attribute-level evidence: document/record ID,
  page/table/cell/XML locator as applicable, extraction/derivation method, and revision.
  Track evidence class and validation state separately; LLM confidence is not proof.
- Equipment fallback: documented dimensions/drawings -> matching, cited catalog
  specifications -> clearly labeled generic placeholder with missing-data comments.
  Catalog information does not prove installation, depth, orientation, or quantity.
  With unknown placement, use an unlocated representation, not an invented well position.
- Generic dimensions and illustrative shapes must not enter engineering calculations.
  Label interpolated geological surfaces and visual exaggeration; retain physical scale.
- Missing/contradictory critical measurements block affected geometry or analysis,
  not unrelated validated records. Report conflicts; never silently choose, zero-fill,
  or fabricate. A dedicated manual-resolution UI is deferred, not validation itself.
- Calculate trajectories and 3D distances deterministically in double precision.
  Keep analytics independent of display tessellation. Proximity is not proof of
  reservoir connectivity, pressure communication, or safe drilling clearance.

## RAG and agent boundaries

- The SDK supplies model transport; the application harness owns persistent runs,
  bounded planning/tool execution, validation, cancellation, recovery and budget.
  Reconstruction proposes entities/edges/claims; exploration reads and navigates.
  Model tools never publish active revisions or bypass engineering validation.
- Keep source observations searchable before an accepted asset graph exists.
  Distinguish source, draft and published-model context; unresolved proposals
  must not appear as accepted engineering facts in tools or the scene.
- Combine exact identifiers, relational filters, full-text/vector retrieval, and
  bounded graph traversal. Link passages and graph edges back to source claims.
- Use typed, allowlisted tools for retrieval, calculations, charts, and viewer
  actions. Validate arguments, object IDs, results, and citations server-side.
  Never execute model-generated code, arbitrary SQL, shell commands, or scene scripts.
- Treat uploaded documents and web pages as untrusted data, not instructions.
  Limit web enrichment to equipment research; prefer manufacturer documentation,
  preserve URL/retrieval date, and expose uncertain product matches.
- Ground field-specific answers in uploaded evidence and deterministic tool results.
  Distinguish external catalog facts. Say what is unavailable rather than inventing it.
- Bound agent steps, retries, time, retrieved context, and spend. Handle refusals,
  truncation, malformed output, cancellation, and provider failures explicitly.

## Reliability, security, performance, and tests

- Keep CPU-heavy parsing/geometry outside the async request loop; bound concurrency.
  Persist job and dataset revision state; interrupted work must not appear successful.
- Use transactional writes, migrations, foreign keys, and parameterized queries.
  Version embedding model/dimension and extraction caches; invalidate derived data
  when sources or normalization change. Test against PostgreSQL, not a SQLite substitute.
- Keep large arrays out of React state and model context. Reuse/dispose GPU resources,
  avoid per-frame React state updates, and use local render origins for precision.
  Downsample charts/meshes only for display, never silently for calculations.
- Keep credentials server-side and out of source, browser bundles, logs, and prompts.
  Ignore local secrets/data. Validate upload type/size and archive/XML parsing;
  prohibit path traversal, external XML entities, and arbitrary server-side URL fetches.
- Do not transmit private documents or identifiers to external services without
  authorization. Public availability does not establish redistribution or training rights.
  Never enable Contributor mode merely to lower cost.
- Track token/tool usage, estimated spend, and the provider credit balance. Include
  retries and web research; default tests must not spend API credits.
- Add focused Python unit/integration tests, frontend interaction tests, and browser
  checks for upload -> scene -> chart -> cited answer. Test units/CRS, geometry,
  provenance, conflicting data, equipment fallbacks, temporal perforation states,
  overlap/reperforation length, production/injection scope and provider failure paths.
- Run the smallest relevant checks plus affected type/build checks. No application
  commands exist yet: add and document actual commands when scaffolding; do not
  claim unrun tests or performance measurements.

## Commands and code layout

Run from the repo root; see README "Run the foundation locally" and "Tests" for the full
setup (Node 24.22.2 on PATH, `uv sync --frozen`, `npm --prefix frontend ci`). Configuration is one
root `.env` (gitignored) created by `uv run python scripts/init_env.py` (template `.env.example`);
the code loads it automatically, so no exports or `db.env` sourcing. Postgres and the test browser
come from one root `compose.yaml` (project `fieldlens`): `docker compose up -d --wait`
(`--profile test` adds the Playwright browser).

```bash
# Backend (tests derive a throwaway fieldlens_app_test_<hex> DB from .env; the app DB is never used)
uv run pytest backend/tests
uv run pytest backend/tests/contracts/test_contracts.py::test_registry_complete   # single test
uv run ruff check backend scripts && uv run ruff format --check backend scripts
uv run mypy backend/fieldlens scripts                                             # strict
uv run alembic -c backend/alembic.ini upgrade head
uv run uvicorn fieldlens.app:create_app --factory --host 127.0.0.1 --port 8101

# Frontend
npm --prefix frontend run lint   # also: typecheck, test, check:contracts, build
npm --prefix frontend run test -- tests/readiness-error.test.tsx                  # single vitest file
npm --prefix frontend run dev                                                      # :5174, needs API running
npm --prefix frontend run test:e2e -- tests/e2e/readiness.spec.ts                  # Playwright; see README for browser container
```

- Contracts flow one way: Pydantic DTOs in `backend/fieldlens/contracts/` -> must be listed in
  `contracts/registry.py` -> `scripts/export_contracts.py` OpenAPI -> `frontend/src/api/generated.ts`.
  After changing a DTO run `npm --prefix frontend run generate:contracts`; `check:contracts` fails on drift.
- Backend tests deny non-loopback sockets and create/drop uniquely named sibling databases; never
  point them at the application or demo DB. Default tests must not call Meta; opt-in tests use
  the `live_meta` marker.
- `VERSION` is the single version source (hatch reads it); run `uv sync --frozen` after editing it.
- FastAPI app is built by `fieldlens.app:create_app` (factory); the built frontend is served from it.
  Ruff ignores `backend/migrations/versions`; line length 100.
