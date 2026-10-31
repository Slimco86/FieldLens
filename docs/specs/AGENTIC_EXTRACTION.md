# Specification: Agent-assisted extraction of ambiguous source content with deterministic validation

> **Spec type:** Product/feature + Agent task.
> **Load-bearing frameworks:** outcome, acceptance, scope, context. **Supporting:** failure conditions, ambiguity audit.
> **Date:** 2026-10-30. **Author:** orchestrator (draft). **Decision owner:** project owner.
> **Status:** Approved by the owner on 2026-10-30 (section 6 records the decisions); implementation not started.
> **Backlog ID:** FL-022 (TASK-035 approval, TASK-036 extraction, TASK-038 activity log, TASK-040 Reconstruction view). **Delivery state:** in progress (TASK-038 dispatched October 31).
> **Approved spec revision/date:** r1, 2026-10-30. **Integration version:** pending.
> **Zero-Question Score:** 0 blocking. Non-blocking: multimodal entitlement is verified by the TASK-005 live smoke, and TASK-036 uses the stub until then.

> **Owner amendment, October 31:** the priority extraction target is production/completion equipment
> (tubing, casings/liners in service, packers, pumps, bearings) from the completion documents; drilling-side
> assemblies are out of scope. TASK-042 (live feasibility spike) and TASK-041 (extraction) follow the TASK-005
> live smoke; their acceptance criteria are added after the spike. The harness contract (AX-1..11) is unchanged.

> **Owner amendment, October 31 (demo, second pass):** OCR is dropped. For scanned completion pages the model reads
> page images directly and proposes a superficial, visual-level equipment structure; values are labelled model-read
> and unverified, are never used in calculations, and the AX-2 quote-in-span check applies only where a text layer
> exists. Speed and performance take priority over detail; missed details are acceptable. See DATA_COMPLETENESS.

## How to Read This Spec

Owner: outcome, scope, acceptance policy and spend (section 6). Implementer: scope, contract and ACs.
QA: negative/adversarial ACs and the worst-misinterpretation test. Builds on [ingestion](INGESTION.md)
(deterministic profiles come first), [Meta integration](META_INTEGRATION.md) (provider adapter, budget, MI-1..5),
[reconstruction](ASSET_RECONSTRUCTION.md) (consumes the result), [data quality](DATA_QUALITY.md) (surfaces it).

## Notation Key

`[Validated]` = owner/source confirmed; `[Assumed: verify]` = proposed, owner approves in TASK-035.
AC score 3 = binary and outsider-testable.

## 1. Outcome Statement

After this increment, whenever answering a specific question about an entity, measurement, fact or record needs
broader document context or multimodal input than a deterministic profile provides (an ambiguous table, free-text
report paragraph, unlabeled units, unclear well/wellbore subject, or scanned/legacy-Word content), the application
harness can ask the model for typed candidate claims. The model may read the source through allowlisted read-only
content tools (spans, tables, page images by locator, project retrieval). Every candidate carries its exact source
locator, is checked by deterministic validators, and ends as `accepted`, `rejected` or `flagged` with a visible
reason. Each work unit leaves a project-scoped activity log (steps, tool calls, candidates, validator outcomes,
usage) that the Reconstruction tab displays. Model output never becomes an accepted fact because the model said so,
never overrides a deterministically parsed value, and never runs without budget.
Verification: AX-1 through AX-11 with the offline stub provider on fixtures; live behavior is a separate gate.
Outcome score: 3.

## 2. Scope

### IN Scope

- `[Validated: owner, October 30]` Extraction should be as deterministic as possible; model judgement is for the
  ambiguities that deterministic parsing cannot resolve.
- `[Validated: owner, October 30]` Question-driven use: the model is invoked for a specific question about an
  entity, measurement, fact or record when broader document context or multimodal input is needed.
- `[Validated: owner, October 30]` Ambiguity classes: (a) table column/header/unit interpretation; (b) free-text
  statements of events, dates, depths and equipment attributes; (c) subject identity (which well/wellbore a passage
  is about); (d) text/images produced by approved scanned-PDF and legacy-Word profiles (TASK-030 locators).
- `[Validated: owner, October 30]` Read-only content tools for the model: read a text span, read a table, fetch a
  page image by locator, and search the project (TASK-011 retrieval). Page images enable multimodal questions.
  Tools are allowlisted, project-scoped, argument-validated and return only source content with locators.
- `[Assumed: verify, H]` A persisted, project-scoped agent activity log per work unit: question, steps, tool calls
  with argument/result summaries, candidates and validator outcomes, usage and stop reason. No hidden reasoning is
  stored. Shown in the Reconstruction tab (TASK-040; persistence in TASK-038).
- `[Assumed: verify, H]` A typed candidate-claim schema (value, unit as written, subject candidate, effective-time
  text with precision, evidence locator(s), extraction method `model_proposal`, prompt/model/version ids) reusing the
  existing evidence/locator/quantity contracts; persisted candidate states and reasons.
- `[Assumed: verify, H]` Deterministic validators: locator exists and the quoted text matches the source span; value
  and unit parse; unit/dimension and range plausibility; subject is a known project identity candidate (otherwise
  stays a candidate); date precision preserved; no conflict with a parsed value (a conflict is `flagged`, never
  resolved by the model). Validators are code, never a second model call.
- Display of candidates/states/reasons in the evidence and issue views (shared shell, FL-021).
- Offline stub provider tests; usage/budget recording through the existing adapter.

### OUT of Scope

- Reconstruction (relationships, entity merging, publication): FL-016 consumes accepted/flagged candidates.
- Retrieval/chat (FL-011) and equipment catalog research (FL-007).
- Replacing native parsers; model code/SQL/shell execution; any tool beyond the read-only content allowlist;
  autonomous web access (web research stays with equipment research, FL-007).
- Manual fact editor or review-based acceptance of model facts (a reviewer UI is deferred; flagged items stay flagged).
- Live provider spend: not authorized by this spec (see section 6, question 5).
- Contributor mode and any non-Standard provider mode (project rule).

### Scope Dependencies

TASK-004 (offline provider adapter and budget reservations), TASK-009 (native profiles producing the
deterministic records and the ambiguity signal) and TASK-011 (retrieval for the search tool) are hard prerequisites;
TASK-030 supplies scanned/Word text for class (d). Missing profiles mean those documents stay `unsupported`,
not model-read. Multimodal entitlement is unverified until the TASK-005 live smoke runs the image-input check.

### Open Scope Tensions

1. **How much may the model decide?** Proposed resolution: a candidate is `accepted` only when every validator in
   section 4 passes and no parsed value disagrees; otherwise `flagged`. Owner: project owner (section 6, Q2).
2. **Cost vs coverage.** Proposed: per-document and per-project caps from the MI-5 work-unit limits; exhaustion
   records partial coverage, not silent truncation. Owner: owner (Q5).

## 3. Acceptance Criteria

| ID | Type | Given / when / then or measured threshold | Score | Annotation | Test |
|---|---|---|---|---|---|
| AX-1 | Behavioral | For each ambiguity-class fixture, a run with the stub provider persists typed candidates, each with a locator that resolves to the source span and the quoted text matching it, plus model/prompt/version ids and usage. | 3 | [Assumed: verify] | `test_candidates_persisted` |
| AX-2 | Negative | A candidate whose locator does not exist, whose quoted text is not in the cited span, whose unit does not parse or is dimensionally wrong for the attribute, or whose value is out of plausible range is rejected with a machine-readable reason; nothing from it appears in accepted claims. | 3 | [Assumed: verify] | `test_validators_reject` |
| AX-3 | Negative | A candidate that disagrees with a deterministically parsed value for the same attribute/subject/time is `flagged` as a conflict and the parsed value remains unchanged and authoritative. | 3 | [Validated: owner rule, deterministic first] | `test_no_override_of_parsed` |
| AX-4 | Negative | Prompt-injection text inside a source ("ignore previous instructions", fabricated tool calls) changes no state, scope or tool use; only the typed candidate schema is accepted from the model; malformed/oversized/refused output yields an explicit failed attempt, not a partial success. | 3 | [Validated] | `test_hostile_source_text`, `test_malformed_output` |
| AX-5 | Behavioral | Subject-identity candidates not supported by an existing identity candidate stay unresolved; a wrong-folder/cross-well fixture keeps the actual source subject; MD is never treated as TVD; no CRS, date order or installed state is invented. | 3 | [Validated: same rules as IN-6/RC-3] | `test_identity_and_reference_rules` |
| AX-6 | Edge case | Cancel, process kill, provider timeout/429/5xx and budget exhaustion leave interrupted attempts that a fenced retry completes without duplicate candidates; exhaustion records the partial coverage and stop reason; interrupted work never appears successful. | 3 | [Validated: INGESTION IN-4 / META MI-3..5 patterns] | `test_extraction_recovery`, `test_budget_stop` |
| AX-7 | Behavioral | The UI shows each candidate's state, reason, validator outcome and a link to the exact source location; accepted, flagged and rejected are distinguishable without color alone; unresolved candidates are never rendered as accepted facts (draft-vs-accepted separation). | 3 | [Assumed: verify] | Vitest + Playwright on a fixture project |
| AX-8 | Non-behavioral | Default tests make zero external requests and spend no credits; re-running unchanged inputs with unchanged model/prompt versions reuses the cached result (no new provider call), and changing the source or prompt version invalidates it. | 3 | [Validated: AC-10; MI-2] | `test_no_network`, `test_extraction_cache_keys` |
| AX-9 | Negative | A stub-provider run that requests a tool outside the allowlist, a locator or document outside the project, an unbounded range, or more than the per-unit tool-call limit is refused with a recorded reason and no data from outside scope is returned; allowed tools return only content with locators, and a page-image request returns the image for that locator only. | 3 | [Validated: owner allows tools/multimodal; project tool rules] | `test_tool_allowlist_and_scope`, `test_tool_call_bound` |
| AX-10 | Behavioral | Each work unit persists an activity log (question, ordered steps, tool calls with summaries, candidates, validator outcomes, usage, stop reason) scoped to the project and source revision; the Reconstruction tab lists it with state and links to source locations, shows no hidden reasoning text, and interrupted/failed units are visibly not successful. | 3 | [Validated: owner Reconstruction-tab model] | `test_activity_log_persisted`; Vitest + Playwright (TASK-040) |
| AX-11 | Negative | Owner decision October 30: coordinates and trajectory values may be model-extracted only as a labeled backup. When no deterministic source for the subject exists, a candidate that passes every validator (quoted span matches; explicit units, horizontal CRS, vertical datum, depth reference and azimuth reference stated in the source or its cited context; plausible and monotonic MD/stations) is accepted with evidence class `model_proposal` and a visible "agent-extracted fallback" marker that propagates to every derived geometry, distance and tool result. A missing CRS/datum/reference is never assumed (the value stays flagged and the affected output blocked). Once a deterministic source exists, it wins and the fallback is superseded; a disagreement is flagged, never resolved by the model. | 3 | [Validated: owner; guardrails Assumed: verify] | `test_coordinate_fallback_labeled`, `test_fallback_requires_explicit_reference`, `test_deterministic_supersedes_fallback` |

Definition of done: all ACs pass with recorded commands/results (stub provider, not live); independent QA; integration per
[workflow](../DEVELOPMENT_WORKFLOW.md). Live quality is measured later (section 6, Q5) and must not be claimed from stubs.

## 4. Context and Decisions

- Executor profile: `fieldlens-ingestion`, coordinating with `fieldlens-rag` for the harness/adapter interface; the
  worker must not delegate. Skills: `fieldlens-document-ingestion`.
- Decisions already made: native structured parsers first, then model judgement for ambiguity; the harness owns runs, validation,
  cancellation, recovery and budget; model tools never publish or bypass validation; documents are untrusted data.
- Pipeline: deterministic profile output with an ambiguity marker -> extraction work unit (bounded context from the cited
  spans only) -> provider adapter (stub offline) -> schema validation -> deterministic validators -> persisted candidate
  state -> issue/evidence views -> consumed by reconstruction (FL-016).
- Bounds: each work unit obeys MI-5 (<= 4 attempts, <= 6 tool calls, <= 90 s, <= 4,096 output tokens/attempt, <= USD 0.50
  reserved); project-level caps follow the approved budget policy. The 6-tool-call limit may prove tight for
  tool-using extraction; it stays the default and is tunable only by amending MI-5 with measured evidence. Tools are
  the read-only allowlist in section 2; the output is a typed object, not code.
- Disclosure `[Validated: owner, October 30]`: all documents are open source and shareable with third parties without
  restriction, so content, page images and tool results may go to the entitled provider. This authorization covers
  the Volve demo documents; any other source needs its own confirmation. Standard mode only; never Contributor mode.
- Contracts: candidate state (`candidate|accepted|rejected|flagged`), reason codes, validator results and
  `extraction_method = model_proposal` must be representable with existing `EvidenceClass`/`ValidationState`/`Locator`
  contracts. If a new enum value or table is needed, that is a shared-contract change with a single writer, registry
  entry, regenerated client and `check:contracts` (open item for TASK-035). Persistence via a migration; PostgreSQL tests.
- Historical semantics: effective time, report time and dataset revision stay separate; date precision is preserved as
  written; no same-day ordering is invented; the as-of context is part of every cache key.
- Delegation: one writer/branch; files `backend/fieldlens/ingestion/` (extraction), `backend/fieldlens/evidence/`
  (candidate states/issues), tests, migration;   frontend candidate display only through existing evidence components (TASK-034 restyles them later).
  Isolated database/ports per the dev-tooling lanes; budget reservation per MI-3; no live calls.
- Model routing: Sonnet 5.5 / medium `fieldlens-ingestion`; verify host resolution at dispatch (TASK-001 policy).
- Agent/UI effects: the extraction tools are read-only and mutate nothing; the UI shows validated IDs, states and the
  activity log only. These tools are separate from the exploration/chat tool set (FL-011).

## 5. Failure Conditions

1. **Plausible but wrong value accepted.** A fluent model output passes schema checks and is treated as fact. Prevent:
   acceptance requires the deterministic validators (AX-2/3/5); LLM confidence is never an input to acceptance.
2. **Silent override or fabrication.** The model "fixes" a parsed value, fills a missing unit/CRS/date or links an
   unverified subject. Prevent: AX-3/5; unknown stays unknown; affected outputs are blocked, unrelated records are not.
3. **Hostile or malformed source/output.** Injection, truncation, refusal or provider failure. Prevent: AX-4/6; failed
   attempts are persisted as failed, never as partial success.
4. **Runaway cost or repeated work.** Prevent: MI-5 limits, reservations (MI-3) and cache keys (AX-8).

Failures return to the implementer; QA re-verifies; the owner decides scope/budget questions. Worst misinterpretation
test: a stub that echoes a fixed candidate passes AX-1 but not AX-2/3/4/5, which use adversarial fixtures that a
pass-through implementation cannot satisfy.

## 6. Ambiguity Audit and Owner Decisions (TASK-035)

| # | Question | Owner decision `[Validated: owner, 2026-10-30]` |
|---|---|---|
| 1 | Ambiguity classes / when the model is used | Yes: question-driven, whenever a specific question about an entity, measurement, fact or record needs broader document context or multimodal input. Classes (a) tables/units and (b) free text both fit; (c) and (d) as in section 2. |
| 2 | Acceptance policy | Yes: accepted only if all validators pass and no parsed value conflicts; otherwise flagged; no reviewer-accept path. |
| 3 | Fields never model-extracted | Revised October 30: coordinates/trajectories come from deterministic parsers first. If no reliable deterministic source exists, a model-extracted value may be used as a labeled backup (AX-11): explicit reference metadata required, never assumed, visible "agent-extracted fallback" marker on all derived outputs, superseded by any later deterministic source. Values without a quotable source span are never accepted. |
| 4 | Contract change | Yes: one shared-contract change with a single writer (registry, regenerated client, `check:contracts`). |
| 5 | Live spend | Yes: none in TASK-036; later live measurement falls under the USD 150 budget and the TASK-020/028 allowances, authorized separately. |
| 6 | Disclosure | All documents are open source and shareable with third parties; the model may receive content or use the provided read-only tools. Recorded in section 4 (scope: Volve demo documents). |

Follow-on work from these decisions: TASK-038 (activity log, backend), TASK-040 (Reconstruction tab view) and a multimodal image-input
check in the TASK-005 live smoke (within its USD 1 allowance).

## 7. Implementation Guidance

Smallest approach: (1) define the candidate schema/states/reason codes and a migration; (2) the extraction work unit
and cache keys over the TASK-004 adapter with a fixture-driven stub provider; (3) the validators (locator/quote match,
unit/dimension, range, identity, conflict-with-parsed); (4) the read-only tool allowlist and page-image access, with
scope checks; (5) recovery/budget behavior; (6) the evidence/issue view. TASK-038 adds the activity log (backend: `backend/fieldlens/activity/`, migration 0006, read API
`/api/v1/projects/{project_id}/agent-units`; tests `backend/tests/activity`, named `*_ax10`) and TASK-040 its view. The step_key convention belongs to the TASK-036 harness; replaying a key returns the stored
step without comparing content, so a reused key with different content is ignored.
Start with one ambiguity class end to end (table/unit interpretation on a TASK-009 fixture), then add classes in order.
Do not claim proposed commands exist; record actual test commands and results at handoff.

### Implementation handoff and integration

| Field | Record before handoff / after integration |
|---|---|
| Feature commits / tested HEAD | pending |
| Verification | pending; stub provider only, label live vs offline |
| Execution usage | pending; actual model/effort evidence |
| Compatibility assessment | pending; new feature, possible shared-contract addition |
| Proposed version bump | minor, orchestrator allocates |
| Proposed changelog entry | FL-022: validated model-proposed extraction candidates |
| Related documentation | INGESTION.md, DATA_QUALITY.md cross-references |
| Residual blockers / owned resources | none yet |
| Integrated commit / final version | pending |
| Backlog status | ready |
