# Specification: Bounded Meta protocol and spending integration

> **Spec type:** API contract. **Backlog:** FL-003.
> **Load-bearing frameworks:** F2, F4, F5. **Supporting:** F1, F3, F6.
> **Date:** 2026-10-28. **Decision owner:** project owner.
> **Status:** Design complete; live entitlement/balance and spending approval unverified.
> **Amendment, October 30:** the adapter message model must represent image content parts and tool-call round trips (FL-022 page images and read-only content tools); the MI-5 tool-call bound (default 6) is configurable; MI-6 gains a harmless image-input check.
> **Zero-Question Score:** 0 unowned design questions; live calls remain opt-in.

## How to Read This Spec

Executor: section 4. QA: MI tests and failure paths. Owner: budget and live gate.
Implements project AC-7/10 and G2, independently of the pilot data download.

## Notation Key

`[Validated]`: owner/project requirement. `[Assumed: verify]`: proposed budget or
protocol choice requiring approval. H/M/L are confidence. AC score 3 = binary.

## 1. Outcome Statement

An application request either uses the verified Meta protocol within a reserved
shared budget or returns an explicit safe failure with accounted usage.
Verification: MI-1 through MI-6. Outcome score 3.

## 2. Scope

### IN Scope

Offline provider adapter tests, entitlement smoke procedure, budget reservation,
retry/deadline/cancellation behavior and sanitized usage. `[Validated: project]`

### OUT of Scope

Retrieval/exploration tool selection/UI (FL-011), reconstruction policy/UI (FL-016),
paid bulk extraction, provider subscriptions,
Contributor mode, non-Meta fallback and new runtime agent frameworks.

### Scope Dependencies

MI offline adapter can be specified/tested with frozen contracts; persistent
budget integration requires FL-004-A. Live check also requires owner-approved
allowance, confirmed balance and locally available credentials. It needs no G1 data.

### Open Scope Tensions

A key's existence is not a known balance or entitlement. Live execution is blocked
until those facts are recorded; do not guess that USD 150 remains unspent.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| MI-1 | Behavioral | Adapter handles text, typed tool call/result IDs, refusal, truncation and opaque reasoning replay using fixture Responses payloads. | 3 | [Assumed: verify protocol] | `test_meta_protocol` |
| MI-2 | Negative | All default tests make zero external requests; missing key/balance/pricing produces explicit unavailability before dispatch. | 3 | [Validated] | `test_paid_calls_disabled` |
| MI-3 | Behavioral | Concurrent reservation attempts against one PostgreSQL ledger cannot exceed the configured remaining cap; reservations survive restart. | 3 | [Validated] | `test_budget_reservations` |
| MI-4 | Edge case | Timeout after dispatch retains estimated liability until reconciliation; 429/5xx retry at most once within the request/cost deadline; 401/403, refusal and bad schema are not retried automatically. | 3 | [Validated] | `test_provider_failure_accounting` |
| MI-5 | Non-behavioral | A request permits <=4 provider attempts including retry, <=6 tool calls, <=90 seconds total, <=4,096 output tokens/attempt and <=USD 0.50 reserved cost; cancellation prevents subsequent calls. | 3 | [Assumed: verify limits] | `test_agent_limits` |
| MI-6 | Dependency | Opt-in smoke records actual model/protocol, text response, one harmless tool round trip, cancellation/error result and usage within USD 1 total, with no field documents or secrets in evidence. | 3 | [Assumed: verify live allowance] | `test_meta_live_smoke` |

MI-6 is live and cannot pass using a mock. MI-1 through MI-5 are an independently
verifiable offline slice. Full FL-003 requires all criteria and G2 approval.

## 4. Context and Decisions

Executor: `fieldlens-rag`; owned planned module `backend/fieldlens/assistant/provider.py`,
budget repository/migration coordinated with backend, and
`backend/tests/assistant/test_meta_*.py`. Use the Python `openai` SDK, base URL
`https://api.meta.ai/v1`, Responses and `muse-spark-1.3` Standard as the selected
test candidate. If entitlement or required protocol semantics differ, report the
actual supported option for an amendment; do not silently switch provider/mode.

This adapter is shared by reconstruction and exploration. The application harness,
not the SDK, owns persisted run state, bounded evidence-dependent tool selection,
validation, review gates, cancellation and recovery. FL-016 adds proposal tools;
FL-011 exposes read/navigation tools. Neither mode can bypass the same global
ledger. MI-5 bounds one work unit, not an entire project corpus; explicit continued
work needs a new reservation. Upload and local extraction never implicitly start
paid model work.

Budget is global across worktrees and requests, not USD 150 per process.
Persist `budget_period`, ledger cap, known starting balance/time/source, usage,
reservations, request IDs, pricing revision and reconciliation status.
Use decimal currency and a transactional row lock before allocating liability.
Only the owner updates the externally confirmed starting balance.

Proposed controls: warn at USD 100 consumed; block unattended experiments at
USD 120; reserve the final USD 30 for explicitly authorized evaluation/demo.
Hard cap is the lower of the project USD 150 allowance and confirmed available
provider credit, less spending and outstanding liabilities. If external spending
makes the balance stale/unknown, pause paid work until owner reconciliation.

Compute an upper bound from actual bounded payload sizes, output allowance,
number of attempts and enabled paid tools before dispatch. If tokenization/billed
reasoning limits cannot be bounded, fail preflight rather than rely on an average
cost. A USD 0.50 reservation is a ceiling, not permission to exceed that estimate.
Count provider-side web queries separately; application catalog enrichment is
disabled until its allowance/authorization exists. No paid search in smoke tests.

SDK auto-retry is disabled; the application owns the single retry and Retry-After
handling. An attempt that may have reached the provider remains chargeable even
if no response arrived. Reconcile known usage; release only demonstrably unused
reservation. No automatic restart replay of interrupted paid calls.

Record model, attempt/tool counts, input/cached/output tokens when exposed,
elapsed time, estimated/billed amount and errors. Missing provider fields remain
unavailable, not zero. Keep keys, source text, prompts and opaque reasoning out of
ordinary logs. Stateless handling is preferred where the verified protocol permits.

## 5. Failure Conditions

Entitlement/401/403 -> stop live slice and report sanitized status; no upgrade.
Unbounded billing or malformed tool response -> stop the request, retain liability
and return a typed failure; never describe an incomplete answer as successful.
Worst misinterpretation: an estimated cheap request is not safe without an atomic
reservation and bounded retries; MI-3/4 enforce both.

## 6. Ambiguity Audit

The four-attempt limit includes retry. Budget mode never changes automatically.
Actual entitlement/balance are G2 facts, owned by owner/RAG executor before MI-6.
Offline success cannot close the live gate.

## 7. Implementation Guidance

Split FL-003-A (MI-1..5) from FL-003-B (MI-6). Planned commands:
`uv run pytest backend/tests/assistant -m "not live_meta"` and explicitly
`uv run pytest backend/tests/assistant -m live_meta` only after authorization.
Use harmless synthetic inputs for live smoke; persist a sanitized protocol result.
MI-6 ran live on October 31 (see evidence file); MI-1..5 remain offline. Implementation proposes minor;
the main agent assigns final version and records live/stub evidence.

## Open Tensions

Live verification must happen before final acceptance, but ordinary coding/tests
must remain zero-cost. Separate commands, fixtures and ledger gates enforce this.

## Offline Implementation Traceability (TASK-004, October 30)

Code: `backend/fieldlens/assistant/` (`messages`, `provider`, `stub`, `meta`, `budget`,
`tables`, `runner`, `errors`); migration `0004_provider_budget`. Tests live in
`backend/tests/assistant/`. No live call was made; MI-6 stays open.

| ID | Offline evidence | Residual (live/unverified) |
|---|---|---|
| MI-1 | `test_meta_protocol.py`: payload build/parse of fixture Responses payloads (text, tool call/result IDs, refusal, truncation, opaque reasoning replay, image parts, web-search counting) | Real protocol shape and reasoning-replay entitlement (MI-6) |
| MI-2 | `test_paid_calls_disabled.py`: socket guard, missing key/balance/pricing fail before dispatch, client never used, SDK retries disabled, secrets absent from logs/errors/DB rows/recordings | Nothing live |
| MI-3 | `test_budget_reservations.py`: 12-thread race, idempotent keys, ceiling = min(cap, balance), restart survival, DB cap constraint | Owner-confirmed real balance |
| MI-4 | `test_provider_failure_accounting.py`: timeout keeps liability until reconcile, one 429/5xx retry, no retry for 401/403/refusal/bad schema, usage-less answers stay estimated | Real billing of a timed-out call |
| MI-5 | `test_agent_limits.py`: attempts incl. retry, tool-call bound (default 6, configurable), deadline, output-token bound, reserved-cost bound, cancellation | Limits remain `[Assumed: verify]` |

Amendment items: image content parts and tool-call/result round trips are in the message model
and handled by the stub, replay and Responses payload builder; MI-5 tool-call bound is
`FIELDLENS_PROVIDER_MAX_TOOL_CALLS`. Token bounds are conservative estimates (1 token per UTF-8
byte; `provider_image_token_bound` per image) until MI-6 compares them with provider usage.

## Assumption Registry

MI-6 live results (October 31, `docs/evidence/MI6_LIVE_SMOKE.md`): `muse-spark-1.3` Responses
text, tool round trip with opaque reasoning replay and image input are entitled and work
(Validated, live). No embeddings endpoint exists for this key (404; local embeddings stand).
Corrections: default reasoning effort is `high` and consumes output tokens; the 1-token-per-byte
input bound underestimates tool requests (about 2.3x); in-flight cancel does not stop billing;
HTTP 4xx rejections (404 unknown model, 404 embeddings) were not billed. Provider rates are still
unknown (spend estimated at placeholder rates; owner must reconcile the balance).

TASK-043 adapter hardening (offline-tested; stub/fixture payloads, not live proof):
- Effort: `ProviderRequest.effort` (`minimal|low|medium|high`, default unset = provider default
  `high`) is sent as `reasoning.effort`. `WorkUnit(effort=...)`, `RequestLimits.default_effort`
  and `step(..., effort=...)` choose it per unit/call site (call > unit > limits). An unset effort
  is excluded from the request fingerprint, so older recordings still match; the recorder stores
  the requested effort and stub/replay `calls` expose it. The API accepted `low` and `minimal`.
- Input bound: bytes-as-tokens plus 512 tokens when any tool is sent, 128 per tool definition,
  128 per tool call/result item and 256 per replayed reasoning item (plus its bytes). Chosen
  above the MI-6 figures (one-tool request billed 552, follow-up step 992; old estimate 245).
  Image bound unchanged. Still an estimate from one model's one data point.
- Cancel: the synchronous SDK call is not aborted in flight. A cancel during a call lets it
  complete and bill; the unit records the actual usage (reservation `settled`, not `liable`)
  and then raises `RequestCancelled(settled=True)`. Cancel stops later calls, not billing of the
  call in flight. If usage is missing the attempt stays estimated liability.
- Rejected 4xx (not 408/409, not 429/401/403 which were already handled) map to
  `ProviderRejected` (non-chargeable): the reservation settles at 0 instead of `liable`. The
  `released` state stays for never-dispatched reservations (table constraint); no migration.
  5xx, timeouts, connection errors, 408/409 and unknown outcomes remain `liable`.
- Reconcile: `BudgetLedger.list_liable`, `release_liable(id, reason)` (settle at 0) and
  `reconcile(id, total, reason=...)` (settle at the confirmed total); the reason slug is appended
  to the unresolved attempts' error code. State is in PostgreSQL and survives restarts.
- Pricing stays data: `load_pricing(path)` builds a `Pricing` from a JSON rate card to register
  as a new revision; no rates are in code.
Published rates bound the chosen mode (M; unresolved: no rate source). USD 150 is the original
allowance, not current balance (H; owner must supply current credit).

## Adversarial Self-Critique

SDK retries can double-count attempts: disable and test them.
Timeout may still incur charges: retain liability.
An existing key can conceal unavailable model access: do not infer MI-6.

## Revision Triggers

Reopen on model/protocol retirement, billing/pricing changes, or unexplained
provider balance differences before another paid request.
