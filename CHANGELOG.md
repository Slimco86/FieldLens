# Changelog

Human-readable changes by integration version. Versions use major.minor.patch:
breaking changes increment major, features minor, fixes/documentation patch.
See the [workflow](docs/DEVELOPMENT_WORKFLOW.md) for classification and merge rules.

## Unreleased

No unreleased changes.

## 0.22.0 - 2026-11-01

- **TASK-041 (FL-022-D):** Added visual-level production/completion equipment candidates (EQ-8..EQ-10, offline stub
  verified; no live result yet) on the extraction harness: a closed taxonomy (casing, liner, tubing, packer, pump,
  bearing, perforation interval, isolation, accessory, other) with optional printed material, sizes and depths; a
  versioned prompt; page plans by content hash for the F-14 and F-5 completion documents (with the rotated F-14
  schematic); wrong-well documents excluded before any model call; wellbore attachment through identity, never named by
  the model; every candidate is model-read, unverified, never accepted and never used in calculations; flag-not-drop
  validators; category/wellbore filters on the candidate API. Shared validators hardened (a unit written away from its
  value is flagged, depths must sit on the item's own line, a page naming another well overrides the cover rule,
  glued `95/8` is ambiguous). A page whose image cannot be produced fails the unit before any provider call. Added a
  guarded live runbook `scripts/run_equipment_live.py` (dry run by default; requires an explicit allow flag, a spend cap
  and the live-meta environment flag; refuses the application database) and a project bootstrap helper. Contracts are
  additive; no migration. Known limits: PDFs have no record link to a wellbore (attachment uses a caller-bound label,
  not checkable on scans), the database does not itself forbid relabelling an equipment row as accepted, and the
  lane-database guard does not look at a `dbname` query override.

## 0.21.1 - 2026-11-01

- **TASK-034 integration polish:** The extraction candidates section (TASK-036) in the evidence panel now uses the design
  kit (heading, state/validation/evidence chips with icons, kit buttons, loading/error/empty states, card layout), and
  the status chips cover the `unverified` validation state and `model_proposal` evidence class. Frontend only.

## 0.21.0 - 2026-11-01

- **TASK-034 (FL-021-A):** Replaced the unstyled prototype with a designed application shell: Mantine light theme
  (cobalt brand, self-hosted Inter, lucide icons) built from one token set with a style-scan and contrast checks, a left
  sidebar for project list/create/edit/switch, URL-routed Sources / Reconstruction / Explore tabs with honest
  prerequisites, the Explore region layout (tree, stage, inspector, dock), status/evidence chips with text and icon,
  and redesigned Sources screens (upload dropzone, files table, job and revision panels, inspection and evidence
  views) with truncated long names and IDs that stay keyboard-reachable and copyable. Evidence records re-read until
  they match the report. No API change; no remove/replace/delete controls (their backend is not built). Initial JS
  163 kB gzip, zero external requests, axe clean on the tested states. The one stale e2e assertion (UP-1) was updated
  to the settled "Unsupported" state. Independent UI reviewer score 4/5; owner sign-off pending.

## 0.20.0 - 2026-11-01

- **TASK-036 (FL-022-A):** Added model-proposed extraction candidates with deterministic validation (offline stub
  provider only, no live calls): migration `0010_extraction_candidates` (`extraction_candidate`, reservation link on
  `agent_work_unit`), a closed JSON candidate schema, read-only project-scoped tools (read span, read table, project
  search, page image), pypdfium2 page rendering (about 1600 px, cache by blob/page/scale/rotation, text-layer
  orientation correction, explicit rotation), text-layer page triage, and validators that reject values that are only
  part of a longer number, check units against the quote, parse fractions, Unicode minus and decimal commas strictly,
  require the subject to be named by the source, verify page-item fields, flag parsed-value conflicts against the whole
  parsed set and flag every coordinate or trajectory-type candidate pending AX-11. Image-only reads are `model_read`,
  unverified and rejected by the calculation entry. Per-unit budget reservations link to the activity log, finished
  units settle on startup recovery, `step_key` carries an ordinal, and a candidate read API and evidence-view list were
  added. New dependencies `pypdfium2` and `Pillow`. Known limits: the image-only orientation check is opt-in (it
  rotated upright scans), no render timeout, triage selects nothing for the scanned F-14/F-5 documents (pages are
  supplied explicitly), and a unit written away from its value is not detected (follow-up).

## 0.19.0 - 2026-10-31

- **TASK-047 (FL-005-F):** Added full-resolution time-series storage for LAS curves and daily production:
  migration `0009_series_storage` (`series_axis` with one shared index per data block, `series_curve` with float64
  value arrays, NaN for missing samples, per-curve counts/min/max/unit/NULL sentinel, evidence and a series revision hash),
  written atomically with the extraction run and superseded or cascade-deleted with it; read-only
  `GET /api/v1/projects/{id}/series`, `.../series/{series_id}` and `.../series/{series_id}/window` (deterministic
  min/max- and gap-preserving downsampling `minmax-gap-v1`, bounded full-resolution mode, stable cache key, ASCII-only
  bounds, `decreasing`/`non_increasing` index orders) and the typed `SeriesService` for charts and agent tools. LAS and
  production profiles are v2 (existing runs re-derive; LAS parsing uses compact arrays: 792 MB -> 146 MB peak on 234 real
  files). A LAS file with a free-text data header (for example `15_9-19_A_CPI.las`) or a column-count mismatch stores no
  series. On the real subset 172 LAS files store series (970,241 samples) and production stores 7 wellbores / 15,634 days;
  the independent re-read matched exactly. Time-indexed or wrapped LAS files store no series (follow-ups in TASK-045).
  Migration renumbered from 0008 to 0009 at integration (after TASK-046).

## 0.18.0 - 2026-10-31

- **TASK-046 (FL-005-E):** Depth values in the perforation and formation-pick tables that carry no documented unit now
  default to meters (measured depth) with one non-blocking `MISSING_UNIT` warning per file, and missing depth
  references warn instead of blocking (profile versions 3; stated units always win; TWT, azimuth, coordinates, blanks and
  flagged picks are untouched); a defaulted depth beyond 105% of the known trajectory/log MD range emits
  `SUSPICIOUS_VALUE`. Added deterministic well/wellbore identity: one label rule shared with retrieval
  (`fieldlens.identity.labels`, retrieval behaviour unchanged), migration `0008_identity_links`
  (`well.well_key`, `wellbore.wellbore_key/suffix`, `record_wellbore_link`), post-extraction resolution with
  `IDENTITY_MISMATCH` findings for ambiguity, production-workbook `H`/`AH` bores aliased to the observed base wellbore
  with one warning, and `GET /api/v1/projects/{id}/identity`, `.../identity/wellbores/{id}/evidence` and
  `POST .../identity/resolve`. On the approved real subset: 19 wells, 35 wellbores, 17,136 records linked, none
  unresolved. Parent links are naming-based, not a drilling relationship. Independent QA passed with low notes
  (follow-ups in TASK-045).

## 0.17.0 - 2026-10-31

- **TASK-011 (FL-011-A):** Added project- and source-scoped retrieval over the extracted source observations:
  migration `0007_source_retrieval` (`retrieval_index`, `evidence_chunk` with stemmed and simple full-text vectors,
  `chunk_identifier`, `chunk_embedding`); a deterministic chunker (`chunker-3`, target 400, hard cap 480 estimated
  tokens; headers and units repeated, numbers never orphaned); exact-identifier resolution (well, wellbore and
  sidetrack distinct, nonexistent suffixes reported as unmatched, ambiguity returned explicitly), PostgreSQL
  full-text and exact-cosine pgvector search fused by RRF(60) with eligibility applied before ranking, at most 10 chunks
  and 12,000 tokens; per-hit support flags and a `weak_evidence` status (relevance floor and margin uncalibrated);
  `GET /api/v1/projects/{id}/retrieval/search` and `/retrieval/coverage`; a leased index runner on the job worker with
  ANALYZE policy; local embeddings via pinned FastEmbed `bge-small-en-v1.5` (int8 ONNX, MIT) behind the explicit
  hash-pinned `scripts/fetch_embedding_model.py`, with an explicit degraded mode (exact + full text) when unavailable;
  numeric production/trajectory tables excluded from vectors by owner policy; `fastembed` dependency. Four independent
  QA rounds (no cross-project leak at any point) found and fixed a 30-55 s cold first search, a 500 on NUL, mislabelled
  modes, missing stemming, sidetrack/parent identity leaks and lone-frequent-word false strength. Offline tests only;
  no real-data recall claim; follow-ups in TASK-045. Integration fix: a type annotation in the TASK-030 spike script
  `scripts/spikes/ocr_common.py`, needed because the new embedding dependencies make Pillow's types visible to mypy.

## 0.16.3 - 2026-10-31

- **TASK-030 phase A (FL-005-C):** Added the offline OCR/rendering/orientation evaluation for the scanned completion
  pages: `scripts/spikes/ocr_*.py` and `docs/evidence/TASK030_OCR_EVALUATION.md`. Findings (agent-read reference, not
  human-verified): RapidOCR with onnxruntime recovers 63-66 of 67 reference numbers at 300 dpi (Tesseract 54/67), only the
  rotated schematic needs a second pass, and an OCR-agreement rule would have confirmed 265 of 278 model-read numbers
  while rejecting the judged misreads; the legacy F-5 completion `.doc` has extractable text and 12 pictures (macros
  present, never read). Records the phase B design, its contract needs (an OCR issue code, no EvidenceClass change),
  third-party notices and owner decisions. No product code, contract, migration or lockfile change; the final
  evidence-text commit was reviewed by the orchestrator, not re-QA'd.

## 0.16.2 - 2026-10-31

- **TASK-044 (FL-005-D):** Added the offline check of the deferred 211 MB EDM export (PV-24) for production/completion
  equipment and perforation history: streaming spike scripts in `scripts/spikes/` (reusing the hardened XML parser,
  about 5 s and 38 MB for a full census) and `docs/evidence/TASK044_EDM_COMPLETION_CHECK.md`. Finding: the export is a
  drilling/planning database with no installed completion, perforation or dated history for F-12, F-14 or F-5, no
  units, and conflicting scenario/case datum elevations (177.165 versus 180.118); only F-14 A has design-variant
  tubing, liner and packer data (design packer depth conflicts: 8350.07 versus 8678.15). A streaming EDM profile is not
  recommended for this purpose. No product code changed; the final wording-only evidence commit was reviewed by the
  orchestrator and not re-QA'd.

## 0.16.1 - 2026-10-31

- **TASK-042 (FL-022-E):** Added the live feasibility spike of model reading of the seven approved completion
  PDFs: reviewable scripts in `scripts/spikes/` (survey, render, live runner behind `--live`, scoring) and
  `docs/evidence/TASK042_COMPLETION_SPIKE.md`. Findings (live `muse-spark-1.3` on an agent-read, not
  human-verified reference): typed equipment candidates are read reliably from upright page images at about
  1600 px and `low` effort (strict 68/83 uniform, 80/83 tuned), depths and units exact as printed, no invented
  items on control pages, but small-print digit misreads and silent empty answers on rotated pages; scanned
  documents need OCR first; the three completion reports in the F-12 folder describe F-11 wells, so no F-12
  production equipment exists in the seven files; F-11 B perforation history appears on PV-11 pages 74 and 136
  (with a 4065 versus 4063 disagreement). Spend USD 2.9036 at placeholder rates (real about one sixth,
  unverified). No product code changed.

## 0.16.0 - 2026-10-31

- **TASK-043 (FL-003-C):** Hardened the provider adapter from the live MI-6 findings: optional per-request
  reasoning effort (`minimal`/`low`/`medium`/`high`; unset keeps the provider default and old recordings still
  replay), a tool- and reasoning-aware input-token reservation bound (a one-tool request now reserves at least the
  552 billed tokens), explicit in-flight cancel settlement (the call still bills and is settled; cancel does not
  stop billing), 404/405 rejections settled as non-billable while every other 4xx stays liable, and ledger helpers
  to list, reconcile and release liable reservations that never go below known billed attempts. Rate cards are
  validated before registration; no rates changed. Independent QA found two medium defects, repaired and
  re-verified. Offline only: effort acceptance, the 404/405 non-billing rule and multi-tool token bounds are not
  yet verified live.

## 0.15.0 - 2026-10-31

- **TASK-038 (FL-022-B):** Added the persisted, project-scoped agent activity log (AX-10 backend):
  migration `0006_agent_activity_log` (`agent_work_unit`, `agent_step`), a fenced write service for the
  extraction harness (start/append/finalize, restart-safe interruption and resume without duplicate steps),
  conservative secret redaction and size bounds including evidence locator text, and read endpoints
  `GET /api/v1/projects/{id}/agent-units[/{unit_id}]` with generated client types. No hidden reasoning is stored
  and the log is never an engineering source. Independent QA found one medium defect (locator text not
  redacted or bounded), repaired and re-verified. Deferred to TASK-036: startup recovery wiring, budget
  reservation link, cancel/retry endpoints. Offline only; no UI (TASK-040).

## 0.14.1 - 2026-10-31

- **TASK-005 (FL-003-B):** Added the opt-in live Meta smoke (MI-6): `test_meta_live_smoke` behind the
  `live_meta` marker and an explicit `FIELDLENS_LIVE_META=1` plus a real-environment `MODEL_API_KEY` (default
  runs exclude it, blank the key and keep the loopback socket guard), with evidence in
  `docs/evidence/MI6_LIVE_SMOKE.md`. Live findings on `muse-spark-1.3` (Responses): text, tool round trip with
  reasoning replay and synthetic image input work; there is no embeddings endpoint; reasoning effort defaults to
  high and consumes output tokens; the input estimator under-counts tool requests (about 2.3x); in-flight
  cancel still bills. Adapter fixes are tracked as TASK-043. Placeholder-rate upper bound about USD 0.42
  across two runs (one accidental during QA), real rates and balance unconfirmed. No runtime code changed.

## 0.14.0 - 2026-10-30

- **TASK-009 (FL-005-B):** Added versioned native source profiles with attribute-level
  evidence (WITSML tubular/BHA run/bore geometry/trajectory, Volve production workbook, LAS 2.0,
  perforation and well-pick tables, Compass survey-report PDF), content-based detection, a
  persistent bounded extraction runner (leases, fenced finalize, idempotent re-runs, supersede on
  profile version change), `/extraction` endpoints and DTOs, five new data-quality codes
  (`MISSING_REFERENCE`, `MISSING_UNIT`, `SUSPICIOUS_VALUE`, `UNKNOWN_CODE`,
  `ASSEMBLY_TYPE_MISMATCH`) plus identity-mismatch reporting, a 500-page PDF limit and an evidence
  panel in source inspection. Migration `0005_native_profiles`; dependency `pypdf`; opt-in
  `FIELDLENS_LOCAL_DATA_ROOT` local-data test and a lane-safe `FIELDLENS_E2E_API_PORT` e2e override.
  On the real subset all 18 files produce reports; trajectory, production and perforation
  records exist for F-12, F-14 and F-5, equipment is drilling-side only, and perforation/pick
  depths stay `unsupported` (no documented unit/datum). Independent QA found a report-endpoint
  500 and nine further defects, all repaired and re-verified. EDM export, grids, completion PDFs
  and OCR remain deferred.

## 0.13.0 - 2026-10-30

- **TASK-004 (FL-003-A):** Added the offline provider adapter in `backend/fieldlens/assistant/`:
  message model with image parts and tool-call round trips, stub/replay/recorder providers, the
  Meta Responses wrapper (never called by default tests; no live calls), a PostgreSQL budget
  ledger (USD 150 ceiling; reserve/settle/release/reconcile; overruns are flagged and pause the
  period) and bounded work units (4 attempts, configurable tool-call bound default 6, 90 s,
  USD 0.50) with typed refusal/truncation/malformed/timeout/cancellation handling. Migration
  `0004_provider_budget`; dependency `openai`. Owner decision: the single provider key variable is
  `MODEL_API_KEY`, adopted only by the application settings as a secret (DEV_ENVIRONMENT AC-6
  amended); default tests force it blank. Independent QA found six defects, all repaired and
  re-verified. Meta behaviour, billing and token bounds remain unverified until TASK-005.

## 0.12.1 - 2026-10-30

- **Fix (FL-019):** `./dev up` failed in `alembic upgrade head` when the shell had `.env`
  exported verbatim by an editor terminal (`${FIELDLENS_DB_PORT}` left unexpanded in
  `FIELDLENS_DATABASE_URL`). Settings now resolve `${VAR}` references (undefined ones are
  rejected without echoing the URL), and the test harness ignores such unexpanded values.

## 0.12.0 - 2026-10-29

- **FL-020-C:** Added the one-way backlog -> Taiga mirror (`scripts/taiga_client.py`,
  `track.py plan|sync [--apply] [--keep-drift] [--notify] [--only IDs]`): features become user
  stories and tasks become tasks under their parent in sprint `Hackathon`, with tags (priority,
  agent), status per spec 4.2, due dates, owner assignment, blocked flags/notes from unmet
  dependencies and `#ref` dependency links. Idempotent against live state (detail fetch per
  matched item), drift reported/overwritten, retries/re-auth, operation lock, atomic 0600 state
  file, privacy/secret guards (refuses a public project without `TAIGA_ALLOW_PUBLIC=1`),
  optional Telegram summary. Orchestrator profile and workflow now require Telegram progress
  notifications. No application, API or schema change. Independent QA: live smoke (8 items,
  zero-write rerun), 536 backend tests; live `is_blocked=true` and 429/5xx paths verified on fakes only.

## 0.11.0 - 2026-10-29

- **FL-020-B:** `docs/BACKLOG.md` is now a machine-checkable ledger: one block per feature
  (FL-000..FL-020) and task (TASK-001..TASK-032) with status, priority, tags, dependencies,
  assignee, due date, sprint, spec and version; all earlier narrative is kept verbatim under
  `## Journal`. Added `scripts/ledger.py` (strict parser/validator: required fields, enums,
  duplicate IDs, dependency existence/cycles/due order/priority order, done evidence, secret
  guard, no echo of values) and `scripts/track.py check|list|plan` (no network yet; Taiga sync is
  slice C). TASK-001 is recorded as in_progress (DA-7 not yet verified for every profile);
  TASK-003's done status keeps a documented owner-exception dependency on it. No application,
  API or schema change. Independent QA PASS after one repair round (517 backend tests).

## 0.10.0 - 2026-10-29

- **FL-019-A:** Added `./dev`, a one-command local stack (`scripts/dev.py`): `up [--dev]`
  starts PostgreSQL (service-named Compose), applies migrations, rebuilds the frontend only when
  its inputs changed (atomic swap), starts the API with pid/log files and waits for a real
  `/api/v1/ready`; `down [--db]`, `restart`, `status`, `logs`, `test [backend|frontend|e2e|all]`,
  `reset-data` (typed confirmation, never the test DBs), `env-check`. Idempotent, operation
  lock, SIGINT/SIGTERM cleanup, child environment allowlist (no credentials), and
  worktree lanes with their own database/ports/storage (`down --drop-lane`). Known limits: lane
  Vite still proxies to port 8101 and `./dev test e2e` is fixed to 8101. No application, API or
  schema change. Independent QA PASS after three rounds (450 backend tests, real up/down runs).

## 0.9.0 - 2026-10-29

- **FL-020-A:** Added `scripts/notify.py`, a send-only Telegram progress notifier for the
  orchestrator: event vocabulary with 🔴 ACTION NEEDED versus 🟢/🔵/⚪ status markers, dry-run,
  `--best-effort`, 60 s duplicate suppression, secret redaction/refusal, config-shape
  validation, and an optional allowlisted inbox (`TELEGRAM_INBOX=1`, off by default; stores
  commands only, executes nothing). `scripts/toolenv.py` loads only `TELEGRAM_*`/`TAIGA_*` keys
  with dotenv comment semantics (worktrees fall back to the main checkout's `.env`);
  `fieldlens.localenv` is unchanged. `.env.example` documents the empty keys. No application,
  API or schema change. Independent QA PASS after two repair rounds (396 backend tests).

## 0.8.0 - 2026-10-29

- **FL-005-A (TASK-006):** Added project-scoped upload, storage and persistent jobs plus the
  upload/source UI. Backend: `POST /api/v1/projects/{id}/imports` (metadata part first, files
  aligned by index; 202 new / 200 replay / 409 one staging import per project / 415 unknown
  binaries), streamed 128 MiB/file, 512 MiB/batch and 200-file limits, content-hash blob
  storage, immutable source revisions with idempotent replay, fenced restart-safe jobs with one
  automatic retry, staging sweep, migration `0003_upload_jobs`, `python-multipart`. Files are
  stored and hash-verified only: no extraction, evidence claims or asset-model publication
  (unknown plain text is `unsupported`; readers and the 500-page PDF / XLSX XXE and ZIP-entry
  parse-time checks arrive with TASK-009). UI (`features/uploads`): multi-file upload with
  limit validation, progress and abort, explicit stored/unsupported/pending-extraction
  labels, revision/quarantine/partial-revision warnings, label edit with version conflicts,
  job status/cancel and idle-stopping polling; keyboard/focus and 320 px layouts. Independent
  QA: backend passed IN-1/3/4/5/7 after two repair rounds (rejected-import blob, stale staging
  files); UI passed after three rounds (focus management, "superseded" wording, 320 px
  overflow, keyboard-scrollable table, focus after removal). 380 backend (1 skipped: TASK-009),
  38 vitest and 12 browser E2E tests. Known low gaps: tab buttons break mid-word at 320 px;
  orphan-blob sweep, a real quarantined-revision browser run, 128 MiB/200-file browser runs and
  non-Chromium browsers are unverified; "superseded" is judged from the loaded page only.

## 0.7.0 - 2026-10-29

- **FL-008-A (TASK-008):** Added the deterministic perforation state engine
  `fieldlens.engineering.perforation`: as-of replay of wellbore-scoped events, unique-MD
  interval union (exact decimals, ft/m), `unknown` instead of verified zero without a
  baseline, scope-specific interval state (well-level production/shut-in never erases or
  assigns interval state), commutativity-based order analysis that never invents an order
  (over-budget groups report unresolved axes, never definite values), dataset-revision
  correction chains and per-event validation (implausible/overflow depths rejected without
  losing valid history). Engine and unit tests only: no API, UI, migration or PostgreSQL
  persistence (PH-6 persistence, PH-1/4/8 and day-range queries remain open). Independent
  QA of `aaf0fdd` passed PH-2/3/5/7/9 and engine PH-6 (299 backend tests; brute-force
  oracle over 14,488 queries with no wrong resolved result). Assumptions awaiting owner
  confirmation: a baseline precedes same-instant events; correction-chain rule; 100,000 m
  MD plausibility bound; 12-event/32-state exploration budget.

## 0.6.0 - 2026-10-29

- **FL-006-A (TASK-007):** Added the deterministic trajectory engine
  `fieldlens.engineering.trajectory`: double-precision minimum-curvature coordinates,
  survey validation that blocks affected geometry (missing CRS/datum/depth/north reference,
  unresolved magnetic/true conversion, nonfinite angles, bad MD), and bounded 3D closest
  approach with an explicit error bound (<= 0.02 m). Adds `numpy`. Engine and unit tests
  only: no API, renderer or pyproj transform. Proximity is not proof of connectivity or
  safe clearance. Independent QA of `532d517` passed TR-1/2/3 (233 backend tests); known
  low gaps: deadline can overrun inside piece construction, near-duplicate MD is not
  flagged, `depth_reference` is not compared between bores.

## 0.5.1 - 2026-10-28

- **FL-018:** Replaced the per-lane Compose files and `db.env` credentials with one
  root `compose.yaml` (project `fieldlens`: PostgreSQL plus a `test`-profile browser) and
  one gitignored root `.env`. The API, Alembic, tests and the E2E runner load `.env`
  automatically (real environment variables still win); `MODEL_API_KEY` is never loaded
  into application or test processes. `uv run python scripts/init_env.py` creates the
  missing keys idempotently, with 0600 mode and a generated password.
- Fresh names: role `fieldlens`, database `fieldlens_app`, volume `fieldlens_pgdata`.
  **Data in the old `fl004a`/`fl015a` volumes is not migrated** and the volumes are
  untouched. Tests derive a throwaway `fieldlens_app_test_<hex>` database and never use
  the application database. `infra/compose*.yaml` was removed.
- Independent QA of `2bc4129` passed AC-1..8 from a clean shell: 219 backend, 15 UI,
  9 E2E, lint/type/contract/build checks. Known limitations: hand-edited passwords
  containing `@`, `$` or `%` are not validated (generated passwords are safe), the
  not-configured readiness message does not yet name the bootstrap script, and
  `frontend_dist` stays cwd-relative.

## 0.5.0 - 2026-10-28

- **FL-015-A / TASK-025:** Added persistent project list/create/open/edit APIs
  and keyboard-accessible workspace navigation. Project switching discards stale
  reads and save acknowledgements; reload restores the selected existing project.
  Empty projects expose prerequisites without fabricated assets or upload controls.
- Added typed project requests and cursor pagination, plus migration
  `0002_project_lifecycle` for the existing 4000-character description contract
  and newest-first index. Run `uv run alembic -c backend/alembic.ini upgrade head`;
  valid foundation data is preserved. This is an additive feature, not a breaking
  public-contract change.
- Independent QA found invalid NUL input misreported as a storage failure.
  Repaired NUL/unpaired-surrogate validation now returns typed 422 errors before
  database access. Independent re-verification passed on `2af22aa`: 193 backend,
  15 UI and 9 real API/PostgreSQL browser tests, plus invalid-text and migration
  preservation probes. The browser runner supports real API process restarts.
- Uploads/jobs and their workspace criteria remain the next packet. No original
  source qualification, provider call, push, tag or publication is included.

## 0.4.0 - 2026-10-28

First runnable local foundation. The owner accepted tested repair `95da2b7` and
authorized merging it into master using direct verification as a **one-time
exception**. Independent QA remains required for future features. Integration
is recorded in the backlog; no push, tag or external publication is included.
The initial backend invocation regained editing tools, but the repair invocation
lost them again; its precise cache/registration/model-interaction cause is not proven.

- **FL-004-A / TASK-003:** Added FastAPI health/readiness, PostgreSQL migration
  baseline, typed/generated contracts, local session guards and React shell.
  Repaired nested evidence scope, generic/catalog authority bypasses, finite
  metadata/image/quantity validation, read limits and test database isolation.
  Retry retains keyboard focus, runtime metadata derives from VERSION, Node 24
  is pinned/enforced, and startup/test documentation is usable.
- Added a digest-pinned, test-only Playwright Noble browser with Docker Desktop
  loopback forwarding. The CLI suite now verifies loading, network failure,
  real database-unavailable state and keyboard Retry recovery against an owned,
  disposable API/database. No application container or host OS upgrade.
- Direct validation: 124 backend, 4 UI and 3 CLI E2E tests pass; affected
  lint/type/build/contracts checks pass. This is not independent re-verification.
- **FL-001:** Record mandatory separate-agent acceptance, repair re-verification
  and completion of the authorized commit/merge cycle for every logical feature.

- **FL-001 / FL-004:** Owner approved serial development in the existing checkout:
  one feature branch and one writer at a time, subagents launched by the main
  session, no new worktrees. Preserve legacy worktrees and pending changes.
  Updated scheduling, worker boundaries and resource allocations; model/tool
  gates remain per-assignment requirements. These governance amendments share
  this one minor version; no additional bump is allocated for the merge.

## 0.3.3 - 2026-10-28

Integrated by the owner in `9d630e3`, matching [VERSION](VERSION).
Patch bump: source qualification and implementation-planning documentation only; no implemented
API/schema or application behavior change.

### Changed

- **FL-002 / FL-007:** Verified F-5's embedded Existing completion table with
  source/image hashes, exact MD/length/OD/ID and inert OLE-image provenance.
  Expanded the F-12 installed-tally search; recorded bounded coverage and the
  continued non-finding without claiming absence from the complete release.
- Distinguished F-11 B's actual installation narrative from its dimensioned
  drawing explicitly marked Plan; kept it a conditional reserve rather than
  silently replacing F-12 or merging sidetrack identities.
- Located dated perforation evidence for all three proposed pilots. Matched
  F-14's six initial and F-5's five 2008 intervals to the static table, explained
  F-5's three-versus-five snapshot difference, and recorded 2016 additions.
- Preserved F-12's conflicting 2014 interval summary/detail and clarified that
  physical perforation length, open/isolation state and interval flow differ.
  At that inspection checkpoint cohort/history/reference/rights acceptance remained open.
- Reconciled the owner's `a4bf9ee` integration as version 0.3.2; documentation
  integration alone did not approve the then-draft behavior or close G0/G1.
- **FL-002 / FL-007 / FL-014..017:** Recorded the owner's subsequent F-12/F-14/F-5
  selection, evidence-safe generic F-12 equipment, visible discrepancies, hybrid
  labels, explicit reconstruction/review/publication and upload-limit approval.
  Final G1/live/runtime gates remain separate.
- Added a source/draft/model data-quality issue specification and shared DTO/API
  contract, named real discrepancy fixtures and generic/unlocated negative tests.
  Expanded the global DAG to 32 tasks without dropping mandatory features.
- Added detailed foundation/project/upload implementation packets with 19 internal
  steps, planned paths/checks, isolated worktrees/resources, single-writer rules and
  stop/handoff conditions. No application workers or paid calls were launched.
- Reconciled instructions, backlog and acceptance traceability; clarified inert
  legacy-Word inspection versus forbidden macro execution for the F-5 source.

### Validation

- Original XML activity locators/timestamps, static interval correspondence,
  exact-decimal union lengths, device length arithmetic and source/image hashes
  checked; evidence retained in a new ignored audit sidecar without overwriting
  prior records. Selected scans inspected visually; no general OCR or Meta calls.
- Planning checks passed for 23 Markdown files/208 local links and headings,
  table/fence structure, 32-task and 18-item dependency graphs, 12 project
  acceptance rows, DQ-1..8/EQ-7 traceability, 19 first-packet steps and whitespace.
  Mandatory tasks reach release; optional Blender does not block it.
- Documentation-only change; no application tests or completed reconstruction
  are claimed.

## 0.3.2 - 2026-10-28

Integrated by the owner in `a4bf9ee`.
Patch bump: source evidence and revised planning/specifications only; no
implemented API/schema or application behavior change.

### Changed

- **FL-014 / FL-015 / FL-016:** Resumed planning on October 28 at the owner's
  request while leaving final data qualification and implementation approval open.
  Drafted project-scoped categorized uploads, separate source/model revisions,
  composite-asset reconstruction and minimal evidence/diff review/publication.
- Made the custom persistent Meta harness responsible for reconstruction as well
  as exploration; separated proposal, validation, accepted facts and tool permissions.
  Added early source conversation and independent reconstruction gold evaluation.
- Reworked delivery into UI-verifiable project/source/reconstruction/scene/enrichment
  checkpoints, with a 31-task dependency DAG and 12 project acceptance criteria.
  Preserved all required history, context and chart families.
- Proposed streaming limits that admit the inspected F-14 PDF and explicit
  qualification of required scanned/legacy-Word equipment evidence. Hybrid labels,
  limits and review-before-publication remain defaults awaiting owner approval;
  no confirmation is inferred from the unanswered clarification form.

- **FL-002 / FL-007:** Recorded acquisition of the pinned production workbook and
  1,759-report WITSML conversion, including 402 reports under the proposed pilot
  labels. Added byte/hash provenance and exact completion/perforation locators.
- Distinguished nominal equipment sizes from actual geometry, report dates from
  operation windows, missing converted unit/datum attributes and cross-well
  activity subjects. Complete installed geometry/history gates remain open.
- Recorded the repeated official missing-volume failure and documented shared
  volume read-privilege checks without changing access or assuming an upgrade.
- Reconciled the owner's `4ae7f7b` integration as version 0.3.1, then reopened
  **FL-014** for project-centric uploads, reconstruction-agent/harness ownership
  and UI-first verification. The previous architecture is explicitly provisional;
  those design changes have not yet been agreed or implemented.
- Recorded the owner's subsequent hard data gate: pause further design and
  application implementation until essential-data access/coverage is established,
  overriding the old plan's source-independent dispatch permission.
- **FL-002:** Acquired four pinned F-5 trajectory XML sections and their mapping;
  recorded unit/overlap/reference limits and an essential-data coverage table.
  Verified local copies now live under the existing Git-ignored data directory.
- Identified the official listing's 90-day installation policy and the May 27
  installation as an expiration hypothesis. Recorded the provider support route;
  no agent-performed reinstall or account change is claimed.
- **FL-002:** Inspected the owner's subsequent local official download: 33,678
  files, all 33 candidate paths, referenced ACTUAL surveys, depth horizons,
  production, logs and original operational evidence. Recorded that the earlier
  workspace failures no longer block local inspection.
- Found report/folder misattribution, undated pilot perforation-table rows and
  an embedded TIME horizon in the nominal seabed DEPTH file. Kept raw/interpreted
  curves, conflicting depth/position references and installed/design equipment
  separate. Seismic/OW archive acquisition is unnecessary for interpreted depth
  layers; this does not close G1 or authorize application implementation.
- Verified dimensional/MD evidence in F-14's AS INSTALLED completion schematic,
  including a safety valve, PBR and packer. Identified the specifically referenced
  29-01-2008 F-12 tally as not located in inspected sources, and distinguished
  F-5's genuine Word completion report from its mislabeled drilling PDF.

### Validation

- October 28 planning checks: 26 Markdown files, 188 local links/headings,
  table/fence structure, 31-task/six-goal acyclic DAG, 17 backlog items and all
  12 project acceptance criteria traced. Verified early UI/agent independence,
  optional Blender exclusion and explicit source/draft/model scopes. No runtime
  tests, live Meta calls or implementation approval are claimed.
- Acquired mirror bytes/hashes, row counts and selected source locators checked.
  Parquet inspection used temporary Python 3.12/PyArrow 26.0.0, not an application
  dependency change. No paid model calls, application tests or pilot acceptance.
- Local filesystem inventory, native structured-data checks and source hashes
  recorded in Git-ignored audit sidecars. Document-only review; the full 44.82 GiB
  was not content-validated and no app performance claim is made.

## 0.3.1 - 2026-10-27

Integrated by the owner in `4ae7f7b`.
Patch bump: architecture/specification and data-discovery documentation;
no implemented application API/schema change or completed pilot/live audit.

### Added

- **FL-002:** Public-source discovery report, official access/license handoff,
  expanded 33-file metadata-only pilot list and draft data-feasibility spec.
- **FL-002 / FL-007:** Equipment-source reassessment, three pinned WITSML probes
  with dimensions/locators/hashes, EDT/EDM and tubular/run priorities, and a
  proposed installed-assembly feasibility checkpoint distinct from generic/BHA geometry.
- **FL-014:** Complete modular-monolith architecture, selected stack/process model,
  revision/evidence/time/API contracts, feature specifications and requirement-to-test
  traceability based on inspected evidence.
- **FL-014:** A 24-task dependency-aware implementation plan with independent
  source-free slices, required real-data/live gates, agent/worktree/file ownership,
  two resource lanes, serialized integration and deadline/rehearsal checkpoints.

### Changed

- Recorded owner-confirmed indie track, public repository, three-minute demo,
  local/container runtime and ready Meta key/public-data processing permission.
- Corrected the earlier prepared-data assumption, refreshed Docker availability,
  and distinguished metadata findings from inspected engineering samples.
- Recorded successful account sign-in and the actual catalog visibility blocker:
  missing public schema/volume, not a missing account. No access-policy changes.
- Completed the bounded alternative-source search and documented another
  drilling/completion label mismatch, plus the distinction between provider
  inspection privileges and shared-volume read access.
- Reconciled FL-013 and version 0.3.0 against the owner's `88b177e` integration;
  Blender execution and agent-host activation remain unverified.
- Moved FL-014 from data-blocked design to documentation integration-pending;
  pilot access still blocks FL-002 and real-data acceptance, not all design work.
- Split existing feature IDs into bounded implementation increments without
  removing seabed/formations, production/log charts or historical perforations.
- Selected native PDF readers with conditional measured OCR, CPU local embeddings,
  strict generated API types, finite provider budgets and separate display/analytic
  projections. Runtime/model/package qualifications remain explicit future checks.

### Validation

- Official license/access documents and selected SODIR identities inspected;
  community metadata catalog checksum verified. No pilot files, account creation,
  paid Meta calls, cloud provisioning or application implementation.
- Three public mirrored WITSML files (7,776 bytes) passed fixed-revision/blob/hash,
  bounded XML and structural field checks across 8 components and 4 bore sections;
  these are not validated installation/datum claims.
- Initial static checks passed: 22 unique candidate paths matched catalog rows, unknown
  bytes/hashes remain blank, 86 local documentation links, 15 unique backlog IDs
  with acyclic dependencies, candidate version agreement and `git diff --check`.
  These do not satisfy the draft audit's content/numerical acceptance criteria.
- Equipment follow-up checks passed for 33 exact candidate paths, 95 local
  documentation links, 15 acyclic backlog items, DF-1 through DF-9, version
  agreement, sample hashes and `git diff --check`. Pilot acceptance remains blocked.
- Architecture-package checks passed: 185 local links, 24 unique acyclic tasks,
  six phase goals, 15 acyclic backlog parents, 10 new spec structures, 84 unique
  feature/data/history criteria and traceability for all 10 project ACs. All
  13 new design documents passed table/fence/whitespace checks; independent lanes,
  optional-asset exclusion, fixture arithmetic and EST deadline/version consistency
  were checked. These are documentation checks, not executed application tests.

## 0.3.0 - 2026-10-27

Offline Blender authoring skill integrated by owner on `master` in `88b177e`.
Minor bump for a newly invocable development skill; no application API/schema
change or operational Blender validation.

### Added

- **FL-013:** Original `fieldlens-blender-assets` skill for source-aware hard-surface
  equipment modeling, reviewed bpy scripts, materials/UVs, low-poly optimization,
  previews and validated GLB handoff.
- **FL-013:** Export checklist for units, axes, pivots, semantic IDs, permitted
  resources, format/round-trip checks and runtime budgets.

### Changed

- Existing 3D/motion agent and Three.js skill now route complex offline equipment
  authoring to Blender; simple wellbore geometry stays procedural.
- Workflow, technical baseline and curation guidance distinguish Blender's bundled
  Python from backend Python and reviewed offline scripts from prohibited runtime
  generated code. Agent count and model/effort defaults are unchanged.
- Reconciled the 0.2.0 configuration integration against `35ed5d2`; host activation
  remains unverified and is not inferred from that commit.
- Removed the broad `.github/` ignore rule at the owner's request so new shared
  skills remain visible to Git.

### Validation

- Static checks passed for the new skill header, 8 skills, 11 unchanged agent
  model tiers, 2 new routing cases, 158 local references, backlog/dependency/
  version consistency and Git visibility. `git diff --check` passed.
- Blender was not found on WSL PATH. Installation, assets, real export/render/
  browser tests and any new service are explicitly deferred by the owner.

## 0.2.0 - 2026-10-27

Development-agent configuration integrated by owner on `master` in `35ed5d2`.
This confirms repository configuration, not host activation or an application
release. Minor bump for new opt-in development-agent capability.

### Added

- **FL-001:** Main Astra/xhigh orchestrator profile and ten specialist profiles
  for small tasks, frontend, backend, 3D/motion, research, ingestion/OCR, RAG,
  geospatial/engineering, QA and bounded plan repair.
- **FL-001:** Owner-approved Terra/low, Sonnet/medium and Sol/high worker tiers;
  explicit routing, no silent model fallback, no nested worker delegation,
  minimal-context assignments and model/usage verification.
- **FL-001:** Agent registry, shared execution contract, activation guidance and
  approved configuration specification.

### Changed

- Execution guidance and feature handoffs now record role/risk rationale,
  actual model/effort evidence, bounded attempts and exposed usage. Development
  usage is distinct from the shared Meta application budget.
- Reconciled FL-000 and the 0.1.0 baseline against the owner's actual integration
  commit `e8b156a`; this does not retroactively claim an application release.

### Validation

- Static checks passed for 11 YAML profiles/model tiers/tool boundaries, 12 routing
  cases, 143 local references, backlog dependencies and version consistency.
  VS Code reported no agent-file diagnostics; `git diff --check` passed.
- Host profile/model activation remains untested and is a required check before
  real feature delegation; static checks do not prove runtime model selection.
- No application implementation, new worktrees, paid Meta calls or publication.

## 0.1.0 - 2026-10-27

Initial documentation baseline, integrated on `master` by `e8b156a`.
No application release or Git tag is asserted; earlier unversioned commits
remain listed below without invented historical versions.

### Added

- **FL-000:** Development workflow for main-agent planning/orchestration, isolated
  implementation worktrees, dependency-aware parallelism, verification/handoff,
  serialized integration and backlog reconciliation.
- **FL-000:** Persistent backlog, canonical version file, changelog policy, and
  feature-template fields for delegation, compatibility and integration evidence.
- **FL-000 / FL-008:** Historical perforation requirements and a draft feature
  contract for MD/TVD intervals, total/open perforated length, date-specific
  producing/injecting/shut-in states, reperforation, uncertainty and provenance.
  These are requirements, not implemented application capabilities.

### Changed

- **FL-000:** Project, technical, source and developer guidance now account for
  historical perforation state and selected-time/revision consistency.
- **FL-000:** Clarified that the deferred application-runtime multi-agent framework
  does not exclude the required multi-agent development workflow.

### Validation

- Checked 94 local Markdown/HTML references, backlog ID/dependency integrity,
  bootstrap version consistency, all seven synthetic state/length examples and
  ft/m round trips. Skill metadata matches the previously validated baseline;
  `git diff --check` passed.
  No application feature tests, worktree-agent execution, push, release or tag
  were performed by the documentation task. Integration was subsequently confirmed
  from Git history.

## Pre-versioning history

These entries describe existing commits, not historical numbered releases.

- **2026-10-27, `2772cff`:** Design/reference assets, curated development skills
  and supporting documentation.
- **2026-10-26, `695da46`:** Initial project structure, requirements and technical
  documentation.
