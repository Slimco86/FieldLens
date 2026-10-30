# Specification: One compose project and one `.env` for local development

> **Spec type:** Product/feature (developer environment). **Load-bearing frameworks:** outcome, acceptance, scope.
> **Supporting:** failure conditions.
> **Date:** 2026-10-28. **Author:** main orchestrator. **Decision owner:** project owner.
> **Status:** Approved by owner request and decisions on October 28 (single compose, central `.env`, fresh names/volume).
> **Backlog ID:** FL-018. **Delivery state:** in_progress. **Integration version:** pending (proposed patch).
> **Zero-Question Score:** 0 unowned questions.

## How to Read This Spec

Owner: outcome and scope. Implementer: sections 2-4 and 7. Tester: section 3.
Replaces the per-lane `db.env`/Compose-override convention introduced for the
first worktree allocation; application behavior and public API are unchanged.

## 1. Outcome Statement

After this increment a developer runs `docker compose up -d --wait`, then
`uv run alembic ... upgrade head` and `uv run uvicorn ...` with **no variable
exports or env-file flags**. All local settings come from one root `.env`
(gitignored, bootstrapped by a script, documented by a tracked `.env.example`),
and one Compose project (`fieldlens`) owns every local container.
Verification: AC-1..AC-8 below; backend tests and E2E run from a fresh terminal.
Outcome score: 3.

## 2. Scope

### IN Scope

- Root `compose.yaml` (replacing `infra/compose.yaml` and `infra/compose.browser.yaml`)
  with a default `postgres` service and a Playwright `browser` service under the
  Compose profile `test`. Fixed project name `fieldlens`; one named data volume;
  loopback-only published ports; existing image digests and limits retained.
- A tracked `.env.example` and an idempotent bootstrap script that appends the
  missing local keys to the existing `.env` (random password, mode 0600) without
  rewriting or printing any existing value such as `MODEL_API_KEY`.
- Python application, Alembic, test support and `scripts/run_e2e.py` load the
  repository-root `.env` automatically (independent of the current directory).
  Real environment variables take precedence over `.env`.
- The test database URL is derived from the same configuration as a unique
  `_test_<8 hex>` sibling, so `FIELDLENS_TEST_DATABASE_URL` is optional. Existing
  safety checks stay: loopback only, no query overrides, never the app/demo DB.
- Browser tests get their endpoint/network settings from `.env` defaults.
- README, the foundation/workspace specs and agent allocation notes that name
  `db.env`, `infra/compose*.yaml`, `fl-004/fl-015` projects, or manual exports.

### OUT of Scope

- Application behavior, API, schema, migrations, frontend code.
- Reading, rotating or relocating `MODEL_API_KEY`; any provider call.
- Deleting old Docker volumes or data. Removing the stopped legacy containers
  is an orchestrator step after acceptance, never `down -v`.
- Containerizing the API/frontend, new services, secret managers.

### Scope Dependencies

None. Base is `master` at `c14cff4` (0.5.0).

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Test |
|---|---|---|---|---|
| AC-1 | Behavioral | From a fresh shell with no FIELDLENS_*/POSTGRES_* variables exported, `docker compose up -d --wait` starts exactly one container (`postgres`) in Compose project `fieldlens`; `docker compose --profile test up -d --wait` adds only the Playwright browser | 3 | command run from clean `env -i`-style shell |
| AC-2 | Behavioral | `uv run alembic -c backend/alembic.ini upgrade head` and `uvicorn fieldlens.app:create_app --factory` use `.env` with no exports; `/ready` is healthy and the project API persists across an API restart | 3 | scripted run + `test_dotenv_*` |
| AC-3 | Behavioral | `uv run pytest backend/tests`, `npm --prefix frontend run test:e2e` run in a fresh shell without `FIELDLENS_TEST_DATABASE_URL`, `PW_TEST_*` or credential exports; same results as before (193 backend, 15 Vitest, 9 E2E) | 3 | full gate run |
| AC-4 | Negative | A real environment variable overrides `.env`; an explicit `Settings(_env_file=None)`/DB-less test configuration never picks up `.env`; tests never target the app database or any name containing `demo` | 3 | unit tests |
| AC-5 | Negative | Bootstrap is idempotent, keeps every existing line (incl. `MODEL_API_KEY`) byte-for-byte, creates keys only when absent, sets mode 0600, and prints no secret; it never overwrites an existing password | 3 | tests with a temp dir |
| AC-6 | Negative | Only `MODEL_API_KEY` (owner decision 2026-10-30 13:41 EDT) may be adopted, by the application settings loader alone, as a provider secret that is never logged, echoed or stored; any other non-`FIELDLENS_`/`POSTGRES_` key is not loaded; scripts/loader and derived lane `.env` files stay allowlist-only, and default tests run with the key forced blank (offline, socket guard kept); `.env` stays gitignored and `.env.example` contains no real secret | 3 | test + `git check-ignore`, `git grep` |
| AC-7 | Edge case | Missing/incomplete DB configuration fails with an explicit message naming the bootstrap command; unsafe test URL rules (loopback, no query overrides, name pattern) still fail explicitly | 3 | existing isolation tests updated |
| AC-8 | Integrity | Docs contain no stale `db.env`, `infra/compose`, `fl-004-a-foundation` runtime paths or manual-export steps (historical records excepted and labeled); lint/format/mypy/contracts/build pass | 3 | `git grep` + gates |

## 4. Context and Decisions

- Decisions (owner, October 28): single Compose project; all local variables in
  the root `.env` loaded automatically by code; **fresh** role `fieldlens`, database
  `fieldlens_app`, volume `fieldlens_pgdata`; old `fl004a`/`fl015a` volumes untouched.
- Ports stay: API 8101, Vite 5174, PostgreSQL 55432, browser 9323 (all loopback).
- Test database names become `fieldlens_app_test_<8 hex>`; the validator pattern
  and `run_e2e.py` change accordingly and keep the `demo` guard.
- Only `FIELDLENS_*` and `POSTGRES_*` keys are loaded into application/test
  environments; other keys in `.env` are ignored by code.
- Delegation: `fieldlens-backend` (config/persistence/test infrastructure;
  interconnected, security-sensitive), one writer on branch
  `feature/fl-018-dev-environment` from `c14cff4` in `/home/slimco/code/FieldLens`.
  Independent `fieldlens-qa` acceptance follows. The dirty
  `.github/copilot-instructions.md` is the orchestrator's and is excluded.

## 5. Failure Conditions

- `.env` missing keys -> explicit error pointing at the bootstrap script, never a
  silent default pointing at some other database.
- Bootstrap run against an `.env` that already has a password -> unchanged; a
  rotated password with an existing volume is documented, not automated
  (Postgres fixes credentials at first initialization).
- Worst misinterpretation: tests pass because they read the application database
  or a stale shell export. ACs 3/4 therefore run from a clean shell and assert the
  derived test database is a fresh sibling that is dropped afterwards.

## 6. Ambiguity Audit

No open questions: names, ports, profile layout and cleanup scope are decided above.

## 7. Implementation Guidance

Prefer small changes: pydantic-settings `env_file` anchored to the repo root with
a `FIELDLENS_*`/`POSTGRES_*` filter for process environments, one shared loader
reused by Alembic/test support/E2E, and Compose's native root `.env` handling.
Implementation record (implementer view; independent QA pending):

- Naming scheme: `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` (shared by Compose and
  the application), `FIELDLENS_DB_PORT`, `FIELDLENS_DATABASE_URL` (composed with `${VAR}`
  interpolation, verified in Compose and python-dotenv), `FIELDLENS_STORAGE_ROOT`, and
  `FIELDLENS_PW_CONNECT_WS_ENDPOINT`/`FIELDLENS_PW_EXPOSE_NETWORK` (mapped by the E2E runner to
  `PW_TEST_CONNECT_*` so only `FIELDLENS_*`/`POSTGRES_*` keys are ever loaded). Required
  variables use `:?` messages naming `uv run python scripts/init_env.py`.
- Loader: `backend/fieldlens/localenv.py` (root `.env`, cwd-independent, filtered parse that
  never reads other keys) plus `Settings.model_config["env_file"]` for the application and
  Alembic. Test support derives `fieldlens_app_test_<8 hex>` unless
  `FIELDLENS_TEST_DATABASE_URL` is set. Removed `infra/compose*.yaml`.
- Tests: 26 new (`test_dotenv_loading`, `test_init_env`, derivation cases in
  `test_test_isolation`); 219 backend, 15 Vitest, 9 E2E passed from `env -i`-style shells.

| AC | Evidence (implementer) |
|---|---|
| AC-1 | `env -i ... docker compose up -d --wait` started only `fieldlens-postgres` (project `fieldlens`, volume `fieldlens_pgdata`); `--profile test` added only the browser |
| AC-2 | `alembic -c backend/alembic.ini upgrade head` and uvicorn (started from `/tmp`) with no exports; `/ready` 200; project persistence across restart by E2E `project-lifecycle`; `test_dotenv_*` |
| AC-3 | backend 219, Vitest 15, E2E 9 passed from `env -i` with no `PW_TEST_*`/credential/test-URL exports |
| AC-4 | `test_real_environment_overrides_the_env_file`, `test_explicit_no_env_file_configuration_ignores_dotenv`, isolation tests (`demo`, app DB, legacy names) |
| AC-5 | `test_init_env.py` (idempotence, byte-for-byte prefix, 0600, no printed values, password never overwritten) |
| AC-6 | `test_loader_returns_only_fieldlens_and_postgres_keys_with_interpolation`, `test_provider_key_is_never_adopted_*`; `git check-ignore .env`; `.env.example` has no secret |
| AC-7 | `test_missing_database_configuration_names_the_bootstrap_script`, updated unsafe-URL cases; Alembic error names the script |
| AC-8 | `git grep` leaves only labeled historical/tooling references; lint, format, mypy, contracts, build pass |

Tested SHA and release version: see the handoff/commit; version bump proposed (patch) by the
implementer, applied by the orchestrator.

## Open Tensions

None after owner decisions.

## Assumption Registry

| Assumption | Confidence | Invalidation signal |
|---|---|---|
| Compose reads the root `.env` automatically next to a root `compose.yaml` | H | `docker compose config` shows unset variables |
| Postgres credentials are fixed at first volume initialization | H | fresh volume rejects the new role/db |

## Adversarial Self-Critique

- A silent fallback to a default database would hide misconfiguration: AC-7.
- Loading the whole `.env` would leak the provider key into test processes: AC-6.

## Revision Triggers

Reopen if containers for the API/frontend are introduced, secrets move to a
manager, or a second database lane is required.
