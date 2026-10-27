# FieldLens backlog

Updated 2026-10-27. Main-agent-owned, persistent work ledger.
See [workflow](DEVELOPMENT_WORKFLOW.md) for gates and
[project scope](PROJECT_SPEC.md) for mandatory requirements.

## Status and ownership

States: `proposed`, `specifying`, `ready`, `in_progress`, `testing`,
`integration_pending`, `done`; exceptional `blocked` / `cancelled`.
`Ready` requires an approved feature spec and satisfied prerequisites. `Done`
requires the integrated commit, version and acceptance evidence, not just coding.
Owner is the project owner for approval; an execution agent is unassigned until
delegated. [Custom profiles](../.github/agents/README.md) are now defined; actual
host activation/model verification is still required. No additional worktrees
have been created by the preparation tasks.

The initial decomposition below is **proposed**, not an implementation schedule.
Dependencies are starting technical prerequisites; refine them into separate
contract-ready slices during specification to expose safe parallel work. Do not
assume list order implies a dependency or that documentation links imply approval.

## Work items

| ID | Outcome / scope | Status | Prerequisites | Spec / next action |
|---|---|---|---|---|
| FL-000 | Adopt perforation requirements and versioned parallel-development governance | done | None | Integrated by owner in `e8b156a`, version 0.1.0; verification below |
| FL-001 | Agree custom development-agent roles, worktree delegation and resource boundaries | integration_pending | FL-000 | [Statically verified configuration](specs/DEVELOPMENT_AGENTS.md); confirm selected-profile host activation and integrate before feature delegation |
| FL-002 | Approve compact demo data/rights manifest, including dated perforation/state evidence | proposed | None | G1/G4; jointly inspect samples and create a feasibility spec |
| FL-003 | Verify Meta entitlement/protocols and agree shared budget controls | proposed | None | G2; create bounded authorized smoke-test spec; no paid calls by default |
| FL-004 | Establish runnable stack, database/migrations and common identity/evidence/time contracts | proposed | FL-002 | G5; approve foundation spec, compatibility choices and actual test commands |
| FL-005 | Upload supported records into traceable, persistent, restart-safe dataset revisions | proposed | FL-004 | Approve ingestion spec and fixtures |
| FL-006 | Reconstruct/inspect real trajectories with evidence and deterministic closest approach | proposed | FL-005 | Approve trajectory/scene spec and independent numerical fixtures |
| FL-007 | Reconstruct equipment with catalog/generic fallbacks and source-aware placement | proposed | FL-006 | Approve equipment spec and targeted enrichment contracts |
| FL-008 | Inspect dated perforation intervals, state transitions and total/open perforated length | specifying | FL-005, FL-006 | [Draft feature spec](specs/PERFORATION_HISTORY.md); audit real event fields, approve mappings/tolerances |
| FL-009 | Display aligned terrain/bathymetry and reservoir/formation context | proposed | FL-006 | Approve contextual-layer spec; all layers remain mandatory |
| FL-010 | Link production and depth logs to asset/time selection and perforation overlays | proposed | FL-006, FL-008 | Approve chart spec; basic charts can become a contract-ready slice before live temporal overlays |
| FL-011 | Deliver evidence-backed hybrid/graph retrieval and Meta tool-driven exploration | proposed | FL-003, FL-005, FL-006, FL-007, FL-008, FL-010 | G3; split retrieval/tool contracts into earlier ready slices; final integration needs real tools |
| FL-012 | Verify complete fresh-upload -> scene/history -> charts -> cited-answer demo | proposed | FL-009, FL-011 | Approve end-to-end acceptance/rehearsal spec and recheck submission rules |

**Scheduling gate for implementation across all rows:** FL-001 agent configuration
must be integrated and the selected profile/model/tools verified in the host;
the workflow's resource allocation must also be ready before implementation
delegation. Main-agent planning/specification and source inspection can proceed
before that gate; FL-002/FL-003 do not depend on each other.

## Completed integration record

| Field | FL-000 |
|---|---|
| Owner / executing agent | Project owner / main agent, documentation-only |
| Base commit / current branch | `2772cff` / `master` |
| Worktree | Existing primary worktree; no feature implementation delegated |
| Integrated version | `0.1.0` initial documentation baseline |
| Required checks | Relative links, backlog ID/dependency integrity, version/changelog consistency, perforated-length example arithmetic, documentation whitespace |
| Verification evidence | 2026-10-27: 94 local Markdown/HTML references checked; 13 unique IDs with valid states/acyclic dependencies; bootstrap version agreement; all 7 synthetic state/length rows and ft/m round trips checked; 7 skill metadata headers unchanged from the previously validated baseline. `git diff --check` passed. No application tests apply |
| Integrated commit | `e8b156a8e306bd5af993b9b6108ceea6c8810aaa`, confirmed on `master` 2026-10-27; committed by owner after the documentation task |
| Next action | None for FL-000; implementation of the documented product features remains separate |

## Active integration record

| Field | FL-001 |
|---|---|
| Owner / executing agent | Project owner / main agent, approved agent-configuration bootstrap |
| Base commit / current branch | `e8b156a8e306bd5af993b9b6108ceea6c8810aaa` / `master` |
| Worktree | Existing primary worktree; no application implementation delegated |
| Approval | Owner approved 10 specialists plus orchestrator; Astra xhigh, Terra low, Sonnet medium, Sol high on 2026-10-27 |
| Candidate version | `0.2.0`, new opt-in development-agent capability, pending integration |
| Required checks | YAML/schema, 11 profiles/model tiers, tool/role boundaries, routing cases, links, version consistency, whitespace and host activation |
| Verification evidence | 2026-10-27: 11 YAML profiles/model tiers/tool boundaries, 12 routing cases, 143 local links, 13 backlog IDs/acyclic dependencies and version metadata passed static checks. VS Code reported no agent-file diagnostics; `git diff --check` passed. Actual model/effort/tool activation not yet run |
| Integrated commit | Pending |
| Next action | Confirm selected-profile activation before real delegation; commit/integrate when authorized and reconcile |

## Assignment record for each active feature

Add a record when scheduling, not speculative branches or fake test results:

```text
ID / approved spec / scope:
Status / blocked reason / resume state:
Prerequisite IDs and integrated hashes:
Configured agent / base commit / branch / absolute worktree:
Complexity-risk rationale / model and effort / actual host-selection evidence:
Owned files and shared contracts:
Database/ports/Compose project / budget reservation:
Acceptance checks and evidence location:
Time/tool/attempt bounds / elapsed time / exposed usage:
Proposed bump / compatibility rationale / release note:
Tested commit / integrated commit / final version:
Next action / cleanup status:
```

Keep cancelled or superseded items with rationale. Newly discovered scope is a
new item or an owner-approved spec revision, not a hidden addition to another
agent's work. Record verified test evidence in the feature spec; link it here.
