# Specification: One-command local stack (`./dev`)

> **Spec type:** Product/feature (developer tooling).
> **Load-bearing frameworks:** outcome, acceptance, scope. **Supporting:** failure conditions.
> **Date:** 2026-10-29. **Author:** orchestrator. **Decision owner:** project owner.
> **Status:** Draft -> awaiting owner "go" (owner approved the one-script direction October 29, 22:03 EDT).
> **Backlog ID:** FL-019. **Delivery state:** specifying.
> **Approved spec revision/date:** pending. **Integration version:** pending.
> **Zero-Question Score:** 0 unowned questions; open choices are listed in section 6 with defaults.

## How to Read This Spec

Owner: outcome and scope. Implementer: scope, contracts, ACs. Tester: ACs and failures.
Builds on [Dev environment](DEV_ENVIRONMENT.md) (one Compose project, one root `.env`).

## Notation Key

`[Validated]` = owner confirmed; `[Assumed: verify]` = proposed default. AC score 3 = binary.

## 1. Outcome Statement

After this increment the owner starts, inspects, tests and stops the complete local
application (PostgreSQL, migrations, built or hot-reloading frontend, API) with one command
from any checkout, without exporting `PATH`, running Compose, Alembic or npm by hand.
Verification: from a clean state `./dev up` ends with a printed URL and a healthy
`/api/v1/ready`; a second `./dev up` changes nothing; `./dev down` stops what it started.
Outcome score: 3.

## 2. Scope

### IN Scope

- `./dev` (bash shim) -> `scripts/dev.py` (Python 3.12, standard library plus existing
  dependencies; no new dependency).
- Commands: `up [--dev] [--no-build]`, `down [--db]`, `restart`, `status`, `logs [api|vite]
  [-f]`, `test [backend|frontend|e2e|all]`, `reset-data`, `env-check`.
- Starting PostgreSQL itself (`docker compose up -d --wait postgres`) and waiting for health.
- Pinned Node discovery (see 4), `uv sync --frozen` when the lock/VERSION changed,
  `scripts/init_env.py`, `alembic upgrade head`, frontend build when sources changed.
- API as a background process with pid file, log file and readiness wait; optional Vite
  dev server (`--dev`) on 5174 proxying to the API.
- Worktree awareness: a linked Git worktree gets its own database, storage root, ports and
  state directory, so parallel sessions never share mutable state.
- Documenting the commands in the README (replacing the manual sequence).

### OUT of Scope

- A devcontainer or containerized app/API/frontend (owner prefers lower load; revisit later).
- Production packaging, remote hosts, TLS, auth changes.
- Creating a database role per lane (lanes share the server role; separation is by database).
- Any provider (Meta), Taiga or Telegram behavior ([tracking](TRACKING.md)).

### Scope Dependencies

FL-018 (done). Docker/Compose reachable from the user shell. None else.

### Open Scope Tensions

None. The owner accepts one script over a devcontainer (October 29, 22:03 EDT).

## 3. Acceptance Criteria

| ID | Type | Given / when / then | Score | Annotation | Test |
|---|---|---|---|---|---|
| DV-1 | Behavioral | Docker running, no PATH changes, Postgres stopped, `.env` present: `./dev up` starts Postgres, applies migrations, builds the frontend if stale, starts the API, waits for `/api/v1/ready`, prints URL/DB/version/migration head/log paths and exits 0. | 3 | [Validated] | `test_up_sequence` (fakes), manual real run |
| DV-2 | Behavioral | `./dev up` when everything is healthy starts no second process, rebuilds nothing, restarts nothing, exits 0 and says so. | 3 | [Validated] | `test_up_idempotent` |
| DV-3 | Behavioral | `./dev down` stops only the API/Vite processes it recorded (verified by pid + command line), removes their pid files and leaves Postgres running; `down --db` also stops the postgres service; never runs `down -v`, `rm` of volumes, or removes unnamed services. | 3 | [Validated] | `test_down_scope` |
| DV-4 | Negative | Missing `.env`/Docker daemon down/port in use by a foreign process/missing Node: exits non-zero with one actionable message naming the fix command; no partial background process is left. | 3 | [Validated] | `test_preflight_errors` |
| DV-5 | Behavioral | Frontend rebuild happens iff the input hash (frontend sources, lockfile, config, `VERSION`) differs from the last successful build; build failure leaves the previous `dist` untouched and `up` fails. | 3 | [Assumed: verify] | `test_build_staleness` |
| DV-6 | Behavioral | In a linked worktree `./dev up` derives `<lane>` from the worktree directory, uses database `fieldlens_<lane>`, API/Vite ports `8101/5174 + lane offset`, storage `.local/fieldlens/storage-<lane>`, and state under that worktree's `.local/run`; it never touches the main checkout's database, ports or storage. `down --drop-lane` removes the lane database and storage after typed confirmation. | 3 | [Validated: lanes allowed by owner October 29] | `test_lane_allocation` |
| DV-7 | Edge case | State recovery: stale pid file (process gone or pid reused by another command), crashed API, killed script mid-`up`: next `./dev up`/`status` classifies state correctly, removes only stale files and continues. | 3 | [Validated] | `test_stale_state` |
| DV-8 | Behavioral | `./dev test` runs exactly the documented gates (backend: pytest, ruff check/format, strict mypy; frontend: typecheck, lint, vitest, contracts check, build; e2e: browser container started by service name, `scripts/run_e2e.py`, container stopped by service name afterwards) and exits non-zero if any fails, summarizing counts. | 3 | [Validated] | `test_test_command` |
| DV-9 | Negative | `reset-data` requires typing the database name, refuses when the API is running unless `--force`, refuses any database not named exactly like the configured app/lane database or whose name starts with `fieldlens_app_test_`, and prints what it deleted. | 3 | [Validated] | `test_reset_data_guards` |
| DV-10 | Non-behavioral | No secret value (password, token, `DATABASE_URL`) is printed, logged or put on a command line; `status` shows key names/presence only; child processes receive only the environment they already need. | 3 | [Validated] | `test_no_secrets_in_output` |
| DV-11 | Non-behavioral | The shim works from any working directory inside the checkout and under `set -u`; `./dev` with no arguments prints usage. | 3 | [Validated] | `test_cli_usage` |

Definition of done: all DV tests pass with real PostgreSQL where DB behavior is involved,
plus one recorded real run of `up`/`status`/`down`; actual commands/results in the handoff.

## 4. Context and Decisions

- **Node discovery order** `[Assumed: verify]`: `FIELDLENS_NODE_BIN` (directory) -> `node` on
  `PATH` if it equals `.node-version` -> first match of
  `.local/fieldlens/*/tools/node-v<version>-linux-x64/bin` in this or the main checkout.
  Otherwise fail with the README instruction. `npm` is taken from the same directory.
- **Readiness URL:** `GET /api/v1/ready` (also `/ready`); the Vite dev proxy already forwards
  `/api`, `/health`, `/ready`.
- **State directory:** `<checkout>/.local/run/` (gitignored): `api.pid`, `vite.pid`, `*.log`,
  `frontend-build.hash`. Logs rotate by truncation at 5 MiB.
- **Process ownership:** a pid file is trusted only if `/proc/<pid>/cmdline` still matches the
  recorded command; processes are started in their own session and stopped with SIGTERM, then
  SIGKILL after 10 s. No name-based killing.
- **Lane ports:** offset = (stable hash of lane name mod 20) * 10; API `8101 + offset`, Vite
  `5174 + offset`; collisions are detected, not assumed. Main checkout uses the base ports.
- **Lane `.env`:** a linked worktree has no `.env`; the script writes a derived file (mode
  0600) from the main checkout's values with `POSTGRES_DB`, `FIELDLENS_DATABASE_URL` and
  `FIELDLENS_STORAGE_ROOT` overridden and no tracker/provider keys copied.
- **Shared server:** every checkout talks to the one `fieldlens-postgres` container; lane
  databases are temporary and must be dropped with `down --drop-lane` after merge. The single
  long-lived manual-testing database remains `fieldlens_app` `[Validated: owner October 28]`.
- **Compose safety:** Compose commands always name the service
  (`postgres`, `browser`); never `rm`/`down` without a service name or with `-v` (a profile-wide
  `rm` previously removed the database container).
- Delegation: `fieldlens-backend`, branch `feature/fl-019-a-dev-script` from the then-current
  `master`; one writer; separate `fieldlens-qa`. Owned paths: `dev`, `scripts/dev.py`,
  `backend/tests/tooling/test_dev_*.py`, README run/test sections. Shared files (VERSION,
  CHANGELOG, BACKLOG, plan) stay with the orchestrator.
- Constraints: no new dependency; no network except loopback and Docker; no paid calls.

## 5. Failure Conditions

- Docker daemon unavailable, container unhealthy, or port taken: stop before side effects
  beyond Postgres, print the exact command to fix; never kill a foreign process.
- API fails readiness within 60 s: stop the API it started, keep Postgres, print the log
  tail path (not contents that could contain secrets), exit non-zero.
- Interrupted `up` (Ctrl-C): terminate only children it spawned; leave Postgres.
- Worst misinterpretation: `up` reports success because the process exists while readiness
  fails; DV-1 requires a successful `/api/v1/ready` response, not a live pid.

## 6. Ambiguity Audit

Defaults chosen (owner may override): `up` serves the built frontend from the API on 8101;
`--dev` adds Vite on 5174. Build staleness hash includes `VERSION` so version display stays
current. `reset-data` recreates the schema via Alembic, not by deleting the volume.
Pinned-Node discovery is limited to the paths above.

## 7. Implementation Guidance

Small modules in `scripts/dev.py`: `State`, `Lane`, `Node`, `Compose`, `Api`, `Frontend`,
command functions; subprocess/clock/ports injected so tests use fakes; one integration test
class against real PostgreSQL via existing test helpers. Keep the shim to a few lines
(`exec uv run python scripts/dev.py "$@"` after locating `uv`).

### Implementation handoff and integration

| Field | Record before handoff / after integration |
|---|---|
| Feature commits / tested HEAD | pending |
| Verification | pending |
| Compatibility assessment | New feature (minor); no API/schema change |
| Proposed changelog entry | FL-019: `./dev` one-command stack |
| Related documentation | README run/test sections, `.env.example` comments if needed |
| Integrated commit / final version | pending |

## Open Tensions

None.

## Assumption Registry

Node discovery order (M); lane port offset scheme (M); build hash inputs (H). Invalidated by
a changed Node pinning policy or a different frontend build tool.

## Adversarial Self-Critique

`up` could look healthy while serving a stale bundle (DV-5), or kill the wrong process after
pid reuse (DV-7). `reset-data` could hit the wrong database (DV-9). Lane `.env` generation
could leak a secret into a new file with wrong mode (DV-10, mode check in tests).

## Revision Triggers

A containerized app stack, a second developer machine, or a change to Compose service names.
