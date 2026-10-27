# Specification: <single capability and observable outcome>

> **Spec type:** Product/feature | API contract | Agent task | Research/discovery.
> **Load-bearing frameworks:** <outcome, acceptance, scope, context as applicable>.
> **Supporting:** <failure conditions, ambiguity audit as applicable>.
> **Date:** <date>. **Author:** <author>. **Decision owner:** <owner>.
> **Status:** Draft -> Approved -> Implementing -> Verified.
> **Backlog ID:** <FL-id>. **Delivery state:** <from BACKLOG; Verified is not merged>.
> **Approved spec revision/date:** <owner decision>. **Integration version:** <pending>.
> **Zero-Question Score:** <unowned unresolved questions; list owned blockers too>.

Keep this document proportional to one increment. Replace placeholders; do not
implement against unresolved critical decisions. Update an existing feature spec
for closely related behavior changes instead of creating redundant documents.

## How to Read This Spec

Owner: outcome/scope/tensions. Implementer: scope/contracts/ACs. Tester:
ACs/failures/verification. Link the relevant project-level requirement IDs.

## Notation Key

`[Validated]` = owner/source confirmed; `[Assumed: verify]` = proposed, name approver;
`[Unknown: TBD]` = name owner and due date. H/M/L = confidence estimate:
>70% / 40-70% / <40%, not measured probabilities.
AC score 0 = subjective, 1 = unstated context, 2 = outsider-testable, 3 = binary.

## 1. Outcome Statement

After this increment, <specific user-visible or testable state becomes possible>.
Verification method: <command/scenario and observable result>.
Outcome score: <0-3; target 3>.

## 2. Scope

### IN Scope

<Explicit supported inputs, workflows and feature boundaries, with evidence tags.>

### OUT of Scope

<Name adjacent capabilities and why excluded. Do not remove mandatory project scope.>

### Scope Dependencies

<State dependencies and their readiness; "none" if verified none.>

### Open Scope Tensions

<Conflict, proposed resolution, decision owner and deadline.>

## 3. Acceptance Criteria

| ID | Type | Given / when / then or measured threshold | Score | Annotation | Test |
|---|---|---|---|---|---|
| AC-1 | Behavioral | <observable result> | 3 | <source/owner> | <test> |
| AC-2 | Negative | <behavior that must not occur> | 3 | <source/owner> | <test> |
| AC-3 | Edge case | <specific error/empty/partial condition> | 3 | <source/owner> | <test> |

Add performance, cost, integrity and dependency criteria where relevant. Define
fixture, units, numerical tolerance and measurement method before implementation.
Definition of done: all ACs pass; record actual commands/results and live/stub status.
Delivery is complete only after verified integration, version/changelog updates
and backlog reconciliation under the [workflow](../DEVELOPMENT_WORKFLOW.md).

## 4. Context and Decisions

- Executor profile and glossary: <assumed knowledge; define domain terms>.
- Decisions already made: <choice, rationale, source, date>.
- Dependencies: <data/models/services, versions, readiness, owner, blocking status>.
- Delegation: <configured agent, base commit, branch, absolute worktree path,
  file ownership, shared-contract owner, resource/port/database/budget allocation>.
- Model routing: <complexity/risk and domain; profile/model/effort per the
  [agent roster](../../.github/agents/README.md); actual host-selection evidence;
  time/tool/attempt bounds; stop and return to orchestrator on gaps or mismatch>.
- Parallelism: <hard prerequisite backlog IDs; separately approved contract-ready
  slices/stubs allowed; live integration checks still required>.
- Constraints and stakeholders: <scope/cost/deadline/privacy; approver>.
- Contracts: <input/output shapes, IDs, units/CRS/datum, validation, errors,
  provenance, persistence/migrations, revision/cache invalidation>.
- Historical semantics where relevant: <event effective time versus ingestion time,
  date precision, state scope/validity, selected as-of time and revision, MD/TVD/
  interval-length derivations; document unknown/partial-history behavior>.
- Agent/UI effects: <allowlisted tool, validated IDs, displayed states, evidence
  and acknowledgment; "not applicable" when justified>.

## 5. Failure Conditions

At least two concrete assumption/deviation/action entries. Define affected-record
blocking, retry/cancellation/restart behavior, and owner escalation. Do not replace
failure with fake success.
Worst misinterpretation test: <how a shortcut could pass; tighten ACs to prevent it>.

## 6. Ambiguity Audit

<Resolve definitional, behavioral, precedence, temporal and ownership questions;
otherwise record owner + deadline. An owned blocker still blocks approval.>

## 7. Implementation Guidance

<Smallest approach, actual files/entry points once known, risks and checkpoints.
Record migrations, focused test/type/build commands and results after implementation.
Do not claim proposed commands already exist.>

### Implementation handoff and integration

| Field | Record before handoff / after integration |
|---|---|
| Feature commits / tested HEAD | <actual hashes; no predicted integration hash> |
| Verification | <commands/results, environment/fixtures, live/stub status, skipped checks> |
| Execution usage | <actual model/effort evidence, attempts, elapsed time and exposed tokens/cost; otherwise unavailable> |
| Compatibility assessment | <breaking/new feature/fix-docs; affected API/schema/tool/user contracts> |
| Proposed version bump | <major/minor/patch with rationale; orchestrator allocates final number> |
| Proposed changelog entry | <backlog ID, user-visible changes, migration notes, limitations> |
| Related documentation | <updated files; no unsupported implementation claims> |
| Residual blockers / owned resources | <stop/escalation and cleanup handoff> |
| Integrated commit / final version | <fill only after confirmed merge> |
| Backlog status | <main-agent reconciliation; done only with verified integration> |

## Open Tensions

<State remaining requirement conflicts or "none after review".>

## Assumption Registry

<List assumptions, confidence, evidence, affected criteria and invalidation signals.
Mark assumption-heavy work as draft; do not invent assumptions to fill a quota.>

## Adversarial Self-Critique

<Identify concrete ways this feature could appear correct while violating data,
provenance, operational or UX requirements. Define observable warning signals.>

## Revision Triggers

<Observable source/schema/provider/requirement changes that reopen this spec.>
