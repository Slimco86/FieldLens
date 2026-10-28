# Specification: Bounded Meta protocol and spending integration

> **Spec type:** API contract. **Backlog:** FL-003.
> **Load-bearing frameworks:** F2, F4, F5. **Supporting:** F1, F3, F6.
> **Date:** 2026-10-28. **Decision owner:** project owner.
> **Status:** Design complete; live entitlement/balance and spending approval unverified.
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
No calls/tests have run for this specification. Implementation proposes minor;
the main agent assigns final version and records live/stub evidence.

## Open Tensions

Live verification must happen before final acceptance, but ordinary coding/tests
must remain zero-cost. Separate commands, fixtures and ledger gates enforce this.

## Assumption Registry

Responses tool replay is entitled (M; MI-6 validates). Published rates bound the
chosen mode (M; pricing/usage reconciliation validates). USD 150 is the original
allowance, not current balance (H; owner must supply current credit).

## Adversarial Self-Critique

SDK retries can double-count attempts: disable and test them.
Timeout may still incur charges: retain liability.
An existing key can conceal unavailable model access: do not infer MI-6.

## Revision Triggers

Reopen on model/protocol retirement, billing/pricing changes, or unexplained
provider balance differences before another paid request.
