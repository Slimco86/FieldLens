# Specification: Progress notifications and backlog-to-Taiga synchronization

> **Spec type:** Product/feature (developer tooling).
> **Load-bearing frameworks:** outcome, acceptance, scope. **Supporting:** failure conditions.
> **Date:** 2026-10-29. **Author:** orchestrator. **Decision owner:** project owner.
> **Status:** Approved by owner October 29 (go; due-date policy OK; Taiga project stays public with `TAIGA_ALLOW_PUBLIC=1`; notifications only, no inbox yet).
> **Backlog ID:** FL-020 (slices A notify, B backlog format/check, C Taiga sync). **Delivery state:** specifying.
> **Approved spec revision/date:** October 29. **Integration version:** pending.
> **Zero-Question Score:** 0 unowned questions; owner-visible defaults in section 6.

## How to Read This Spec

Owner: outcome, scope, privacy. Implementer: contracts and ACs per slice. Tester: ACs and
failures. The workflow stays defined by [DEVELOPMENT_WORKFLOW](../DEVELOPMENT_WORKFLOW.md);
this spec only adds a mirror and a notification channel.

## Notation Key

`[Validated]` = owner confirmed; `[Assumed: verify]` = proposed default. AC score 3 = binary.

## 1. Outcome Statement

After this increment (a) the orchestrator and owner can send/receive short progress
messages through one Telegram chat with one command; (b) `docs/BACKLOG.md` is a
machine-checkable ledger whose every feature and task carries status, priority, tags,
dependencies, assignee, due date and sprint; (c) one command mirrors that ledger into the
owner's Taiga project (sprint `Hackathon`) as user stories (features) and tasks, idempotently.
`docs/BACKLOG.md` remains the single source of truth; Taiga is a read-mostly view.
Verification: `track.py check` passes on the converted backlog; a Taiga dry-run lists
53 items (21 features, 32 tasks); `--apply` twice produces zero changes the second time; `notify.py
--dry-run` prints the message that would be sent. Outcome score: 3.

## 2. Scope

### IN Scope

- **A. `scripts/notify.py`**: send-only Telegram notifications (stdlib `urllib`), an event
  vocabulary, redaction, de-duplication, dry-run. Optional **inbox** (owner commands) is
  included but disabled unless `TELEGRAM_INBOX=1`.
- **B. Backlog ledger format** (section 4), conversion of the existing 21 feature rows (FL-000..FL-020) and 32
  plan tasks into it (history text preserved under a Journal heading), and
  `scripts/track.py check|plan`: parse, validate, dependency/cycle/date checks, diff.
- **C. Taiga sync** (`scripts/track.py sync [--apply]`) over the Taiga REST API, with drift
  report, sprint assignment and optional Telegram summary.
- Orchestrator duty: notify at the events in 4.5 (agent profile and workflow doc updated by
  the orchestrator, not by workers).
- Tool-specific env loader that reads only `TELEGRAM_*`/`TAIGA_*` keys (does **not** widen
  `fieldlens.localenv.ALLOWED_PREFIXES`; provider credentials still never enter any process).

### OUT of Scope

- Two-way sync of tickets/status from Taiga into the repo; Taiga webhooks; epics (project has
  them disabled); story points; attachments/comments; any application/runtime behavior.
- Acting on free-text Telegram messages. Only the fixed command set in 4.4 is recognized,
  and only from the configured chat.
- Self-hosting a tracker.

### Scope Dependencies

None on application features. Taiga project `slimco86-test` (id 1812809, scrum enabled,
epics disabled, sprint `Hackathon` 2026-10-29..2026-11-04, single member `slimco86`, role
Product Owner) `[probed October 29]`. Telegram bot and chat id in the untracked `.env`.

### Open Scope Tensions

1. **The Taiga project is public** (owner accepted October 29; set `TAIGA_ALLOW_PUBLIC=1`) (`is_private=false` on October 29). Anyone with the URL can
   read titles and descriptions. Resolution: `track.py` refuses to sync to a non-private
   project unless `TAIGA_ALLOW_PUBLIC=1`; the owner decides whether to make it private (Taiga
   settings) or to accept publication of backlog text. Owner: project owner, before slice C
   `--apply`.
2. **The Telegram bot may be shared** with another group/use (the bot has received supergroup
   traffic). Polling `getUpdates` would consume another consumer's updates. Resolution: inbox
   is off by default; recommend a dedicated FieldLens bot before enabling it.

## 3. Acceptance Criteria

| ID | Type | Given / when / then | Score | Annotation | Test |
|---|---|---|---|---|---|
| NT-1 | Behavioral | `notify.py --event qa_pass --ref TASK-006 "text"` sends one message to the configured chat via `sendMessage` (10 s timeout, 2 attempts with backoff), prints `sent` and exits 0; exits 2 on failure unless `--best-effort` (then 0 with a warning). | 3 | [Validated] | `test_send_success_and_failure` (local fake HTTP server) |
| NT-2 | Negative | Bot token, chat id, Taiga credentials and any `.env` value never appear in stdout, stderr, exception text, logs or the saved state; URLs in errors are redacted; messages containing a configured secret value or a secret-like pattern are refused. | 3 | [Validated] | `test_no_secret_leak` |
| NT-3 | Behavioral | `--dry-run` (or `NOTIFY_DRY_RUN=1`) performs no network call and prints the exact text; missing configuration yields a one-line actionable error (names keys, not values). | 3 | [Validated] | `test_dry_run_and_missing_config` |
| NT-6 | Behavioral | Every message starts with a fixed icon + label so status updates and action-required messages are visually distinct: action required `🔴 ACTION NEEDED` (events `decision_needed`, `blocked`, `qa_fail`, and `--action`), status `🟢`/`🔵`/`⚪` (`started`/`qa_pass`/`merged`/`released` green; `progress`/`handoff`/`repair`/`info` blue/white). Action messages put the requested decision at the start of the text line directly under the header. | 3 | [Validated: owner October 29] | `test_icons_and_action_marker` |
| NT-4 | Edge case | Identical event+ref+text within 60 s is suppressed once (state in `.local/run/notify.json`); text is single-purpose, max 1000 chars (truncated with an ellipsis), control characters stripped, only the event vocabulary in 4.5 accepted. | 3 | [Validated] | `test_dedupe_limits_vocabulary` |
| NT-5 | Behavioral | `notify.py inbox --once` (requires `TELEGRAM_INBOX=1`) reads new updates only from `TELEGRAM_CHAT_ID`, persists the update offset, appends accepted commands to `.local/run/inbox.jsonl`, replies once per command, and never replies to or stores other chats' messages (Telegram's offset acknowledges them collectively, which is why a dedicated bot is recommended). `/cmd@botname` forms and notes containing secret-like patterns are handled per NT-2 (notes with secrets rejected). Free text is stored as `note` data, never executed. | 3 | [Assumed: verify] | `test_inbox_filters_chat_and_commands` |
| BK-1 | Behavioral | `track.py check` parses `docs/BACKLOG.md`: every feature/task has all required fields; statuses, priorities, dates and IDs are valid; dependencies reference existing items; no dependency cycle; tasks reference a feature; `done` items have `Version` and evidence; due dates lie within the sprint/deadline; exits non-zero listing every violation with line numbers. | 3 | [Validated] | `test_check_rules` |
| BK-2 | Behavioral | Conversion preserved every pre-existing item: 21 features (FL-000..FL-020) and 32 tasks (TASK-001..032) with their prior status/evidence, the narrative history is kept verbatim under `## Journal`, and relative links still resolve. | 3 | [Validated] | `test_conversion_inventory` (counts and ID set) + link check |
| BK-3 | Negative | The parser accepts only the documented field names/values; unknown fields, duplicate IDs, and malformed tables fail `check` rather than being ignored. | 3 | [Validated] | `test_parser_strict` |
| TG-1 | Behavioral | `track.py plan` (no network write) prints per-item create/update/no-op for features -> user stories and tasks -> tasks with the exact changed fields; `sync` without `--apply` is identical. | 3 | [Validated] | `test_plan_diff` (fake Taiga API) |
| TG-2 | Behavioral | `sync --apply` creates/updates user stories and tasks in the project named by `TAIGA_PROJECT_SLUG` with: subject `[ID] title`, description (outcome, next action, evidence, dependency list, spec path), tags, status mapped per 4.2, due date, assigned user, `is_blocked`/`blocked_note` from unmet dependencies, milestone `Hackathon`; tasks belong to their feature's story. | 3 | [Validated] | `test_apply_mapping` |
| TG-3 | Edge case | Idempotency: a second `--apply` makes no write calls; items are matched by the `[ID]` subject prefix (state file only caches Taiga ids/versions), duplicates in Taiga abort; deleted tracker items are re-created, extra tracker items without prefix are left untouched and reported. | 3 | [Validated] | `test_idempotent_apply` |
| TG-4 | Edge case | Tracker edits to managed fields since the last push are reported as drift and overwritten (repo is truth); `--keep-drift` skips them. 429/5xx are retried with `Retry-After`/backoff (max 4 tries); a mid-run failure leaves a consistent partial state that the next run completes. | 3 | [Validated] | `test_drift_and_retry` |
| TG-5 | Negative | Sync refuses a non-private project unless `TAIGA_ALLOW_PUBLIC=1`; refuses to send descriptions containing secret-like patterns; sends only text from the backlog (no file contents, no `.env` values); the token is held in memory only and never logged. | 3 | [Validated] | `test_privacy_guards` |
| TG-6 | Behavioral | `sync --apply --notify` sends one Telegram summary (counts and changed IDs) via the notify module. | 3 | [Validated] | `test_sync_notify` |
| TG-7 | Verification | One real run against `slimco86-test`: dry-run, `--apply`, second `--apply` (zero writes), manual spot-check of 5 items in the Taiga UI by QA via the API. | 3 | [Validated] | recorded in handoff |

Definition of done: DV-style evidence in the handoff — actual commands/results, fakes versus
live results labelled; secrets never printed.

## 4. Context and Decisions

### 4.1 Backlog ledger format

`docs/BACKLOG.md` is restructured:

```
# FieldLens backlog
<short preamble, legend of states/priorities/tags, how to edit, link to this spec>
## Features        (one block per FL-xxx)
## Tasks           (one block per TASK-xxx)
## Journal         (all existing narrative/history text, verbatim)
```

Every item block:

```
### FL-005 · Upload project sources into traceable, persistent, restart-safe source revisions

| Field | Value |
|---|---|
| Type | feature            (feature | task)
| Status | in_progress      (proposed|specifying|ready|in_progress|testing|integration_pending|done|blocked|cancelled)
| Priority | P0             (P0 | P1 | P2 | optional)
| Tags | ingestion, backend, frontend
| Depends on | FL-004, FL-002   (IDs or `none`)
| Assignee | agent:fieldlens-backend   (owner | agent:<profile> | unassigned)
| Due | 2026-11-01          (YYYY-MM-DD; done items: completion date)
| Sprint | Hackathon
| Parent | FL-005             (tasks only; slice A/B in `Slice`)
| Slice | FL-005-A          (tasks only)
| Spec | specs/INGESTION.md
| Version | 0.8.0            (required when done)

**Outcome.** one paragraph.
**Next action.** one paragraph.
**Evidence.** commits/versions/tests, or `none yet`.
```

Rules: field names exactly as above; one value per row; `Depends on` for tasks follows the
plan DAG; free text blocks use only the three bold labels; history stays out of items.

### 4.2 Taiga mapping `[probed October 29]`

| Backlog | Taiga user story (FL) | Taiga task (TASK) |
|---|---|---|
| proposed, specifying | New | New |
| ready | Ready | New |
| in_progress | In progress | In progress |
| testing, integration_pending | Ready for test | Ready for test |
| done | Done | Closed |
| blocked | New + `is_blocked`, note | New + `is_blocked`, note |
| cancelled | Archived | Closed + tag `cancelled` |

- **Blockers:** `is_blocked=true` with `blocked_note = "Waiting for FL-004 (in_progress), ..."`
  whenever the item is not done/cancelled and at least one dependency is not `done`
  `[Validated: owner asked for blockers/dependencies]`. The dependency list is also written
  into the description with Taiga `#ref` links after refs are known (second pass).
- **Assignee:** `owner` -> `slimco86`; `agent:*` and `unassigned` -> no Taiga assignee;
  agent profile appears as tag `agent-<profile>`. Only one human member exists today.
- **Sprint:** milestone looked up by name (`Hackathon`); tasks use their story's milestone.
- **Due date:** `due_date` on stories and tasks.
- **Tags:** backlog tags plus lower-case priority (`p0`) and `agent-<profile>`.
- **Order/points/epics:** not managed.

### 4.3 Environment keys (untracked `.env`, documented in `.env.example` as empty keys)

`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, optional `TELEGRAM_INBOX`; `TAIGA_USERNAME`,
`TAIGA_PASSWORD`, optional `TAIGA_PROJECT_SLUG` (default `slimco86-test`),
`TAIGA_URL` (default `https://api.taiga.io`), `TAIGA_ALLOW_PUBLIC`. Parsed with dotenv
semantics (a ` #` after an unquoted value starts a comment: **put no comment after a secret**).
Linked worktrees resolve the file from the main checkout. `init_env.py` appends the keys
as empty lines when absent and never prints values.

### 4.4 Inbox commands (disabled by default)

`/status`, `/pause`, `/resume`, `/approve <ID>`, `/reject <ID>`, `/note <text>`. Stored in
`.local/run/inbox.jsonl`; the orchestrator reads the file at turn start and decides. No
command executes anything by itself.

### 4.5 Event vocabulary and orchestrator duty

`started`, `progress`, `handoff`, `qa_pass`, `qa_fail`, `repair`, `blocked`,
`decision_needed`, `merged`, `released`, `cleanup`, `info`. The orchestrator sends at: feature/
slice start, handoff to QA, each QA verdict, repair start, merge/release with version,
a blocker or required owner decision, and cleanup/session wrap-up — one message per
transition (action-required events carry the 🔴 ACTION NEEDED marker per NT-6) (not per tool call), IDs and short titles only, never document contents or secrets.

### 4.6 Delegation

`fieldlens-backend`, serial feature branches from the then-current `master`, one writer,
separate `fieldlens-qa` per slice: `feature/fl-020-a-notify`, `feature/fl-020-b-ledger`,
`feature/fl-020-c-taiga-sync`. Owned paths per slice: A `scripts/notify.py`,
`scripts/toolenv.py`, `backend/tests/tooling/test_notify*.py`, `.env.example`, `init_env.py`
(key list only); B `scripts/track.py` (parse/check/plan), `docs/BACKLOG.md` conversion,
tests; C `scripts/taiga_client.py`, `scripts/track.py` (sync), tests. Shared release files stay
with the orchestrator. No new Python dependency (stdlib `urllib`). Default tests make no
network call except loopback fakes.

## 5. Failure Conditions

- Telegram/Taiga unreachable or rate-limited: tools fail closed with a short message; the
  orchestrator uses `--best-effort` so tooling never blocks delivery, but records the miss.
- Partial sync: items already written stay valid; next run converges; nothing is deleted
  in Taiga by the tool.
- Backlog parse error: `sync` aborts before any network call.
- Worst misinterpretation: a green dry-run that does not reflect what Taiga contains. TG-3/TG-7
  require comparing against the live API state, not only the local snapshot.

## 6. Ambiguity Audit

Defaults (owner may override): features -> user stories, tasks -> tasks (no epics); due dates
proposed from priority/phase (P0 first UI Oct 31, early agent risk Nov 1, reconstruction
Nov 2, enrichment Nov 3, acceptance/release Nov 4; done items use their integration date);
one-way sync; blockers derived from unmet dependencies; inbox off; sprint is `Hackathon`.

## 7. Implementation Guidance

Notify and Taiga clients are thin `urllib` wrappers behind an injectable transport so tests use
fakes and a loopback fake server. Parse the ledger with a small strict state machine
(heading regex `^### ((?:FL|TASK)-\d{3}) · (.+)$`, 2-column field table, three bold labels).
Checkpoints: A merged first (orchestrator uses it immediately), then B, then C.

### Implementation handoff and integration

| Field | Record before handoff / after integration |
|---|---|
| Feature commits / tested HEAD | pending (per slice) |
| Verification | pending |
| Compatibility assessment | New features (minor per slice); BACKLOG layout change documented |
| Proposed changelog entry | FL-020-A/B/C |
| Related documentation | README tooling section, `.env.example`, workflow doc (orchestrator) |
| Integrated commit / final version | pending |

## Open Tensions

See 2: public Taiga project and shared bot.

## Assumption Registry

Taiga REST shape (`/auth`, `/userstories`, `/tasks`, `/milestones`; `is_blocked`, `due_date`
fields) `[probed October 29, M]`; Taiga cloud free-plan rate limits unknown (M); Telegram
`getUpdates` semantics (H). Invalidated by Taiga API changes or a self-hosted instance.

## Adversarial Self-Critique

The sync could silently drop dependencies if blockers are only flags (descriptions carry the
list); overwrite semantics could erase owner edits in Taiga (drift is reported and
documented); a pasted password with an inline comment already broke login once (NT-2/4.3
documentation and a dotenv-semantics test); a public project could leak backlog text (TG-5).

## Revision Triggers

Owner wants two-way sync or epics; Taiga plan limits; moving to a self-hosted tracker;
new messenger.
