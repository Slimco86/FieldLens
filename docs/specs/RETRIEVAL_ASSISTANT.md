# Specification: Grounded hybrid retrieval and bounded viewer assistance

> **Spec type:** Product/feature. **Backlog:** FL-011.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-27. **Decision owner:** project owner.
> **Status:** Design complete; corpus/model evaluation and live acceptance not run.
> **Zero-Question Score:** 0 unowned design questions; G1/G2/G3/G5 are execution gates.

## How to Read This Spec

Executor: retrieval/tool contracts. QA: RG criteria/evaluation set. Owner:
grounding boundaries and live budget. Implements project AC-7/8/10.

## Notation Key

`[Validated]` = project truth/cost requirement; `[Assumed: verify]` = proposed
algorithm/threshold. H/M/L are confidence. Score 3 = explicit pass/fail.
The evaluation design is complete; actual gold source answers await G1.

## 1. Outcome Statement

The assistant answers supported field questions with validated evidence and
deterministic numbers, proposes valid UI actions and explicitly declines unsupported
claims, including when the provider or budget is unavailable.
Verification: RG-1 through RG-7. Outcome score 3.

## 2. Scope

### IN Scope

Exact/full-text/vector retrieval, typed graph traversal, evidence-cited answers,
numeric domain tools, acknowledged UI actions and bounded equipment-only research.
All are `[Validated: project scope]`.

### OUT of Scope

Unrestricted autonomous agents, generated SQL/code/scripts, reservoir simulation,
general web enrichment, inferred installation/interval flow and a non-Meta fallback.

### Scope Dependencies

FL-011-A retrieval needs FL-005-B accepted evidence/chunks.
FL-011-B offline assistant/tools/UI needs FL-011-A, FL-003-A, FL-007-A,
FL-008-B and FL-010-C. FL-011-C live acceptance additionally requires FL-003-B
and G1/G3 gold cases. Source-independent mocks do not close these live gates.

### Open Scope Tensions

Citation existence is not semantic support. Validate citation scope server-side
and compare factual answer claims against source-backed gold evidence during QA.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| RG-1 | Behavioral | Exact identifiers return only the mapped entity or explicit ambiguity; retrieval applies revision/entity/time eligibility before lexical/vector/graph ranking. | 3 | [Validated] | `test_retrieval_scope` |
| RG-2 | Non-behavioral | Gold answer evidence appears in top five for >=22 of 24 answerable cases; all 4 exact-ID cases find the correct record; at most 10 chunks/12,000 tokens reach the model. | 3 | [Assumed: verify targets] | `test_retrieval_gold` |
| RG-3 | Behavioral | Tools return schema-valid evidence, quantities and context; all numerical answers match deterministic results within fixture tolerance and every factual answer block cites supporting evidence/tool IDs. | 3 | [Validated] | `test_tool_results`, gold claim review |
| RG-4 | Negative | All eight negative controls below refuse unsupported assertions/actions; malicious document instructions cannot execute commands, broaden scope, fetch arbitrary URLs or erase provenance. | 3 | [Validated] | `test_agent_negative_controls` |
| RG-5 | Edge case | Stale/rejected actions are not described as applied; cancellation, provider outage, malformed results and unavailable vector index expose explicit state without fake success. | 3 | [Validated] | `test_action_ack`, assistant interactions |
| RG-6 | Dependency | The fixed 32-case evaluation runs with the entitled live Meta model, produces >=22 correct supported answers of 24, passes all 8 controls, and records protocol/usage within approved USD 3/run. | 3 | [Assumed: verify evaluation allowance] | opt-in `test_assistant_live_gold` |
| RG-7 | Behavioral | Public model research is limited to documented public identifiers, <=3 queries/5 pages/60 seconds and permission/budget; conflicting variants return alternatives, not invented installation. | 3 | [Validated scope; assumed limits] | `test_equipment_research_tool` |

Full verification requires RG-6. Offline replay measures contracts and regressions,
not live model performance. Source support and numerical correctness must be 100%
for claims actually emitted; an unanswerable reply to a positive case counts wrong,
not permission to invent an answer to meet the overall score.

### Fixed evaluation composition

| Family | Answerable cases | Required coverage |
|---|---|---|
| Exact/source lookup | 4 | Well versus bore; sidetrack; source locator; revision |
| Equipment | 4 | Source dimension; catalog dimension; configuration; missing attribute explanation |
| Navigation | 4 | Select bore; focus component; open evidence; acknowledge chart action |
| Charts | 4 | Production window; log curve; units/gap explanation; acquisition-time distinction |
| Closest approach | 4 | Two path pairs; MD bounds; physical versus exaggerated display |
| Perforation history | 4 | t1/t3/t4 fixture equivalents; total versus open coverage |
| Negative controls | 8 | Unknown ID; wrong revision; wrong catalog variant; unknown placement; incomplete initial history; unsubstantiated interval flow; hostile document instructions; budget/provider failure |

Each case records question, context, required source/tool IDs, expected supported
claims, numeric values/tolerance, allowed action/ack and forbidden assertions.
Source-specific gold cases are authored from G1, not generated by the model being
evaluated. Use synthetic equivalents for default tests and identify them as such.

## 4. Context and Decisions

Executor: `fieldlens-rag`, owning `backend/fieldlens/{retrieval,assistant}`,
assistant frontend feature and tests. Shared evidence/series/engineering APIs
are consumed, not reimplemented. The main agent serializes migrations/contracts.

Chunks contain document/revision, page/record locators, entity/claim IDs, temporal
coverage and extraction quality. Preserve table headers/units and row locators;
do not split a number from its attribute/unit. Target <=800 tokens/chunk with
<=100-token overlap; split oversized tables by row groups repeating headers.
Keep the original record as the evidence authority.

Use the [architecture ranking recipe](../ARCHITECTURE.md): exact lookup,
PostgreSQL `simple` full text and exact cosine vectors, RRF constant 60, bounded
two-hop graph expansion. Typed edges include well-has-bore, sidetrack-of,
component-in-configuration, instance-of-catalog-model, series-for-asset,
claim-supported-by and validated intersects-formation. No inferred hydraulic
connectivity edge. Every edge references supporting claims and revision validity.

The 384-dimensional FastEmbed/bge-small candidate requires model revision/license
and retrieval/RSS validation before acceptance. One CPU embedding process, batch
16 initially, no GPU assumption. Store model/dimension/preprocessing fingerprint;
changed fingerprint creates a new index and never silently reuses old vectors.
Embedding failure leaves exact/text retrieval explicitly degraded.

Tool names: `search_evidence`, `get_equipment`, `get_perforation_state`,
`get_series_window`, `calculate_closest_approach`, `propose_viewer_action`,
`research_equipment`. IDs/context/results are validated server-side through
[shared contracts](SHARED_CONTRACTS.md). Maximum six tool calls includes failed
calls. Return compact statistics/intervals, not raw trajectories or log arrays.

Answer envelope: status, QueryContext, ordered text blocks with evidence/tool
references, uncertainty notes, action proposals/ack status and usage.
Sanitize Markdown; external links never become server fetch instructions.
Discard unsupported citation IDs and fail answer validation explicitly rather
than removing citations and presenting the remaining prose as grounded.

UI shows pending/tool/provider/budget/failure states and Stop. Requests are
persisted, polled and cancelled using the shared REST surface; no duplicate
dispatch on refresh. Action acknowledgment is required before claiming completion.
Apply [Meta controls](META_INTEGRATION.md), including four total attempts/90 seconds.
One opt-in public catalog query may be included in the live evaluation allowance
after source identifier/rights authorization; otherwise RG-7 live coverage is
recorded blocked, not silently counted from mocks.

## 5. Failure Conditions

Index/gold evidence missing -> report unavailable/degraded and keep RG-2 blocked.
Provider emits invalid tool/citation IDs -> reject affected request/action, retain
sanitized diagnostics/usage and do not retry into unrestricted behavior.
Worst misinterpretation: plausible prose with real but irrelevant citations fails
the gold claim-support review even when the JSON schema passes.

## 6. Ambiguity Audit

Ranking, context limits, graph depth, tools, metrics and evaluation counts are
fixed. Gold source answers are G1/G3-owned evidence due before FL-011-C.
Actual embedding suitability is G5; no unknown model endpoint is assumed.

## 7. Implementation Guidance

FL-011-A: retrieval/index tests and RG-1/2. FL-011-B: offline tools/UI RG-3/4/5/7.
FL-011-C: live RG-6 and authorized research check. Planned commands: retrieval/
assistant pytest files, frontend assistant interactions, type/build, separate
live marker only after allowance approval. Record model/index revisions,
gold-case results and every failed/control case. No implementation result yet.
Propose minor; orchestrator owns release metadata and final evaluation acceptance.

## Open Tensions

Unavailable source facts remain unavailable; a score target cannot override that.

## Assumption Registry

Gold evidence is extractable (M; G1). Small embeddings meet recall/RSS (M; RG-2/G5).
Meta supports the bounded tool protocol (M; MI-6). All three are execution gates.

## Adversarial Self-Critique

Filtering after vector search can lose scoped recall: filter before ranking.
Old facts can answer a new date: test revision/time eligibility.
Valid citation IDs can support wrong prose: compare claims to actual gold sources.

## Revision Triggers

Reopen on recall below target, new source-time semantics or changed provider
tool/billing behavior; never lower grounding requirements to pass an evaluation.
