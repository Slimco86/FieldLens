# Specification: Runnable local foundation and persistent contracts

> **Spec type:** Infrastructure/migration. **Backlog:** FL-004.
> **Load-bearing frameworks:** F2, F4, F5. **Supporting:** F1, F3, F6.
> **Date:** 2026-10-27. **Decision owner:** project owner.
> **Status:** Workflow baseline confirmed; detailed packet review/commit and host activation required before execution.
> **Zero-Question Score:** 0 unowned design questions; G5 qualification is not yet run.

## How to Read This Spec

Executor: scope, contracts and commands. QA: FN criteria. Owner: outcome and
limits. Covers project AC-2/8/10 and establishes commands for later criteria.

## Notation Key

`[Validated]` means project requirement; `[Assumed: verify]` means design selection
for owner approval before handoff. H/M/L are confidence, not measurements.
All ACs score 3. Proposed paths and commands do not exist until this slice runs.

## 1. Outcome Statement

A clean checkout starts a loopback-only API/browser workspace and an isolated
PostgreSQL database with generated, versioned identity/evidence/time contracts.
Verification: FN-1 through FN-6. Outcome score 3.

## 2. Scope

### IN Scope

Python/Node manifests and locks, health/readiness endpoints, database migrations,
shared contracts, generated client, minimal accessible application shell and test
runners. Use [architecture](../ARCHITECTURE.md) and
[shared contracts](SHARED_CONTRACTS.md). `[Assumed: verify, H]`

### OUT of Scope

Real-data import (FL-005), 3D scene (FL-006), Meta calls (FL-003), account changes,
OS upgrades, hosted authentication, Blender installation and app containers.

### Scope Dependencies

Approved FL-014 design and verified FL-001 worker activation. G1 and G2 are not
prerequisites for this synthetic-contract foundation. Docker must be responsive;
do not start a paid service or silently substitute SQLite.

### Open Scope Tensions

Host Node 20 is insufficient. Install Node 24 into a user/project-managed path
only during this approved setup; no system-wide runtime replacement.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| FN-1 | Behavioral | Locked Python 3.12 and Node 24 environments install; production frontend builds; `/health` returns 200 and `/ready` reports unavailable DB as 503. | 3 | [Assumed: verify] | `test_readiness`, frontend build |
| FN-2 | Behavioral | Migrate a new PostgreSQL test database, insert/read contract fixture, downgrade to empty and upgrade again without schema drift. | 3 | [Validated] | `test_migration_roundtrip` |
| FN-3 | Negative | API/DB/dev server bind only to loopback; a disallowed Origin/Host cannot mutate data; secret config is absent from generated client and build output. | 3 | [Validated] | `test_local_boundary` |
| FN-4 | Edge case | With DB unavailable, UI displays an explicit readiness error and retry control, not an empty successful dataset. | 3 | [Validated] | `readiness-error.test.tsx` |
| FN-5 | Behavioral | SC-1 through SC-6 contracts and a keyboard-accessible empty workspace pass; generated types reproduce with no diff. | 3 | [Assumed: verify] | contract tests, `check:contracts` |
| FN-6 | Non-behavioral | Default test command blocks external network/provider calls and uses a uniquely named test database, never the demo database. | 3 | [Validated] | `test_test_isolation` |

Definition of done: all criteria plus lint/type/build checks pass on the assigned
worktree; lockfiles and actual runtime/image versions are recorded.

## 4. Context and Decisions

Executor: `fieldlens-backend`; it owns the coherent foundation including the small
shell, not parallel competing scaffolds. Complex persistence/contracts merit the
domain worker, not boilerplate routing. Orchestrator reviews UI composition.

Owned planned files: root `pyproject.toml`, `uv.lock`, `.python-version`,
`backend/fieldlens/{app.py,contracts,persistence}`, `backend/migrations`,
`frontend/package.json`, lockfile, app/API shell, `infra/compose.yaml`,
`scripts/export_contracts.py`, test configuration and this spec.
Later workers request dependency/shared-schema changes; they do not hand-edit locks.

Use PostgreSQL 17 + pgvector 0.8, Pydantic 2, SQLAlchemy 2, psycopg 3, Alembic,
FastAPI and uvicorn. Pin resolved patches and image digest after compatibility
checks. React 19.3.1, R3F 9.8.2 and Vite 8.3.5 were registry-observed on
2026-10-27; R3F declares React `>=19 <19.4`, Vite requires Node
`^20.19.0 || >=22.12.0`. That establishes candidate peer ranges, not a build result.
Resolve Three.js/Drei and remaining packages together under Node 24.

Use environment configuration with secret fields redacted. Backend owns source
and artifact storage roots; default storage is outside Git. A random local session
token plus Origin/Host allowlists protects mutation endpoints; do not create a
multi-user login system. DB readiness includes required migrations/extensions.
Static serving must not turn unknown `/api/` routes into SPA HTML responses.

Token bootstrap is `GET /api/v1/session`, with no-store JSON `{csrf_token}`.
Generate at least 32 cryptographically random bytes per API process; mutations
require `X-FieldLens-Token` and permitted Host/Origin. Reject cross-site fetch
metadata on bootstrap; permit same-origin/dev-allowlisted requests and local
CLI tests without fetch metadata. Do not enable wildcard credentialed CORS.
The client bootstraps again after restart/token rejection, but does not silently
replay a failed mutation. No token is stored in a URL, static bundle or log.

## 5. Failure Conditions

Missing Docker/Compose -> return exact setup blocker; no privileged daemon change.
Incompatible wheels/peers -> adjust patch versions within selected families and
retest; a major stack change returns to the orchestrator.
Worst misinterpretation: a health-only server is not a foundation if migrations,
strict client generation or failure UX do not work.

## 6. Ambiguity Audit

The primary package is Python; Node is frontend tooling only. Local host binding,
database choice and dependency ownership are fixed above. G5 records actual
versions before acceptance; no guessed compatibility is considered verified.

## 7. Implementation Guidance

Establish these **planned commands**, then record actual results:

```text
uv sync --frozen
uv run pytest backend/tests
uv run ruff check backend
uv run mypy backend/fieldlens
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test -- --run
npm --prefix frontend run build
npm --prefix frontend run check:contracts
```

Test configuration requires `FIELDLENS_TEST_DATABASE_URL` with a dedicated test
database; absent/unsafe URLs fail explicitly. Live Meta tests require a separate
opt-in marker and are excluded from ordinary runs.
Assignment resources and commit base are allocated by the execution plan at launch.
The [first implementation packets](../../plan/feature-foundation-workspace-1.md)
define TASK-003 steps, exact planned files, tests, ownership and stop conditions.
No feature commit/test result yet. New runtime capability proposes a minor bump;
orchestrator finalizes version and integration, not the worker.

## Open Tensions

None in the design. Missing host services block execution, not permit another DB.

## Assumption Registry

Node 24/native wheels fit the host (M; invalidate on resolver/build failure).
Compose is available after owner starts Docker (M; verify before assignment).
Single-origin local session protection is sufficient for the accepted demo (H;
reopen before exposing any service remotely).

## Adversarial Self-Critique

SQLite passing tests would hide PostgreSQL issues; inspect test connection type.
Lockfiles may be inconsistent across workers; permit one dependency owner.
A local service can still be targeted by another web origin; test mutation guards.

## Revision Triggers

Reopen if native wheels require an OS change, paired frontend versions cannot
build, or the owner requests non-local hosting.
