# Specification: Runnable local foundation and persistent contracts

> **Spec type:** Infrastructure/migration. **Backlog:** FL-004.
> **Load-bearing frameworks:** F2, F4, F5. **Supporting:** F1, F3, F6.
> **Date:** 2026-10-27. **Decision owner:** project owner.
> **Status:** Original candidate `3c1d2b2` failed independent QA. Owner requested direct repairs without further subagents; repaired candidate passes direct checks, pending acceptance/integration.
> **Zero-Question Score:** 0 unowned design questions; G5 runtime compatibility verified for the foundation.

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
feature branch in the shared checkout; lockfiles and actual runtime/image versions are recorded.
An agent other than the implementer verifies the full acceptance matrix and any
repairs. Failed or unrun required gates prohibit merge, regardless of a working
preview or passing subset.

### Independent QA and bounded repair allocation

QA reviewed frozen candidate `3c1d2b285fc8588d32407977d4f27bf921f0d51f` using
`fieldlens-qa` on host-confirmed Sonnet 5.5/medium. Its overall verdict is **FAIL**:
84 backend and 3 frontend tests, type/lint/build/contracts, migration roundtrip,
real database-unavailable UI and Retry recovery passed, but those checks did not
cover the defects below. This is not feature acceptance or checkpoint A.

- D1: missing usable start/stop/migrate/test documentation and verification record.
- D2: keyboard focus lost when Retry unmounts.
- D3/D4: nested evidence-revision scope bypass and namespace-dependent authority
  checks; preserve the shared-contract invariants, not just existing happy paths.
- D5/D6/D7: nonfinite arbitrary metadata, invalid image regions, blank quantity
  units/reasons and coercible boolean read limits.
- D8: test database query options can override loopback connection destinations.
- D9/D10: runtime version differs from VERSION; Node 24 is not pinned/enforced.
- D11: exception response request-ID/status/header consistency needs correction.
- B1: Playwright 1.64.1 browser installation genuinely rejects Ubuntu 20.04.
  Integrated-browser verification works, but does not waive the CLI test gate.

The repair is still TASK-003, not a new feature. Add regression tests and preserve
the agreed Python/Node/application stack. For B1, the orchestrator authorizes a
bounded, test-only official Playwright 1.64.1 Noble browser container with a
loopback-only connection from the host runner, following the
[documented unsupported-Linux workflow](https://playwright.dev/docs/docker#remote-connection).
Pin the image digest, match runner/browser versions, use the existing Node 24
runner and stop the helper after tests. No host OS upgrade, privileged container,
application containerization or remote public listener is authorized. Report
resource/download failure rather than silently downgrading dependencies or
marking an unrun gate passed.

The repair preflight at base `923b1bf` reported no `apply_patch`, `create` or
`edit`; a focused discovery attempt confirmed no local editor was available.
Host metadata still selected backend Sonnet 5.5/medium. No repair files were
written and no browser image was pulled. The earlier successful profile
recreation was not a durable fix. Do not use shell-writing or patch-return
workarounds; resolve capability or obtain an explicit temporary routing exception.

### Direct repair verification, October 28

After the repeated editor preflight failed, the owner switched the main model
and explicitly requested direct repairs without more subagents. No further
subagent was used. These are **direct implementation checks**, not an independent
QA PASS or a claim that the prior failed verdict was automatically superseded.

| Criteria / finding | Actual evidence |
|---|---|
| FN-1 / D9/D10 | Python 3.12.13, uv 0.11.20, Node 24.22.2; Node 24 enforced by npm engines/engine-strict, patch pinned in `.node-version`. Hatch package metadata reads root VERSION (0.4.0 candidate); `/health` consistency test passes. |
| FN-2 | Real PostgreSQL migration/fixture/constraint/downgrade/upgrade tests pass; migration is unchanged from independent QA's drift-checked baseline. PostgreSQL 17.8, pgvector 0.8.1, pinned image. |
| FN-3 / D11 | Local-boundary regression tests pass; 500 response headers match envelope request ID, logging excludes exception-message secrets, generic 403 is `FORBIDDEN`, health is no-store. |
| FN-4/FN-5 / D2 | Four UI interaction tests pass, including focus during pending Retry, repeated failure and success. Three real CLI browser tests pass through the supported browser container. |
| SC-1/SC-2 / D3 | Typed roundtrips and project-qualified DB constraints pass. Source evidence links require matching nested document/revision IDs; missing outer IDs cannot bypass source-issue scope. |
| SC-3 / D5/D6/D7 | Recursive JSON rejects nonfinite numbers without converting to null; image regions are normalized and ordered; blank units/reasons fail. New counterexample regressions pass. |
| SC-4 | Context/time/cache identity and allowed-context tests pass. Downstream project-scoped endpoints and stale scene responses remain their owning packets, not new foundation business routes. |
| SC-5 / D4 | Reserved generic/catalog namespaces require matching provenance and reject arbitrary-key bypasses; evidence class remains independent of validation state. |
| SC-6 / D7 | Booleans/floats/decimal-looking strings cannot masquerade as integer limits; ordinary decimal HTTP query limits still work and respect 200/5,000 caps. |
| FN-6 / D8 | Unsafe test URLs and all connection query overrides are rejected, as are ambient libpq host-address/service overrides. Unique DB and Python external-network guard tests pass. |
| D1 / TASK-FN-08 | README documents dependency selection, secret setup, start/stop, migration, build, isolated tests, browser helper and limits. |
| B1 | Playwright 1.64.1 CLI runs on Node 24 against the matching digest-pinned Noble browser image. Docker Desktop requires host-loopback port publishing plus `PW_TEST_CONNECT_EXPOSE_NETWORK='<loopback>'`, not host networking. |

Result: **124 backend tests, 4 UI tests, 3 CLI E2E tests pass**; ruff and mypy pass,
frontend lint/typecheck/build and deterministic generated contracts pass.
The E2E runner owns a unique migrated DB and API, cleans both up, and has a
30-second API startup and 180-second suite bound. The browser helper is test-only,
nonprivileged, capped at 1 GiB RAM and approximately 2.52 GB cached image size.
Host port 9323 is loopback-only; the container-private listener is not public.

Browser evidence distinguishes an intercepted network failure from the separate
**real test-DB removal -> repeated 503 -> recreation/migration -> Retry -> ready**
scenario. The original owner DB is not dropped or stopped. No live Meta/source
ingestion is involved. One existing Starlette warning recommends a future httpx2
test-client migration; tests currently pass and that unrelated migration is not
included here.

Resolved Python versions: FastAPI 0.162.0, Starlette 1.10.0, Pydantic 2.14.1,
SQLAlchemy 2.1.6, psycopg 3.3.6, Alembic 1.20.1. The earlier worker's FastAPI
1.10.0 report confused it with Starlette; installed metadata above is authoritative.
Proposed integration remains minor **0.4.0**: first application capability, no
previously released application API to break. Do not mark the backlog done until
the acceptance decision and target integration are recorded.

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

The commands are implemented; see README for required Node/test-DB setup:

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
Original feature candidate: `3c1d2b2`; repair contract: `923b1bf`; direct repair
base: `e7ad07b`. Direct verification is recorded above. The final tested repair
commit and target integration are recorded in the backlog, not guessed here.

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
