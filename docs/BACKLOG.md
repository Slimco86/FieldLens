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
host activation/tool verification is required per assignment. Backend editing
worked for initial implementation but is missing again in the repair worker;
QA browser/test tools worked. The first foundation worktree
was created after the owner's October 28 implementation approval. It is now
inactive and preserved; the serial-checkout allocation below supersedes it.
The foundation implementation is in candidate `3c1d2b2`, not yet accepted or merged.

The confirmed workflow [architecture](ARCHITECTURE.md), [feature specs](specs/README.md)
and [32-task execution plan](../plan/architecture-fieldlens-1.md) define the
implementation baseline. The [first detailed packets](../plan/feature-foundation-workspace-1.md)
were integrated in `9d630e3` and approved for implementation by the owner at
11:19 EDT on October 28. The backend editing-tool blocker recurred during repair;
the foundation has not completed its independent acceptance/repair cycle.
The task plan's explicit **Depends on** column is the scheduling DAG;
parent dependencies below describe complete-feature prerequisites, not permission
to block every independent sub-slice. Documentation links do not imply approval.

## Work items

**Current planning authority (October 28):** the owner selected F-12/F-14/F-5,
accepted evidence-safe generic F-12 equipment and visible discrepancies, and
confirmed hybrid categories, explicit reconstruction/review/publication and
128 MiB/file, 512 MiB/batch, 200-file limits. G0 workflow/cohort choices are resolved.
The first three detailed packets are approved and committed; DA-7 remains a
per-assignment check rather than a current backend tool blocker.
At 14:47 EDT the owner approved one feature at a time on its own branch in
`/home/slimco/code/FieldLens`, with subagents launched from the main session.
No new worktrees or concurrent writers; model/tool preflight is still required.
G1 remains engineering/manifest qualification, not a requirement to find F-12's
missing tally before writing a project form. Foundation implementation has run;
no paid Meta call has started. Owner clarification at 17:12 EDT requires a
different agent to test every logical feature, re-verify fixes and complete the
authorized commit/merge cycle before the next feature.
The planning package was integrated by the owner in `9d630e3`, version 0.3.3.
Historical checkpoint text below records earlier states; this notice and the
current table supersede its access/design holds.

| ID | Outcome / scope | Status | Prerequisites | Spec / next action |
|---|---|---|---|---|
| FL-000 | Adopt perforation requirements and versioned parallel-development governance | done | None | Integrated by owner in `e8b156a`, version 0.1.0; verification below |
| FL-001 | Agree custom development-agent roles, serial branch delegation and resource boundaries | blocked | FL-000 | Base configuration integrated in `35ed5d2`, version 0.2.0. Backend editing worked once but is missing again during repair despite actual Sonnet/medium selection. QA tools worked. Resolve DA-7 or obtain an explicit temporary routing exception; governance amendments await integration |
| FL-002 | Approve compact demo data/rights manifest, including dated perforation/state evidence | in_progress | None | Owner selected F-12/F-14/F-5 and accepted generic/unlocated F-12 limitations. [Data spec](specs/DATA_FEASIBILITY.md): final hashed profiles/windows/reference/state/rights fixtures remain TASK-002/029; G1 not passed. No automatic F-11 B replacement or further tally-search blocker |
| FL-003 | Verify Meta entitlement/protocols and agree shared budget controls | specifying | FL-004 | [Meta spec](specs/META_INTEGRATION.md): offline adapter/ledger then separate opt-in live smoke; no G1 dependency |
| FL-004 | Establish runnable stack, database/migrations and common identity/evidence/time contracts | testing | FL-014 | Owner authorized direct repairs without further subagents after the tool regression. D1-D11/B1 fixes pass 124 backend, 4 UI and 3 CLI E2E tests; see [verification](specs/FOUNDATION.md#direct-repair-verification-october-28). Acceptance/integration decision remains open; no independent re-verification claimed |
| FL-005 | Upload project sources into traceable, persistent, restart-safe source revisions | specifying | FL-004, FL-002 | [Ingestion](specs/INGESTION.md): TASK-025 workspace precedes upload; early native evidence, selected scanned/Word profiles, then final manifest acceptance |
| FL-006 | Inspect published-model trajectories with evidence and deterministic closest approach | specifying | FL-005, FL-016 | [Trajectory/viewer](specs/TRAJECTORY_VIEWER.md): independent numeric engine, then reconstructed model scene |
| FL-007 | Reconstruct equipment with catalog/generic fallbacks and source-aware placement | specifying | FL-006 | [Equipment](specs/EQUIPMENT_RECONSTRUCTION.md): procedural installed-evidence slice; optional Blender later; DF-9 still required |
| FL-008 | Inspect dated perforation intervals, state transitions and total/open perforated length | specifying | FL-005, FL-006 | [History](specs/PERFORATION_HISTORY.md): foundation-only engine, then real event/scene integration |
| FL-009 | Display aligned terrain/bathymetry and reservoir/formation context | specifying | FL-006 | [Context](specs/CONTEXT_LAYERS.md): independent seabed and formation slices; both mandatory |
| FL-010 | Link production and depth logs to asset/time selection and perforation overlays | specifying | FL-005, FL-016, FL-008 | [Charts](specs/LINKED_CHARTS.md): production/log views need model context, not finished 3D; overlays follow history |
| FL-011 | Deliver early source chat, then evidence-backed model/graph/tool exploration | specifying | FL-003, FL-005, FL-006, FL-007, FL-008, FL-010, FL-016 | [Retrieval/assistant](specs/RETRIEVAL_ASSISTANT.md): TASK-011/019/027 source chat precedes reconstruction/3D; full domain tools and 32-case evaluation follow |
| FL-012 | Verify complete fresh-upload -> scene/history -> charts -> cited-answer demo | specifying | FL-002, FL-009, FL-011 | [Demo acceptance](specs/DEMO_ACCEPTANCE.md): offline combined checks, real/live verification, then authorized release/recording |
| FL-013 | Curate offline Blender equipment-authoring skill and export handoff | done | None | Integrated by owner in `88b177e`, version 0.3.0; skill/workflow only, installation and asset creation deferred |
| FL-014 | Finalize project-centric architecture, primary reconstruction agent and UI-verifiable orchestration plan | done | None for planning | Owner integrated the 32-task DAG/specifications/first packets in `9d630e3`, version 0.3.3, and authorized first-packet implementation October 28. Document checks recorded below; no application verification implied |
| FL-015 | Create/reopen isolated projects with categorized, incremental sources | blocked | FL-004 | [Workspace packet](../plan/feature-foundation-workspace-1.md) approved; resume ready for TASK-025 after foundation integration. TASK-006 completes upload-related PW criteria |
| FL-016 | Reconstruct composite entities/relationships/configurations with evidence and reviewed model publication | specifying | FL-004 | [Reconstruction](specs/ASSET_RECONSTRUCTION.md): review policy confirmed; TASK-026 consumes early chat and TASK-032 issues, not full FL-011. Gold fixtures/live allowance remain separate gates |
| FL-017 | Inspect source-linked warnings/errors and the exact effect of missing/conflicting data | specifying | FL-004, FL-005 | [Data quality](specs/DATA_QUALITY.md): TASK-032 source-first issue inspector; FL-016/007 wire publication/generic boundaries; TASK-022 verifies all DQ criteria. No manual override/fact editor or new telemetry service |

**Scheduling gate for implementation across all rows:** FL-001 agent configuration
must be integrated and the selected profile/model/tools verified in the host;
the workflow's resource allocation must also be ready before implementation
delegation. Main-agent planning/specification and source inspection can proceed
before that gate; FL-002/FL-003 do not depend on each other.

### Finalized priorities and next dispatch

| Priority / checkpoint | Tasks | Dispatch condition / owner verification |
|---|---|---|
| P0: first persisted UI | TASK-001 -> TASK-003 -> TASK-025 -> TASK-006 | Approved packets integrated; restore/verify worker editing tools, then foundation -> projects -> uploads; owner browser checkpoint A before broadening |
| P0: independent evidence qualification | TASK-002 | Main-agent bounded source work or separately verified ingestion assignment; no fabricated G1 completion |
| P0: early agent risk | TASK-004 -> TASK-005; TASK-009/011/019/027 | Offline adapter parallel after foundation; live caps and source subsets separately authorized; checkpoint B before full scene |
| P0: visible quality and reconstruction | TASK-009 -> TASK-032; TASK-019/032 -> TASK-026; TASK-030/028 | Source issues before 3D; reviewed partial model; live reconstruction remains distinct from stubs |
| Required enrichment | TASK-007/008/010/012..018/031 | Numeric engines can start after foundation; remaining tasks follow DAG. History, both charts, seabed and formations are all mandatory |
| Required acceptance/release | TASK-029/020/021/022/023 | Full manifest, live evaluations, combined browser/performance and owner release permission |
| Optional only | TASK-024 | Blender after evidence-backed equipment and explicit asset/setup approval; never blocks required release |

These are priorities, not permission to bypass dependencies. Future packets
freeze their source mappings and exact contracts before dispatch; only the first
three runtime packets have step-by-step handoffs now. Known-command validation
routes to Terra; substantial implementation to the relevant domain specialist.

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
At that checkpoint the documentation handoff candidate was `0.3.2`, patch;
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
early evidence/chat/reconstruction UI checkpoints and 31-task DAG. Integrated by
the owner in `a4bf9ee`, version 0.3.2. No new feature is ready/done, no
implementation branch is assigned, and no paid model call is implied.

Documentation checks passed on October 28: 26 Markdown files, 188 local
links/headings, table/fence structure, 31 unique tasks and six goals with an acyclic
DAG, 17 backlog items with acyclic parent prerequisites, and all 12 project ACs
traced. Early source/chat/reconstruction and chart paths do not wait for 3D;
all mandatory tasks reach release and optional Blender does not block it.
The 18 new PW/RC criteria are binary-testable; these are specification checks,
not executed application tests or evidence of live agent performance.

### Focused target follow-up after the 0.3.2 integration

Owner-requested source inspection resumed on October 28. F-5's embedded Existing
completion table now provides visually checked valve/packer/sealstem/muleshoe
dimensions and MD. The F-12 tally remains unlocated after an expanded bounded
search; F-11 B's genuine final report contains a dimensioned table marked Plan.
Actual perforation records exist for all three proposed targets. F-14's six
initial intervals and F-5's first five match the static table exactly; F-5's
2016 additions and F-12's contradictory 2014 summary show why historical
reconciliation is still required.

Evidence and checks are in the [equipment follow-up](EQUIPMENT_DATA_FEASIBILITY.md#10-target-qualification-and-history-follow-up-october-28)
and ignored hashed audit sidecar. FL-002 remains `in_progress`; neither a complete
third equipment tally nor final G1/owner cohort acceptance is claimed.
Documentation-only handoff candidate: **0.3.3**, pending integration. No runtime
API/schema change, commit, push or application implementation is part of this task.

### Cohort confirmation and implementation-planning handoff

The owner then selected F-12/F-14/F-5, accepted the documented F-12 generic
limitation and requested warning/error visibility. A structured clarification
confirmed hybrid labels, review/publication and upload byte/file limits.
The backlog now includes FL-017, a 32-task DAG and detailed foundation/project/
upload packets with ownership, resource isolation, tests and stop conditions.
No G1/G2/G3/G5 result, active worktree, runtime or live call is implied.
This extends the same unintegrated **0.3.3** documentation patch; do not allocate
another version merely because the planning work spans multiple turns.

Documentation checks passed: 23 Markdown files, 208 local links/headings, table/
fence structure, the acyclic 32-task/18-item graphs, all 12 project acceptance
rows, DQ-1..8/EQ-7 traceability and 19 initial packet steps. All mandatory tasks
reach the release gate; optional Blender is not a prerequisite. Early project/
upload work is independent of final G1 and live Meta checks. Whitespace validation
passed. These are document checks, not application, parser or provider tests.

### First-packet execution approval and activation blocker

The owner authorized the first three implementation handoffs on October 28 at
11:19 EDT. Approved specification base:
`9d630e32af898cdc9292451b5258f9c2f9a1a06d` (owner-integrated 0.3.3).

- Foundation branch: `feature/fl-004-a-foundation`.
- Worktree: `/home/slimco/code/FieldLens-worktrees/fl-004-a-foundation`;
  created at the exact approved base and verified clean after activation.
- Reserved lane: API `8101`, Vite `5174`, DB service `127.0.0.1:55432`.
  Ports were free; no application/database service was started. Planned database
  `fieldlens_fl004a_w1` and task-scoped roles are not yet provisioned.
- Host checks: Python 3.12 via uv 0.11.20; Node 20.11.1/npm 10.2.4.
  Node 24 remains approved user-managed foundation setup, not an installed runtime.
  Docker client 26.1.3/server 29.8.2 and Compose 5.6.0 respond.
  Host reports 7.6 GiB RAM and 162 GiB filesystem space available.
- Runtime evidence confirms main `gpt-6-astra/xhigh` and both activation calls
  `claude-sonnet-5.5/medium`; the required profile is discovered.
- **DA-7 BLOCKED:** the backend worker cannot access `apply_patch`, `create` or
  `edit`. Its focused tool search found no general file editor. Shell-write
  workarounds and model substitutions were not authorized or attempted.
  No application implementation handoff was issued.
- Initial synchronous activation cannot receive follow-up messages. The narrower
  background capability probe is idle:
  `1bee9e93-5d7f-4f58-a94a-3d2f62a5c4eb`. Resume only after editing tools are exposed;
  verify a create/delete smoke in the assigned worktree before authorizing code.
- SDK-reported development usage: initial probe 75,359 total tokens / 3 tool calls;
  focused probe 73,796 / 1. These aggregate counts are not billed-cost estimates;
  no cache/billing breakdown was captured. Meta application calls/spend: none.

The owner/host must restore worker file-edit capabilities. Keep the clean worktree;
do not fan out more workers or mark TASK-001/003 complete. Projects/uploads remain
dependent on verified foundation integration. No credentials or attached secret
snapshot were read.

Read-only diagnosis after the owner's follow-up: Astra is this main orchestration
chat, not an implementation worker. Both worker probes used Sonnet. A Git worktree
does not create another WSL installation or Copilot/MCP environment. Parent and
worker tool search used the same client tool registry (247 available client tools);
MCP/extension tools were discovered, so this is not a blanket loss of all tools.
The backend profile has no `tools` restriction, host `modelCapabilityOverrides`
is empty, and the installed host's default native-tool allowlist includes
`create`, `edit` and `apply_patch`. Runtime version: `1.0.23-preview.5`.
The observed failure is therefore at worker editing-tool exposure, not missing
worktree packages or a verified user-disabled editor. The exact SDK registration/
model-filtering cause is not yet isolated. No host configuration was changed;
adding arbitrary profile allowlists or switching implementation to Astra is not
an established fix.

At the owner's 12:03 EDT request, explicitly declared
`tools: ["*", "edit", "create", "apply_patch"]` in the backend profile in both
checkouts. The wildcard preserves the intended complete tool set. A fresh task
invocation (`explicit-tools-smoke`, Sonnet 5.5/medium) still had no file editors,
but the decisive host record at 16:04:57 UTC reported `tools: null`, not the
updated declaration. Therefore this invocation did not validate the explicit
configuration; stale/unrefreshed profile configuration remains a concrete blocker.
The experimental declaration is retained for a fresh-session test. The worktree
now has only that intentional profile edit; no smoke file/application code exists.
Probe usage: SDK-reported 36,137 total tokens, zero tool calls.

Quick upstream checks found [agent hot-reload issue 3106](https://github.com/github/copilot-cli/issues/3106),
[child MCP scoping issue 5191](https://github.com/github/copilot-cli/issues/5191)
and [built-in-tool regression 5243](https://github.com/github/copilot-cli/issues/5243).
The latter names SDK 1.0.23-preview.5, but its same-turn exit-plan condition does
not match this probe; none proves the precise underlying editing defect here.
Next: fresh Copilot conversation, confirm the explicit list in host metadata,
then repeat the bounded editing smoke. Do not equate another cached invocation
with a valid explicit-configuration test.

### Fresh-session restart attempt, October 28

The owner requested resuming the handoff in a fresh conversation at 13:06 EDT.
One bounded `fieldlens-backend` preflight (`foundation-restart-preflight`) ran
against the existing foundation worktree; no implementation was dispatched.

- Host events confirm `claude-sonnet-5.5/medium`, selected from the agent
  definition default. The worker executed `bash` and tool search; this is not
  a loss of all tools. Its `view` call required a narrower range, so the worker
  did not complete reading the worker contract.
- The worker still reported no `apply_patch`, `create` or `edit`. One focused
  search found no general plain-text editor. The create/read/delete smoke was
  not run; no smoke file was created and no shell-write workaround was used.
- The explicit tool declaration remains in both checkouts. The inspected
  fresh-session configuration event records model/effort but no tool list, so
  activation of that declaration remains unverified, not proven fixed.
- Parent verification confirmed branch `feature/fl-004-a-foundation`, approved
  HEAD `9d630e32af898cdc9292451b5258f9c2f9a1a06d`, only the existing backend-profile
  modification, and absence of the smoke file. All primary-worktree changes
  from the previous session were preserved.
- The new session's start event records `gpt-6-astra/medium`, not the required
  `xhigh`. The earlier session's Astra/xhigh evidence does not establish this
  session's configuration; reconfirm the main-session selection before dispatch.
- Probe usage: SDK-reported 75,378 total tokens, 3 tool calls, 10,106 ms.
  No monetary cost or cache breakdown is inferred. No installs, services,
  application code, commits or Meta calls were made.

DA-7 and FL-004 remain blocked. Next: restore actual worker editing-tool exposure,
confirm the required main-session effort and effective worker tool configuration,
then complete one bounded create/read/delete smoke and the worker-contract read
before dispatching the approved foundation packet. Do not repeat unchanged
probes or start dependent project/upload workers.

### Owner-approved serial checkout handoff, October 28

At 14:47 EDT the owner replaced parallel worktree execution with one feature at
a time, each on its own branch, using subagents launched from the main
orchestrator session. This is an approved scheduling amendment, not evidence
that changing checkout location fixes host tool exposure.

- Active checkout: `/home/slimco/code/FieldLens`.
- Active branch: `feature/fl-004-a-foundation-serial`, created from
  `9d630e32af898cdc9292451b5258f9c2f9a1a06d`; integration target remains `master`.
- The existing `/home/slimco/code/FieldLens-worktrees/fl-004-a-foundation`
  allocation is inactive and preserved, including its profile edit. No removal,
  reset, stash or forced branch reuse is authorized.
- All eight pre-existing modified files were preserved on the new branch.
  The backend profile now declares `[vscode, execute, read, edit, search, web]`;
  this owner-supplied setting is preserved, not treated as verified tool exposure.
- One active writer, including the orchestrator; no branch switches while
  workers/checks/helpers are running. No worker edits global release/backlog
  metadata or another checkout. Keep task-scoped databases, ports and output roots.
- Approved order remains foundation -> project lifecycle -> uploads/jobs, with
  integration and acceptance gates between features. Independent DAG tasks are
  queued, not additional parallel workers.
- The governing workflow, agent contract and implementation packets now reflect
  this amendment. Changes are pending, not committed/integrated; no final version
  or foundation acceptance result is claimed.
- Next: one bounded same-checkout backend editing smoke, verify actual
  model/effort/tools, then dispatch only if DA-7 and the foundation prerequisites
  pass. On failure retain the allocation and report the exact blocker.

Serial preflight result at 14:50 EDT: **DA-7 still blocked**. Host metadata
confirms main `gpt-6-astra/xhigh` at 14:47 and worker `claude-sonnet-5.5/medium`
from its profile default. The worker successfully read the bounded contract and
ran the branch/base/status check in the shared checkout. Its exposed tools
included read/execute/search-by-file, but no plain-text editor or tool-discovery
function. The create/read/delete smoke was therefore not run; no file was created
and no shell-write workaround used. Parent verification confirmed unchanged dirty
paths, absent smoke file and untouched legacy-worktree profile modification.
Changing checkout location did not restore editing capability in this probe.

Probe usage: SDK-reported 18,112 total tokens, 2 tool calls, 11,111 ms; no billed
cost estimate or Meta application usage. Documentation checks passed:
`git diff --check`, 192 local file links across 16 changed Markdown files,
11 profile required-header/body-size checks, and a targeted scan for obsolete
parallel-dispatch directives. These are not application or full YAML/schema tests.
No implementation, commit, version bump or service startup was performed.
Next: owner decision on an explicit patch-return handoff (worker authors changes,
orchestrator applies them with its editor) versus pausing until worker tools are
repaired. That alternative is not yet approved and does not silently waive DA-7.

The owner questioned patch-return token overhead and requested configuration
diagnosis instead; patch-return remains unapproved. Read-only inspection found
no model tool overrides in either WSL or Windows agent-host configuration
(`modelCapabilityOverrides: {}`). The installed host's native allowlist contains
`view`, `bash`, `create`, `edit` and `apply_patch`. Repository-local VS Code
settings and repository Copilot/Claude permission-settings files are absent;
the inspected user settings do not explain the missing editors. The current
backend profile includes the documented Copilot `edit` alias. This narrows the
unresolved failure to effective tool exposure rather than proving a filesystem
or worktree-permission issue; runtime/model-specific filtering remains a
hypothesis, not an established root cause. No settings or permissions were changed.

### Foundation implementation and independent acceptance

- Recreated `fieldlens-backend` without an explicit tools list: runtime exposed
  create/edit/discovery and implementation writes succeeded. Host events confirm
  Sonnet 5.5/medium on the recreated-profile probe and implementation launch.
  Global `ai-team-dev` and local `fieldlens-task` comparisons also exposed editing
  tools. Stale profile caching is a hypothesis, not a proven root cause.
- Main-session model switched to Sonnet/medium for diagnosis/initial dispatch;
  host metadata confirms return to Astra/xhigh at 16:59 and 17:12 EDT.
- Implementation candidate is `3c1d2b285fc8588d32407977d4f27bf921f0d51f` on
  `feature/fl-004-a-foundation-serial`; master remains `9d630e3`.
  Worker-reported checks and main-agent exploratory checks are not independent
  acceptance. The original handoff omitted required documentation and did not
  complete the delivery cycle.
- Independent `fieldlens-qa` invocation `79267169-ed0c-402f-9867-025fbdb90fe3`
  used host-confirmed Sonnet 5.5/medium and a clean frozen candidate. Verdict:
  **FAIL**. Existing 84 backend and 3 UI tests, lint/type/build/contracts and
  independent real migration/readiness/Retry checks passed; SC-2/SC-5 and required
  documentation failed, with further boundary/focus/version defects. The full
  [remediation list](specs/FOUNDATION.md#independent-qa-and-bounded-repair-allocation)
  owns D1-D11/B1. No feature or checkpoint is marked verified.
- Native Playwright browser installation returned explicit Ubuntu 20.04 support
  errors on two attempts. VS Code integrated-browser checks work. Repair the
  required CLI gate with the version-matched, test-only browser container;
  do not call either route equivalent to an unrun test.
- QA left the candidate clean, stopped its helper APIs/Vite and dropped its
  test databases. The owner preview remains on 8101 with the allocated foundation
  PostgreSQL service on loopback 55432. Stop branch-bound helpers before merge.
- The QA handoff reports 6,963 seconds elapsed, exceeding the requested
  35-minute checkpoint. Future repair/re-verification turns must return at their
  bound; the excess is not an accepted new time allocation. Development usage
  cost is unavailable here; no Meta application spend is claimed.
- Next: same backend owner repairs this slice, then the same independent QA
  verifies the new frozen candidate. Finalize one minor version only after gates
  pass, commit/merge into master, verify integration and reconcile this ledger.
  No push, next feature or worktree switch is authorized by a passing subset.
- Schedule: October 28's projects/uploads checkpoint A has not been reached.
  Foundation is a prerequisite, not a substitute; retain the gate and rebaseline
  scheduling after this acceptance cycle rather than claim unmeasured slack.
- Repair worker `05eb0074-fd9b-4bdf-b353-025224b93969` selected backend
  Sonnet 5.5/medium at base `923b1bf`, but exposed neither `apply_patch`, `create`
  nor `edit`. One bounded inventory/discovery follow-up confirmed the absence.
  No application writes, image pulls or tests ran. The original implementation
  handle was no longer available, so this was a fresh same-profile repair worker.
  Tool exposure remains session/invocation-dependent; its root cause is unproven.
  Main stopped the 8101 preview before repair; the foundation DB remains running.
  Current blocker: restore native editors or authorize a temporary known-working
  agent/model route. No fallback or merge has been performed.
- At the owner's request, the backend profile was deleted and recreated without
  a `tools` field, retaining its name/model/effort/body. A fresh invocation still
  exposed no `apply_patch`, `create` or `edit` and stopped before any smoke write.
  Recreating the file is therefore not a reliable unblock in this session.
- Owner then switched the main model and instructed it to fix the foundation
  directly, without any subagents. The main implemented regression tests first:
  29 contract/isolation counterexamples and Retry-focus initially failed.
  Repairs now pass 124 backend, 4 UI and 3 actual Playwright CLI E2E tests plus
  affected checks. No new subagent was invoked for these repairs.
- Docker Desktop's host network was not WSL loopback. The reproducible browser
  setup now publishes only 127.0.0.1:9323 and tunnels only loopback destinations;
  the Noble image matches Playwright 1.64.1. Native Ubuntu 20.04 installation is
  not retried and integrated-browser success is not substituted for the CLI.
- VERSION is 0.4.0 on the repair candidate; master is still 0.3.3. Required code
  and operational gaps are repaired, but the main's direct checks are not a
  separate-agent PASS. Resolve the acceptance exception before merge; do not
  invent an independent verdict or mark the feature done early.

Add a record when scheduling, not speculative branches or fake test results:

```text
ID / approved spec / scope:
Status / blocked reason / resume state:
Prerequisite IDs and integrated hashes:
Configured agent / base commit / branch / absolute checkout:
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
