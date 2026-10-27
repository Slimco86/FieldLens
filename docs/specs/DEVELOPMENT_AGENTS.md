# Specification: Model-tiered development-agent handoffs

> **Spec type:** Process/workflow. **Backlog:** FL-001.
> **Load-bearing:** F3 scope, F4 executor context, F6 ambiguity.
> **Supporting:** F1 outcome, F2 acceptance, F5 failure conditions.
> **Date:** 2026-10-27. **Decision owner:** Project owner.
> **Status:** Base configuration integrated; host activation pending.
> **Extension:** FL-013 Blender skill/workflow statically verified; integration pending.
> **Approval:** Owner confirmed 10 specialists plus orchestrator and effort defaults
> in the 2026-10-27 preparation conversation.
> **Zero-Question Score:** 0 unowned questions; host activation remains a verification gate.

## How to Read This Spec

Owner: outcome, boundaries and tensions. Orchestrator: routing, acceptance and
activation. Implementer/tester: role boundaries, assignment and evidence.

## Notation Key

`[Validated]` means owner-approved or documentation-backed, not a runtime test.
`[Assumed: verify]` requires the named check; `[Unknown: TBD]` names its owner and
deadline. H/M/L express confidence, not benchmark scores. AC score 3 is binary.

## 1. Outcome Statement

The orchestrator can select a bounded specialist and explicit model tier for each
approved handoff without defaulting every task to Astra or letting workers become
uncontrolled orchestrators.

Verification: inspect 11 discoverable profiles, exercise the routing cases and
confirm the selected role/model/effort in the host before a real assignment.
Outcome score: 3; static configuration alone does not prove runtime selection.

## 2. Scope

### IN Scope

- One main profile and ten specialists in `.github/agents/`, with role descriptions,
  default model/effort and explicit scope. `[Validated: owner approval]`
- Terra low for exact, low-risk tasks; Sonnet medium for domain implementation and
  quality work; Sol high for bounded plan repair; Astra xhigh for main orchestration.
  `[Validated: owner approval; capability/cost assumptions are not benchmarks]`
- Shared routing/preflight/handoff policy, relevant existing skills, no nested
  worker delegation and dependency/resource isolation. `[Validated: owner/workflow]`
- Reconcile FL-000 against actual commit `e8b156a`; propose a new version for this
  opt-in developer capability, without claiming a merge. `[Validated: Git evidence]`
- FL-013 adds an offline Blender equipment-authoring skill to the existing 3D role,
  not a new worker or runtime dependency. Installation and real asset creation
  are explicitly deferred. `[Validated: owner follow-up approval, 2026-10-27]`

### OUT of Scope

- Application code, runtime RAG agent frameworks, model-provider deployment and
  new MCP services: these profiles customize development, not the product runtime.
- Changing the active chat model or personal VS Code settings: select/verify the
  main profile in the host; a repository edit cannot prove a session switched.
- Automatic model fallback, price claims, paid Meta smoke calls or blanket worker
  fan-out: not authorized by this configuration task.
- Automatic commits, worktree creation, pushes or releases: actual feature work
  still needs an approved assignment and integration.

### Scope Dependencies

FL-000 is integrated as documentation baseline 0.1.0 in `e8b156a`. Host agent
discovery/model entitlement is a gate before using any new profile, not a reason
to fabricate a successful invocation. Existing feature specs remain unapproved
where they were unapproved before this task.

### Open Scope Tensions

Smaller models save resources only when they can complete the assignment correctly.
Route uncertainty and engineering risk upward rather than lowering acceptance.

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation / check |
|---|---|---|---|---|
| DA-1 | Behavioral | Exactly one orchestrator and ten named specialist profiles exist; each has nonempty name/description/body, valid YAML, explicit model/effort and no unresolved placeholders. | 3 | [Validated: owner roster]; static parser |
| DA-2 | Behavioral | All model/effort pairs match the approved four tiers; only the orchestrator is user-invocable, and worker profiles prohibit child delegation. | 3 | [Validated: owner]; metadata/body checks |
| DA-3 | Behavioral | Routing cases distinguish known tests from QA design, boilerplate from interconnected implementation, and plan gaps from code execution; no case defaults to Astra as a worker. | 3 | [Validated: owner]; routing-table check |
| DA-4 | Negative | Research and plan repair expose no edit/execute tools, workers cannot own global release metadata, and no profile permits inferred engineering facts, unauthorized data transmission or default paid Meta tests. | 3 | [Validated: project policy]; scope/tool review |
| DA-5 | Edge case | Missing profile/model/effort, wrong worktree, unapproved contract or unavailable required tool blocks the assignment; no silent fallback or continuation under an unverified model. | 3 | [Validated: owner/workflow]; preflight scenario review |
| DA-6 | Non-behavioral | No worker body exceeds 6,000 characters, shared policy is linked rather than copied wholesale, and assignments record bounds and usage when available (otherwise explicitly unavailable). | 3 | [Validated: approved cost-conscious setup]; static bounds and handoff check |
| DA-7 | Dependency | Before feature delegation, host discovery resolves the chosen profile and runtime metadata confirms its model/effort; required tool access is checked. Static validation, self-reported model names and documentation are not substitutes. | 3 | [Unknown: orchestrator at first activation]; host smoke/trace |

Definition of done: DA-1 through DA-6 pass, DA-7 is recorded for activation, and
integration is confirmed. Configuration can be ready for owner review while
activation is pending; do not mark the implementation scheduling gate open then.

## 4. Context and Decisions

- Executor: main agent configuring project instructions, then isolated development
  workers with no assumed chat history. Owner resolves scope; orchestrator owns
  contracts, resources, validation and release allocation.
- **Role** means expertise/ownership; **tier** means model/effort. A small frontend
  boilerplate change can use the task worker plus the frontend skill rather than
  creating a duplicate low-tier frontend persona.
- **Plan repair** returns a bounded missing-contract/dependency proposal; it does
  not approve scope, replace global architecture or implement speculative code.
- Profiles use Copilot model IDs requested/available in this session:
  `gpt-6-astra`, `gpt-6.1-terra`, `claude-sonnet-5.5`, `gpt-6.1-sol`.
  `[Validated: owner/session catalog; actual profile resolution untested]`
- `model`, `reasoning-effort`, visibility and tool fields follow the
  [VS Code custom-agent reference](https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference).
  `agents` restrictions have harness-specific semantics; enforce the no-child
  rule in worker instructions too. No claim of filesystem/process sandboxing.
  `[Validated: official reference checked 2026-10-27]`
- Keep the approved Python/React/PostgreSQL/Meta stack and historical engineering
  truth rules. Development-model usage is distinct from the shared USD 150 Meta
  application budget. Do not invent token prices or provider balances.

## 5. Failure Conditions

| Type | Deviation signal | Action |
|---|---|---|
| Host/configuration | Profile omitted, model rejected, effort ignored or tools absent | Stop activation; report the host error and request an explicit mapping/configuration fix |
| Process | Worker needs unowned files, another worker, an undefined contract or unsafe shared resources | Return blocker to the orchestrator; preserve worktree and tests |
| Evidence | Research cannot verify a claim, parser loses locators or geometry lacks references | Report missing/contradictory evidence; do not substitute model confidence |
| Resource | Assignment bound reached, repeated same failure or unreserved paid call needed | Stop with attempts/evidence and request revised scope/budget |

Worst misinterpretation: a YAML model label is not runtime proof, a cheap worker
is not permission to guess engineering logic, and command access is not isolation.

## 6. Ambiguity Audit

| Question | Resolution / owner |
|---|---|
| Which specialist gets trivial work? | Task worker only when contract/pattern/check are known and risk is low; retain domain skill requirements |
| Does Sol decide the architecture? | No; it fills a bounded gap and returns to Astra/owner for approval |
| What if a model is unavailable? | No fallback array; orchestrator stops for an explicit replacement decision |
| Are profiles active in this conversation immediately? | Unknown until host discovery; orchestrator verifies at activation, before feature execution |
| Does this replace the Meta application model? | No; only development models are configured |

## 7. Implementation Guidance

Create the shared agent registry and short profiles; update the workflow,
feature template, always-on instructions, backlog, README and changelog.
Use supported frontmatter only, keep research/plan repair read-only, and inherit
host tools where editing/testing/browser capabilities are needed.

Compatibility assessment: new opt-in development-agent capability, no application
API/data break; proposed **minor 0.2.0**, not a patch for a prose-only correction.
Main-agent governance/configuration work may be performed directly to bootstrap
the team; application execution remains delegated.

### Verification and handoff

- Base: `e8b156a8e306bd5af993b9b6108ceea6c8810aaa`, `master`, primary worktree.
- Static checks, 2026-10-27: DA-1 through DA-6 passed configuration/scenario
  inspection. An isolated Python 3.12/PyYAML 6.0.3 validator checked 11 profiles,
  unique YAML keys, model/effort/visibility/tool fields, body bounds, 12 routing
  cases, 143 local references, 13 backlog IDs/dependencies and version metadata.
  PyYAML was used after the isolated interpreter reported it missing; no project
  dependencies/manifests were added. The temporary validator was not app tooling.
- `git diff --check` passed. VS Code reported no diagnostics for all 11 agent
  files and the updated specification/instructions. These are static checks,
  not tests that model instructions are obeyed at runtime.
- Host discovery/model/tool smoke: pending; no model execution claimed.
- The installed CLI advertises `--agent` and `--reasoning-effort` in `copilot --help`;
  this verifies option availability only, not account entitlement or profile loading.
- Base configuration integrated by owner as version 0.2.0 in `35ed5d2`, confirmed
  on `master` 2026-10-27. DA-7 activation remains unverified; integration alone
  does not establish model/tool selection.

### Blender skill extension (FL-013)

**Outcome:** the 3D worker has a discoverable, evidence-aware offline modeling
workflow for equipment that needs more than procedural tubes/markers.
`[Validated: owner; configuration only, not approval to create assets]`

**Inputs and handoff:** an approved asset brief supplies source/variant identifiers,
attribute evidence, units, dimensions, local axes/pivot, permitted textures,
export/runtime budgets and numerical tolerances. The future asset task returns
reviewed source/script, GLB, manifest and validation evidence. The new skill
defines those requirements without creating a speculative asset schema or binary.

**Routing:** existing Sonnet 3D/motion worker owns modeling and export integration.
Terra may run an already-reviewed deterministic command/check, not invent a mesh
or fix export semantics. No new agent, Blender MCP server, service or renderer.
`[Validated: owner-approved skill/workflow-only scope]`

| ID | Type | Pass condition | Score | Check |
|---|---|---|---|---|
| BA-1 | Behavioral | `fieldlens-blender-assets/SKILL.md` has valid name/description frontmatter; the existing 3D agent and Three.js asset skill link it; model/effort settings remain unchanged. | 3 | YAML, link and metadata comparison |
| BA-2 | Behavioral | Skill covers evidence-aware hard-surface modeling, reviewed bpy scripts, materials/UVs, simplification, preview review and GLB validation; the checklist requires units/axis/pivot/identity and round-trip checks. | 3 | Content/checklist inspection |
| BA-3 | Negative | No executable script, .blend/.glb asset, installation, MCP server, paid call or new agent is created; Blender remains offline and runtime agents cannot execute its scripts. | 3 | Change-scope and tool-execution inspection |
| BA-4 | Edge case | Missing Blender, unknown dimensions/placement, unsupported export features or violated budgets block the affected asset task rather than producing verified-looking geometry or success. | 3 | Failure-path review |

All BA criteria are `[Validated: approved configuration scope]`; they verify the
skill, not Blender or generated assets. Real geometry/export performance checks
belong to the first approved equipment asset slice under FL-007.

**Dependencies/limits:** configuration does not depend on host Blender. No executable
was found on WSL PATH on 2026-10-27; Windows installations were not searched.
Blender 4.5 LTS is an authoring candidate, not an installed/pinned dependency.
`[Unknown: exact patch, platform, GPU/headless compatibility and export smoke;
3D implementer + owner before first asset execution]`

**Failure/escalation:** preserve incomplete evidence, reject untrusted executable
content, keep sources immutable, and return export/scale/identity mismatches to
the orchestrator. Missing permissions/dependencies are not permission to install
or access private/remote data.

**Version/handoff:** propose minor 0.3.0 for the newly invocable authoring skill;
no application API/schema changes. Base `35ed5d2`, primary worktree, no application
implementation delegated. Integration pending.

**Static verification, 2026-10-27:** BA-1 through BA-4 passed metadata/content/
scope checks. A temporary Node validator checked the new two-string YAML header,
eight skill headers, unchanged model/effort/tool settings for 11 agents, two new
routing cases, 158 local references, 14 backlog IDs/acyclic dependencies and
0.2.0/0.3.0 integration/candidate consistency. `git diff --check` passed; the new
skill files are not ignored. The owner's staged ignore edit was preserved while
the authorized removal was made in the working copy. No validator dependency
or executable asset script was added to the project. Blender setup, real assets,
export/render/consumer tests and host model activation remain unrun.

## Open Tensions

Cost/quality rankings are owner routing preferences, not measured superiority.
Use observed retries, token usage and acceptance results to revise them with the
owner. Host differences can limit enforcement; stop rather than claim portability.

## Assumption Registry

| Assumption | Confidence / validation | Invalidation signal |
|---|---|---|
| Host resolves the configured model IDs/efforts | H, advertised catalog; verify at activation | Unknown model, mismatched effort or runtime fallback |
| A small task worker can follow a complete local pattern | M, verify per assignment | Repeated failures or missing design decisions |
| Tool inheritance retains browser/test support | M, inspect actual host tools | Required tool unavailable despite a valid profile |

## Adversarial Self-Critique

1. Role names may conceal overlap: assign ownership explicitly at the ingestion ->
   claims -> RAG and engineering -> renderer boundaries.
2. A cost-saving retry loop can exceed one capable attempt: cap attempts and
   compare outcomes, not nominal model size.
3. Host defaults may override a profile: record actual selection from runtime
   metadata, not the worker's self-description.

## Revision Triggers

Reopen routing when measured retries make Terra inefficient; reopen configuration
when the host changes model/effort/tool semantics; revise role boundaries when
repeated shared-file conflicts show that assignments are not independently owned.
