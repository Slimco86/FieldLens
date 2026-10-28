# Specification: Evidence-led composite-asset reconstruction

> **Spec type:** Product/feature with agent execution contracts. **Backlog:** FL-016.
> **Load-bearing frameworks:** F1, F2, F4, F5. **Supporting:** F3, F6.
> **Date:** 2026-10-28. **Author:** main orchestrator. **Decision owner:** project owner.
> **Status:** Draft; reconstruction objective required, detailed review policy proposed.
> **Delivery state:** specifying. **Approved revision / integration:** none.
> **Zero-Question Score:** 0 unowned questions; approval and source/live gates remain.

## How to Read This Spec

Owner: outcome/review boundary. RAG/backend executors: section 4. QA: RC criteria,
gold cases and failure conditions. Covers project AC-2/7/8/10/12.

## Notation Key

`[Validated]` identifies an owner requirement, not an implemented result.
`[Assumed: verify]` identifies a proposal for owner approval before handoff.
H/M/L are confidence estimates; AC score 3 is binary-testable. A cited model
proposal is not automatically a valid engineering claim.

## 1. Outcome Statement

From a project source revision, the user can run a bounded Meta-led investigation,
inspect an evidence-linked candidate asset model and its unresolved questions,
and publish only an eligible revision without silently changing prior results.
Verification: RC-1 through RC-10, with offline and live results separate.
Outcome score 3.

## 2. Scope

### IN Scope

Identify fields, wells, wellbores/sidetracks, completion configurations, installed
component instances and perforated intervals; reconcile aliases and source
subjects; propose typed relationships, attributes and effective-time events.
Preserve support, contradictions and missing information. `[Validated: owner point 3]`

A persistent reconstruction run, typed tool loop, candidate/diff/evidence UI,
revision publication and incremental re-evaluation are included.
`[Validated: custom harness; assumed: explicit run and review/publication policy]`

### OUT of Scope

Model-generated CAD, source-free identities/dimensions, arbitrary code/SQL, automatic
project-wide web crawling, autonomous publication and a full manual fact editor
are excluded. Rendering, deterministic engineering and conversational exploration
consume the model through FL-006..011; they are not substitutes for reconstruction.

### Scope Dependencies

FL-004/015 project contracts, FL-005 qualified extraction, FL-011-A/B scoped source
retrieval/UI and FL-003-A offline harness support precede the offline slice.
Live RC-10 also needs FL-003-B, approved gold sources/allowance and selected
scanned/Word source qualification when those sources are used. Full G1 is required
for final pilot acceptance, not for each bounded early investigation.

### Open Scope Tensions

Automation versus evidential authority: the agent proposes/investigates; validation
and an explicit user publication action control active state. Owner must approve
this review policy before implementation. Publish never converts unknowns to facts.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| RC-1 | Behavioral | Given a qualified source revision and work scope, a run yields typed entities/relationships/claims, per-attribute evidence and an explicit coverage/unresolved list, visible in the tree/table UI before any 3D viewer exists. | 3 | [Validated] | `reconstruction-review.spec.ts` |
| RC-2 | Behavioral | Cross-document aliases map to one stable entity only with supported identity evidence; well/wellbore, sidetrack, catalog model/installed instance and planned/as-installed remain distinct in all gold cases. | 3 | [Validated] | `test_entity_resolution` |
| RC-3 | Negative | Wrong-folder and cross-well narrative fixtures retain the actual source subject; ambiguous identities remain candidates. Unsupported edges, circular sidetrack/containment links and missing evidence cannot be published as valid. | 3 | [Validated] | `test_relationship_validation` |
| RC-4 | Behavioral | Effective time/precision, report time and revision time remain separate. Contradictory dates/CRS/dimensions block affected conclusions; unknown initial history stays unknown and no same-day order is invented. | 3 | [Validated] | `test_temporal_reconstruction` |
| RC-5 | Behavioral | Review shows added/changed/removed associations with citations; publish atomically advances the expected active model revision only after validation. Reject or 409 stale-base failure leaves the prior active model unchanged. | 3 | [Assumed: verify] | `test_model_publication` |
| RC-6 | Edge case | Re-import/retry produces no duplicate accepted entities/events; replacement sources re-evaluate dependent claims/edges/projections while old revisions remain reproducible. Unsupported old claims are not carried forward as current facts. | 3 | [Validated] | `test_reconstruction_invalidation` |
| RC-7 | Non-behavioral | One model work unit obeys MI-5: <=4 provider attempts, <=6 tools, <=90 seconds and <=USD 0.50 reserved cost. Limit exhaustion records partial coverage/stop reason; no unattended continuation is dispatched. | 3 | [Assumed: verify limits] | `test_reconstruction_bounds` |
| RC-8 | Edge case | Cancel/restart/provider failure persists state/usage and publishes nothing; another project/revision's IDs and hostile source instructions cannot broaden scope or execute unauthorized tools. | 3 | [Validated] | `test_reconstruction_recovery` |
| RC-9 | Negative | Schema/citation existence and model confidence alone cannot make a semantic association valid. Qualified deterministic mapping or recorded source-support review is required; reviewer publication cannot waive critical measurement/reference checks. | 3 | [Validated] | `test_proposal_is_not_truth` |
| RC-10 | Dependency | The approved 12-case reconstruction gold set runs through the actual entitled Meta harness with exact expected supported relationships/unknowns and zero unsupported published facts; source locators, usage and typed outputs are retained within a separately approved <=USD 3 evaluation cap. | 3 | [Assumed: verify gold/allowance] | opt-in `test_reconstruction_live_gold` |

Ten criteria, score 3. Offline replay verifies machinery, not RC-10. A successful
text response, a prebuilt graph or a screenshot cannot pass reconstruction acceptance.

## 4. Context and Decisions

Executor: `fieldlens-rag` owns the bounded harness and reconstruction UI slice;
backend owns shared persistence/transactions under serialized contract changes.
The main agent allocates a committed base, worktree and isolated resources;
there is no current implementation assignment. Owner approves publication policy,
gold cases and spend. Development subagents are not application-runtime agents.

### Output model and authority

A project owns a graph, with a containment tree as one view:
field -> well -> wellbore; a wellbore has dated completion configurations; each
configuration relates installed equipment and relevant interval states. Sidetrack,
evidence, series and catalog relationships are additional typed edges, not forced
into one parent tree. A component's role/model is distinct from its instance ID.
Equipment migration between configurations is an explicit relation/history, not
an inferred new installation on every mention.

Each proposed entity/edge/attribute records source record IDs, evidence locators,
original values/references, effective-time bounds/precision, extraction method,
proposal run/model version, validation result and conflict/unknown reasons.
Entity identity does not depend on filename or model-generated UUIDs: the server
allocates IDs, resolves supported aliases and returns candidates for ambiguity.

Source observations are readable before there is an accepted asset graph.
Keep two retrieval modes: source evidence (including labeled unresolved records)
and published model facts. The first bootstraps reconstruction; the second drives
engineering/tools. No circular requirement that a graph must exist to build it.
Structured native extraction remains first; OCR/LLM-assisted interpretation is
profile-gated and retains original page/cell/image locators and uncertainty.

### Harness and tools

One Python orchestration layer has reconstruction and exploration modes. The
SDK supplies model I/O, not agent semantics. Pydantic validates typed tools;
PostgreSQL persists runs, proposals, tool results and budget reservations.
No new runtime agent framework/service is selected. Revisit only if measured
branching/recovery requirements cannot be maintained clearly in this design.

Reconstruction-only tools: `list_project_sources`, `read_source_records`,
`search_evidence`, `get_candidate_model`, `propose_entities`,
`propose_relationships`, `propose_claims`, `validate_candidate`,
`record_unresolved`. Batch proposals are bounded by shared collection limits.
Proposals write only to their run's staging area, never accepted domain rows.
`research_equipment` is separately permission/budget-gated and cannot prove
installation. `publish_revision` is a user API action, never a model tool.
Exploration uses read/calculation/navigation tools and cannot mutate candidates.

Run input: project, immutable source revision, expected base model revision,
selected source/asset scope and an approved bounded allowance. Context is fixed
at run creation; switching projects in the browser cannot retarget the run.
Processing: inspect coverage -> select next evidence/tool task -> propose ->
validate -> request additional bounded evidence or stop -> present draft.
This is genuine evidence-dependent tool selection, not a fixed graph returned
after a decorative model call.

Run states: `queued/running/needs_review/published/rejected/failed/cancelled/interrupted`.
Coverage and stop reason are separate fields. `needs_review` means the worker
finished a draft, not that every required source/entity is reconstructed.
State transitions and tool outputs are durable; persist useful task summaries,
tool names/IDs, errors and usage, not private reasoning traces or secrets.

Native parsing/index jobs precede the bounded model work unit. One work unit
may cover only one assembly/question; the 90-second limit is not a claim that
the whole download can be processed in 90 seconds. Explicit Continue creates a
new run and candidate revision seeded from the predecessor's durable evidence/
proposals, preserving supported entity IDs and pinning the same source/base.
The predecessor is not mutated; the UI identifies the successor. Each new run
has a new reservation and idempotency key. If either draft is published, another
draft against the old base fails publication with 409. No automatic paid restart.
New uploads require an explicit new source revision/run.

### Review and publication

UI shows the proposed hierarchy/relations, source-linked attributes, timeline,
coverage, validation issues and diff from the base revision. Unknown/unlocated
items are visible without invented geometry. The minimum review UI permits
review evidence, publish eligible revision or reject; arbitrary manual merge,
split and measurement editing remain deferred.

Publication checks all accepted claims/edges, source membership and expected base
in one transaction. Invalid/unsupported proposals stay in the issue ledger, not
the accepted graph. A partial published revision retains explicit coverage and
unknowns. Only valid inputs feed deterministic geometry/temporal projections;
per-feature projection readiness is separate from model publication.
A reviewer may confirm source support but cannot erase unresolved critical
references, fabricate dates or make catalog dimensions installed measurements.

Gold set, authored independently of the model: direct identity, alias, sidetrack,
cross-well report subject, planned/installed separation, catalog/instance separation,
missing reference, ambiguous date, contradictory dimensions, duplicate import,
source replacement/invalidation, and injected document instructions (12 cases).
Each fixture declares exact expected entities/edges, support locators, rejected
claims, unknowns and time semantics. G3 approval is needed before live acceptance.

## 5. Failure Conditions

- Semantic support cannot be checked -> keep proposal unreviewed; schema success
  is insufficient. Escalate parser/review gap, not confidence threshold tuning.
- Live protocol/budget unavailable -> disable paid run, preserve source browsing
  and existing models; do not impersonate a live result with a fixture.
- Base changed while reviewing -> 409, recompute diff/revalidate against a new
  base; never overwrite another accepted revision.
- Required extraction is incomplete -> report missing pages/records and block
  dependent facts; unrelated supported records remain inspectable.

Worst misinterpretation: an attractive asset tree of plausible but unsupported
objects fails RC-3/9/10 even if every node has a real, unrelated citation.

## 6. Ambiguity Audit

Primary reconstruction objective and Meta harness are owner requirements.
Explicit run, review-before-publication, tool limits and exact gold thresholds
are draft defaults. Owner decides before FL-016 handoff; G2/G3/G5 qualify live
protocol, source-backed expectations and extraction resources respectively.

## 7. Implementation Guidance

Planned paths: `backend/fieldlens/reconstruction/`, shared
`backend/fieldlens/assistant/` harness, `frontend/src/features/reconstruction/`,
and matching tests. FL-011 owns retrieval/exploration; reuse one provider/budget
implementation. Shared migrations/types and app composition have one writer.

Offline slice produces a working browser draft/review workflow. A separately
authorized live slice verifies evidence-dependent Meta behavior on qualified
sources before declaring the agent delivered. No implementation/tests or
integration SHA exist. Feature implementation proposes minor; documents are patch.

## Open Tensions

The first bounded run need not reconstruct all project files; whole-project
coverage must enumerate work remaining. The owner approves limits before handoff;
an incomplete run cannot satisfy final G1/demo acceptance.

## Assumption Registry

| Assumption | Confidence | Validation / invalidation |
|---|---|---|
| Revision-level review is enough without a full fact editor | M | Owner approval; reopen if actual ambiguity prevents useful publication |
| A small persistent tool loop fits required workflows | H | Reopen on unsupported branching/recovery after measured prototype |
| Qualified source records allow bounded cross-document reconstruction | M | G3 live gold results; failure blocks agent acceptance, not grounding rules |

## Adversarial Self-Critique

- Exact IDs can hide a wrong subject: test the F-14 report about F-12 operations.
- A changed source can leave stale edges: test dependent invalidation, not just text reindexing.
- Publish can become an evidence bypass: validate support and critical references again server-side.

## Revision Triggers

Reopen if source corrections require unavailable review operations, the selected
Meta protocol cannot perform bounded tool rounds, or live gold cases need scope/
budget beyond the approved work unit. Never silently weaken the criteria.
