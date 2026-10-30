# Specification: Evidence-linked data-quality issues across the workspace

> **Spec type:** Product/feature. **Backlog:** FL-017.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-28. **Decision owner:** project owner.
> **Status:** Owner-approved outcome; implementation contract specified for handoff review.
> **Delivery state:** specifying; no application implementation or acceptance run.
> **Zero-Question Score:** 0 unowned questions; dispatch requires approved committed contract.

## How to Read This Spec

Owner: scope and the real-data cases. Backend/frontend: issue contract and DQ
criteria. QA: exclusions, context races and negative tests. Covers project AC-4/8/12.
This is engineering-data observability, not an infrastructure monitoring product.

## Notation Key

`[Validated]` means owner/source-confirmed, not implemented. `[Assumed: verify]`
identifies an implementation selection for handoff review. H/M/L are confidence
judgments. All criteria score 3: pass/fail is observable, not model confidence.

## 1. Outcome Statement

In Sources, Reconstruction and Explore, a user can identify a missing or
contradictory engineering attribute, open its evidence and see exactly which
outputs are unavailable without losing unrelated valid results.
Verification: DQ-1 through DQ-8. Outcome score 3.

## 2. Scope

### IN Scope

- `[Validated: owner, October 28]` F-12/F-14/F-5 are the selected demo cohort;
  incomplete F-12 equipment and real discrepancies are intentional acceptance cases.
- `[Validated: owner]` Persistent, evidence-linked warnings/errors and generic
  representation labels. Source, draft and published-model contexts stay distinct.
- `[Assumed: verify, H]` One shared issue list/detail component, severity/code
  filters, context-scoped counts and links from evidence, review and inspectors.

### OUT of Scope

Manual fact editing/merge/split, warning dismissal as approval, automatic conflict
resolution, fabricated installation facts, infrastructure dashboards and a new
telemetry service. FL-007 owns meshes; FL-016 owns proposal validation/publication.
FL-017 exposes their results and cannot bypass either validator.

### Scope Dependencies

FL-004 supplies the shared QualityIssue DTO; FL-005-B supplies source records and
evidence navigation. The first vertical slice works before reconstruction or 3D.
Later consumers reuse it; their acceptance checks remain with their feature owners.

### Open Scope Tensions

A useful partial demo must not imply complete engineering truth. Resolve by
publishing only eligible claims, retaining unresolved issues alongside the model,
and blocking each dependent output, not hiding every asset or accepting bad values.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| DQ-1 | Behavioral | A source revision with a conflicting or incomplete record shows persisted issue code, severity text, affected attribute, explanation, evidence links and blocked operations after API/browser restart. | 3 | [Validated outcome] | `test_quality_issue_persistence`, `quality-issues.spec.ts` |
| DQ-2 | Negative | Project/revision filters apply before counts and pagination; another project's issue ID returns 404. Switching context cannot display stale issue counts, rows or evidence. | 3 | [Validated isolation] | `test_quality_issue_scope`, `quality-context.test.tsx` |
| DQ-3 | Edge case | The F-14 reference fixture retains both 53.870 and 54.90 m source values, emits REFERENCE_CONFLICT, blocks affected alignment/calculation and leaves independent valid records available. No value is silently selected. | 3 | [Validated source finding] | `test_reference_conflict_issue` |
| DQ-4 | Edge case | The F-12 2014 fixture retains 3126.2-3139.7 m from the report summary and 3126.2-3130.7 m from detailed activity/service-log evidence; INTERVAL_CONFLICT prevents an exact dependent state/total until qualified resolution. | 3 | [Validated source finding] | `test_interval_conflict_issue` |
| DQ-5 | Behavioral / negative | A documented F-12 component without dimensions shows a Generic - dimensions unavailable label and issue link. Valid placement alone permits a labelled display proxy; unknown/conflicting placement shows an unlocated preview, never a scene depth. No generic dimension enters analytics or engineering export. | 3 | [Validated fallback policy] | `test_generic_issue_impact`, `generic-equipment.spec.ts` |
| DQ-6 | Negative | An issue acknowledgment, review or publish action cannot change validation, suppress a blocker or turn unsupported proposals into accepted claims. Partial publication preserves unresolved issue references and prior revision history. | 3 | [Validated truth boundary] | `test_issue_cannot_waive_validation` |
| DQ-7 | Non-behavioral | Issue pages obey SC-6 limits; keyboard users can open/filter issues and follow evidence, with visible focus and text severity/coverage labels. Zero issues with unknown coverage is not labelled fully validated. | 3 | [Assumed: verify UI contract] | `test_quality_issue_bounds`, `quality-accessibility.spec.ts` |
| DQ-8 | Dependency | Synthetic fixtures exercise all cases offline; real-source acceptance checks exact original hashes/locators for the two conflicts and a supported F-12 component, plus real F-14/F-5 dimensional evidence. No fixture-generated issue is presented as detected from an unread original. | 3 | [Validated evidence boundary] | `test_pilot_quality_issues`, DM-4 |

Eight criteria. Initial FL-017-A verifies DQ-1/2/3/4/7 and the DTO-level negative
parts of DQ-5/6 using labelled synthetic fixtures. FL-016/007 integration completes
DQ-5/6; TASK-029/022 verify DQ-8 with real sources. No partial slice closes FL-017.

## 4. Context and Decisions

Executor: `fieldlens-frontend` owns the bounded issue API/query/UI vertical slice;
shared DTOs and migrations use the serialized backend contract owner. Source,
engineering and reconstruction owners emit issues in their own validators.
Owned paths: `backend/fieldlens/evidence/issues.py`,
`frontend/src/features/evidence/quality/`, and focused tests.
No new generic observability subsystem or independent service.

**Issue** describes an evidence/validation problem. **Severity** describes its
impact, not source credibility. **Coverage** describes what was inspected.
**Blocked operation** names a disallowed dependent output; it is not an
application-wide outage. None of these substitutes for claim validation state.

Use the [shared QualityIssue contract](SHARED_CONTRACTS.md#quality-issues).
Persist scoped issues transactionally with the producer's records/proposals;
do not reconstruct them only from transient log messages. Retries reuse a stable
producer key within the same revision. A different source/model revision gets
its own immutable observations and may reference the prior issue; historical
issues are not deleted when a later revision resolves a problem.

| Condition | Severity / required treatment |
|---|---|
| Missing noncritical mechanical detail with valid identity/placement | warning; labelled generic display, dimensions remain unknown |
| Unknown placement | warning; placement blocked, unlocated preview only |
| Conflicting reference, identity, dimensions or interval endpoints | error; affected claim acceptance/physical geometry/calculation/state blocked as applicable |
| Missing history or extraction coverage | warning; exact dependent totals/state unavailable unless independently justified |
| Unsupported format or failed required extraction | error; affected records unavailable; preserve source and explicit processing failure |

The producer determines impact from the dependency graph and typed validators;
the browser does not infer permissibility from color or downgrade an error.
Missing information cannot be fixed by fabricating a full F-12 assembly. Show
only source-supported component identities; an assembly-level gap is an issue,
not a licence to add imagined packers/valves/quantities.

Source view opens a record/page/cell. Draft review opens the competing proposals
and citations. Explore shows active-model coverage plus unavailable outputs;
it never mixes issues from a newer unreviewed source revision into old facts.
No Dismiss, Override measurement or Accept anyway controls in this slice.

## 5. Failure Conditions

- Producer cannot associate an issue with its context/evidence -> fail that
  record's validation; do not emit an unscoped success result. Return the contract
  gap to the orchestrator.
- Selected original does not match the approved hash/locator -> stop real-source
  acceptance and requalify the fixture, not its expected answer.
- UI shows an error but dependent numeric output remains enabled -> fail
  acceptance and repair the server-side eligibility check.
- Shared migration/client ownership overlaps another assignment -> stop the
  second writer and request serialization.

Worst misinterpretation: decorative warning badges on fabricated geometry fail
DQ-3/4/5/6 even if every badge opens a genuine source document.

## 6. Ambiguity Audit

The owner accepted incomplete F-12 equipment, not missing truth boundaries.
Warnings do not waive validation; partial publication is allowed only for valid
claims. Unknown placement is unlocated. No automatic replacement by F-11 B.
Final history windows/transforms remain G1 tasks, not UI implementation guesses.

## 7. Implementation Guidance

**TASK-009 issue codes (added to `IssueCode`).** `MISSING_REFERENCE` (depth datum, CRS or
azimuth reference absent), `MISSING_UNIT` (a quantity carries no stated unit; none is
assumed), `SUSPICIOUS_VALUE` (placeholder zeros, negative volumes, hours above 24, MD equal
to TVD, TVD above MD), `UNKNOWN_CODE` (enumeration value outside the seeded WITSML list) and
`ASSEMBLY_TYPE_MISMATCH` (drilling BHA vs completion equipment). Each blocks only the
outputs that depend on the affected value; the original value stays unchanged and visible.

TASK-003 defines/round-trips the DTO; TASK-009 emits native-source issues;
TASK-032 delivers list/detail/evidence navigation; TASK-026/012 reuse the component
for review and generic equipment. Add no new runtime service.
Planned checks: focused pytest issue tests, frontend quality interaction tests,
typecheck/build and focused Playwright scenarios. Foundation establishes actual
commands; no checks are claimed run here.

Handoff requires tested SHA, source mode (synthetic/real), affected contracts,
owned-resource cleanup and proposed minor release note. Orchestrator allocates
the version; this documentation-only integration remains a patch.

## Open Tensions

No unresolved behavioral choice. Final source qualification is still required;
accepting visible limitations does not establish missing measurements.

## Assumption Registry

- Shared issue components can serve source/draft/model views (H); revise if context
  eligibility cannot be represented without losing source lineage.
- Qualified source profiles can detect the named discrepancies (M); verify DQ-8,
  do not infer detection from a manually prepared fixture.
- Existing evidence navigation can display required locators (M); unread Word
  images or wrong PDF pages block the affected acceptance, not prompt fabrication.

## Adversarial Self-Critique

- A zero count can hide an unread scan: pair counts with extraction coverage.
- A generic part can imply installation: require supported identity and independent
  placement validation; show unlocated when absent.
- Issue deduplication can erase competing evidence: deduplicate retries, not
  different values or different source revisions.

## Revision Triggers

Reopen if manual resolution is requested, a selected discrepancy needs unsupported
locator/impact types, or a revision change loses historical issue/evidence links.
