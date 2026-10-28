# FieldLens backlog

Updated 2026-10-28. Main-agent-owned, persistent work ledger.
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

The revised draft [architecture](ARCHITECTURE.md), [feature specs](specs/README.md)
and [31-task execution plan](../plan/architecture-fieldlens-1.md) are ready for
review. The task plan's explicit **Depends on** column is the scheduling DAG;
parent dependencies below describe complete-feature prerequisites, not permission
to block every independent sub-slice. Documentation links do not imply approval.

## Work items

**Current planning authority (October 28):** the owner deferred the remaining
data follow-up and resumed requirements 2-5. Planning is unblocked; implementation
is not. Hybrid categories, explicit bounded runs, review-before-publication and
new upload limits are draft defaults because the owner was unavailable to answer
the clarification. G0 approval is required before dispatch.
Historical checkpoint text below records earlier states; this notice and the
current table supersede its access/design holds.

| ID | Outcome / scope | Status | Prerequisites | Spec / next action |
|---|---|---|---|---|
| FL-000 | Adopt perforation requirements and versioned parallel-development governance | done | None | Integrated by owner in `e8b156a`, version 0.1.0; verification below |
| FL-001 | Agree custom development-agent roles, worktree delegation and resource boundaries | testing | FL-000 | Configuration integrated in `35ed5d2`, version 0.2.0; [DA-7 host activation](specs/DEVELOPMENT_AGENTS.md) still needs evidence before feature delegation |
| FL-002 | Approve compact demo data/rights manifest, including dated perforation/state evidence | in_progress | None | [Local data audit](VOLVE_DATA_DISCOVERY.md#8-owner-supplied-local-data-content-audit): owner supplied 33,678 files and all 33 candidates are present. Surveys, depth surfaces, logs, production and selected original history inspected. Equipment attribution/extraction, historical/reference reconciliation and owner-approved manifest remain open; not integrated or G1-passed |
| FL-003 | Verify Meta entitlement/protocols and agree shared budget controls | specifying | FL-004 | [Meta spec](specs/META_INTEGRATION.md): offline adapter/ledger then separate opt-in live smoke; no G1 dependency |
| FL-004 | Establish runnable stack, database/migrations and common identity/evidence/time contracts | specifying | FL-014 | [Foundation](specs/FOUNDATION.md), [contracts](specs/SHARED_CONTRACTS.md); no pilot/provider prerequisite for synthetic foundation |
| FL-005 | Upload project sources into traceable, persistent, restart-safe source revisions | specifying | FL-004, FL-002 | [Ingestion](specs/INGESTION.md): TASK-025 workspace precedes upload; early native evidence, selected scanned/Word profiles, then final manifest acceptance |
| FL-006 | Inspect published-model trajectories with evidence and deterministic closest approach | specifying | FL-005, FL-016 | [Trajectory/viewer](specs/TRAJECTORY_VIEWER.md): independent numeric engine, then reconstructed model scene |
| FL-007 | Reconstruct equipment with catalog/generic fallbacks and source-aware placement | specifying | FL-006 | [Equipment](specs/EQUIPMENT_RECONSTRUCTION.md): procedural installed-evidence slice; optional Blender later; DF-9 still required |
| FL-008 | Inspect dated perforation intervals, state transitions and total/open perforated length | specifying | FL-005, FL-006 | [History](specs/PERFORATION_HISTORY.md): foundation-only engine, then real event/scene integration |
| FL-009 | Display aligned terrain/bathymetry and reservoir/formation context | specifying | FL-006 | [Context](specs/CONTEXT_LAYERS.md): independent seabed and formation slices; both mandatory |
| FL-010 | Link production and depth logs to asset/time selection and perforation overlays | specifying | FL-005, FL-016, FL-008 | [Charts](specs/LINKED_CHARTS.md): production/log views need model context, not finished 3D; overlays follow history |
| FL-011 | Deliver early source chat, then evidence-backed model/graph/tool exploration | specifying | FL-003, FL-005, FL-006, FL-007, FL-008, FL-010, FL-016 | [Retrieval/assistant](specs/RETRIEVAL_ASSISTANT.md): TASK-011/019/027 source chat precedes reconstruction/3D; full domain tools and 32-case evaluation follow |
| FL-012 | Verify complete fresh-upload -> scene/history -> charts -> cited-answer demo | specifying | FL-002, FL-009, FL-011 | [Demo acceptance](specs/DEMO_ACCEPTANCE.md): offline combined checks, real/live verification, then authorized release/recording |
| FL-013 | Curate offline Blender equipment-authoring skill and export handoff | done | None | Integrated by owner in `88b177e`, version 0.3.0; skill/workflow only, installation and asset creation deferred |
| FL-014 | Finalize project-centric architecture, primary reconstruction agent and UI-verifiable orchestration plan | specifying | None for planning | Initial package integrated in `4ae7f7b`; October 28 revised [architecture](ARCHITECTURE.md), [specs](specs/README.md) and [plan](../plan/architecture-fieldlens-1.md) drafted for G0 review. Final data acceptance remains FL-002, not a planning blocker |
| FL-015 | Create/reopen isolated projects with categorized, incremental sources | specifying | FL-004 | [Workspace](specs/PROJECT_WORKSPACE.md): TASK-025 lifecycle first; TASK-006 upload integration completes PW criteria. Hybrid labels/limits need approval |
| FL-016 | Reconstruct composite entities/relationships/configurations with evidence and reviewed model publication | specifying | FL-004 | [Reconstruction](specs/ASSET_RECONSTRUCTION.md): TASK-026 consumes early retrieval/chat, not full FL-011; TASK-028 qualifies live behavior. Review defaults/gold fixtures need approval |

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

## Integrated configuration awaiting activation

| Field | FL-001 |
|---|---|
| Owner / executing agent | Project owner / main agent, approved agent-configuration bootstrap |
| Base commit / current branch | `e8b156a8e306bd5af993b9b6108ceea6c8810aaa` / `master` |
| Worktree | Existing primary worktree; no application implementation delegated |
| Approval | Owner approved 10 specialists plus orchestrator; Astra xhigh, Terra low, Sonnet medium, Sol high on 2026-10-27 |
| Integrated version | `0.2.0`, development-agent configuration |
| Required checks | YAML/schema, 11 profiles/model tiers, tool/role boundaries, routing cases, links, version consistency, whitespace and host activation |
| Verification evidence | 2026-10-27: 11 YAML profiles/model tiers/tool boundaries, 12 routing cases, 143 local links, 13 backlog IDs/acyclic dependencies and version metadata passed static checks. VS Code reported no agent-file diagnostics; `git diff --check` passed. Actual model/effort/tool activation not yet run |
| Integrated commit | `35ed5d2`, confirmed on `master` 2026-10-27; committed by owner after the configuration task |
| Next action | Confirm selected-profile/model/effort/tool activation before real delegation; do not mark DA-7 passed from Git evidence alone |

## Completed skill integration record

| Field | FL-013 |
|---|---|
| Owner / executing agent | Project owner / main agent, approved skill configuration only |
| Base commit / current branch | `35ed5d2` / `master` |
| Worktree | Existing primary worktree; owner subsequently committed the skill and approved ignore-rule correction |
| Approval | Owner approved Blender skill/workflow only on 2026-10-27; setup and actual assets deferred |
| Integrated version | `0.3.0`, new offline authoring skill |
| Required checks | BA-1 through BA-4: skill metadata/links, unchanged agent model tiers, authoring/export/failure guidance, scoped changes and release consistency |
| Verification evidence | 2026-10-27: BA-1 through BA-4 metadata/content/scope checks passed; 8 skill headers, 11 unchanged agent model tiers, 2 new routing cases, 158 local links, 14 backlog IDs/dependencies and version records checked. `git diff --check` passed; skill files are Git-visible. No Blender installation/asset/export/render checks performed |
| Integrated commit | `88b177e`, confirmed on `master` 2026-10-27; committed by owner after the skill task |
| Next action | None for FL-013; choose/pin Blender and run real export/consumer checks only in a separately approved asset task |

FL-013 is preparation-only and does not depend on running Blender or activating
FL-001. Actual asset execution uses the normal scheduling gate and an approved
FL-007 equipment slice; this skill does not silently add a Blender dependency to
all equipment reconstruction.

## Data-first planning checkpoint

**Owner hold, 2026-10-27:** do not advance architecture/specification changes or
application implementation until all essential data for the intended project is
accessible and its required coverage has been checked. Acquisition, access
diagnosis and evidence-coverage verification may continue. This overrides earlier
permission in the plan to advance source-independent slices while G1 is blocked.
Partial mirrored files and metadata inventories do not release this hold.

At the initial discovery checkpoint, FL-002/FL-014 were both blocked. Discovery inspected public documentation,
license clauses, SODIR identities and a checksum-verified metadata catalog. The
expanded 33-file pilot candidate list has no acquired pilot bytes/hashes. No application
tests or provider calls were produced. The later architecture package below
completes FL-014's document deliverables without claiming pilot acceptance.

Owner confirms no prepared data, indie/public-repo/three-minute-video requirements,
local WSL/container execution, and a ready Meta key with public-data processing
permission. Official sample access requires owner action; no account, terms
acceptance, cloud resources or paid model usage were initiated. Proposed cohort
and acquisition limits remain unapproved. The owner subsequently signed in; the
installed catalog exposes only `information_schema`, while the advertised volume
returns missing-schema 404. Provider details return ownership 403. No upgrade,
reinstall or access-policy change was attempted.

The equipment follow-up inspected 3 public mirrored WITSML files (7,776 bytes),
8 components and 4 bore sections. Dimensions are present, but drilling assembly
labels, missing installation context and unresolved MD/TVD references prevent
using them as verified pilot completion state. The report adds EDM/WITSML priority
and proposed DF-9; FL-002 is not closed by this structural sample check.
Further public-source searches found secondary report extracts, not the missing
original completion PDF. A downstream "Completion Report" label conflicts with
its drilling-report header. The equipment-source assessment is complete with a
conditional verdict; source access and pilot acceptance remain blocked. The
report records the privileged catalog/share checks needed without assuming a
paid upgrade or changing permissions.

Initial static checks passed: 22 unique candidate paths matched catalog file rows; unknown
bytes/hashes remain blank; 86 local documentation links, 15 unique backlog IDs
with acyclic prerequisites, candidate version agreement and `git diff --check`.
After the equipment follow-up, checks passed for 33 exact candidate paths,
95 local links, all 15 backlog IDs/dependencies, DF-1 through DF-9, version
agreement, the three source hashes and `git diff --check`.

Documentation handoff candidate: `0.3.1` (patch; no API/schema behavior change).
Subsequently integrated by the owner in `4ae7f7b`; the data audit remains blocked.

## Historical architecture package handoff (October 27)

FL-014 now has a selected modular-monolith stack/process model, typed shared
contracts, complete feature specifications, requirement-to-test traceability,
24 explicit scheduled tasks and bounded parallel worktree/resource assignments.
Design documents are complete, while package/runtime, pilot and live-model
qualification remain future execution tests. No application code or feature
approval is inferred.

The plan removes the unnecessary full-data/full-provider prerequisite from
foundation and synthetic engineering/history/adapter slices. Native pilot import
and full-demo acceptance still require real evidence. Source-first inspection
findings inform the architecture rather than becoming fabricated source mappings.

The owner integrated this initial package in `4ae7f7b`, then reopened its
requirements. FL-014 is now `blocked` on the owner's essential-data gate: address data acquisition,
project/categorized uploads, composite-asset reconstruction, the Meta harness and
UI-verifiable increments one by one. The old DAG is not authorization to start
implementation before those design changes are agreed.

Documentation validation on 2026-10-27 passed: 185 local Markdown links;
24 unique tasks with an acyclic dependency graph and six phase goals; 15 valid
acyclic backlog parents; 10 new feature/API spec structures with 84 unique
acceptance criteria across the new and retained data/history specs; all 10 project
ACs traced; independent source-free lanes and optional-asset exclusion checked.
All 13 new design documents passed table/fence/whitespace checks; fixture arithmetic,
EST deadline offset, pending version consistency and `git diff --check` passed.
This validates the documents, not the planned application tests.

## Historical acquisition follow-up and architecture reconsideration

The pinned public production workbook and daily-report conversion are now local,
outside Git, with hashes and source provenance. The workbook has 15,634 daily
rows across seven labels. The report corpus has 1,759 unique records, including
402 under F-12/F-14/F-5. Selected records show production-completion operations
and actual perforation firing; they also demonstrate an F-14 report discussing
F-12 equipment. Cross-document subject attribution is therefore a real source
requirement, not just a hypothetical architecture concern.

These findings narrow the source gap but do not close FL-002: original access,
full geometry, units/datum reconciliation, complete history and sample approval
remain open. Points 2-5 of the owner's reconsideration are not yet resolved.
Current documentation handoff candidate: `0.3.2`, patch, pending integration;
no application implementation, paid API call or accepted pilot is claimed.

Further acquisition added four mirrored F-5 actual-trajectory section XMLs and
their mapping file (542,300 bytes). Hash/unit/station checks passed, but overlapping
samples differ and physical references remain unverified. Verified acquired files
and provenance now have durable copies under Git-ignored `data/volve/source-audit/`;
session originals were preserved. The current listing's 90-day installation
policy and the May 27 installation make expired access a concrete hypothesis.
No authorization to reinstall was received and no account changes were made.
The [essential-data coverage table](VOLVE_DATA_DISCOVERY.md#7-f-5-trajectory-acquisition-and-essential-data-coverage)
remains incomplete; neither FL-002 nor the owner hold is released.

The subsequent October 27 recovery attempt is also blocked at browser login:
the existing workspace displays "Signed in to a different account", including
when its original workspace-scoped URL is used. Correct-account sign-in is now
a prerequisite to testing the expiry hypothesis; reinstall authorization still
has not been received. No account or catalog modification was performed.

### Owner-supplied local dataset: superseding access checkpoint

The owner subsequently shared a working volume in another workspace and supplied
the local official download. A complete metadata walk found 33,678 files,
48,121,671,122 bytes and all 33 candidates. The [content audit](VOLVE_DATA_DISCOVERY.md#8-owner-supplied-local-data-content-audit)
verified actual survey records, formation/depth surfaces, a seabed block, log
curves, production and original operational evidence. It also found mislabeled
completion documents, undated pilot interval rows and mixed DEPTH/TIME blocks
inside the nominal seabed file. Earlier access/reinstall questions are no longer
the reason for holding local work. FL-002 is `in_progress`, not done; the
engineering manifest and owner acceptance remain open, and FL-014 stays on hold.

The focused completion audit confirms an F-14 AS INSTALLED schematic with actual
safety-valve, PBR and packer OD/length/MD. Its reference/date conflicts are explicit.
The exact remaining F-12 source lead is the **29-01-2008 As Installed completion
tally**, referenced in 2016 plug logs but not located in inspected documents.
F-5's correct completion Word report exists; its embedded schematic images remain
unverified. Do not equate these extraction/qualification tasks with missing
seismic or an inaccessible official release.

## Assignment record for each active feature

October 28 planning handoff: new FL-015/016 specs, source/model context contracts,
early evidence/chat/reconstruction UI checkpoints and 31-task DAG. Candidate
version remains 0.3.2 (one unintegrated documentation patch, no runtime API change).
No new feature is ready/done, no implementation branch is assigned, and no paid
model call or resumed source audit is implied.

Documentation checks passed on October 28: 26 Markdown files, 188 local
links/headings, table/fence structure, 31 unique tasks and six goals with an acyclic
DAG, 17 backlog items with acyclic parent prerequisites, and all 12 project ACs
traced. Early source/chat/reconstruction and chart paths do not wait for 3D;
all mandatory tasks reach release and optional Blender does not block it.
The 18 new PW/RC criteria are binary-testable; these are specification checks,
not executed application tests or evidence of live agent performance.

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
