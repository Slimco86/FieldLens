# Development workflow: one feature branch, one shared checkout

Adopted 2026-10-27 from the owner's requirements. This governs **development
agents**, not the application's Meta reconstruction/exploration harness. The approved
[agent registry](../.github/agents/README.md) defines model-tier routing, role
boundaries and host activation checks. See [FL-001](specs/DEVELOPMENT_AGENTS.md)
for configuration versus runtime verification. The same policy applies when the
work is driven from Claude Code; see [section 9](#9-claude-code-harness) for its
agent, model and activation equivalents (registry: [.claude/agents](../.claude/agents/README.md)).

**Owner amendment, 2026-11-01 at 14:26 EST (supersedes the two-task cap and the 2026-10-28 serial rule):** run
as many independent tasks in parallel as their file ownership allows, each in its own linked worktree under
`/home/slimco/code/FieldLens-worktrees/<lane>` on its own `feature/*` branch with a dedicated agent and its own `./dev`
lane (database, storage, ports). The orchestrator creates the worktrees, assigns non-overlapping file ownership, keeps
`VERSION`, `CHANGELOG`, the contract registry/generated client and the Alembic head serialized (the next branch to merge
rebases onto the new head and re-runs checks), runs independent QA per lane, and **reports every transition to the owner
by Telegram** (`scripts/notify.py`: started, handoff, qa_pass/qa_fail, repair, merged, blocked, with a periodic progress
message while lanes run). Total live-model development/test spend is capped at USD 5 (PROCESSING_FLOW D7).

**Owner amendment, 2026-10-30 at 13:10 EDT (supersedes the 2026-10-28 14:47 serial rule for
this phase):** each feature/task is implemented in its own linked Git worktree under
`/home/slimco/code/FieldLens-worktrees/<name>` on its own `feature/*` branch, by a dedicated
suitable subagent (or group), and up to two such tasks may run in parallel. Each worktree is a
dev-tooling lane (`./dev`, DEV_TOOLING DV-6): its own database, storage root and ports; never
the application/demo database. Orchestrator-owned and serialized across lanes: `VERSION`,
`CHANGELOG`, shared contract registry/generated client edits, and the Alembic head (the second
branch to merge rebases its migration onto the new head and re-runs checks). Only the orchestrator
creates, merges and removes worktrees, after the worker and its checks stop; legacy worktrees stay
untouched. Independent QA, version/changelog finalization and the authorized merge still apply.

**Owner amendment, 2026-10-28 at 14:47 EDT:** develop one feature at a time in
`/home/slimco/code/FieldLens`, on its own branch, with subagents launched by the
main orchestrator session. This replaces parallel worktree dispatch. Preserve
existing worktrees inactive; do not create or remove them for this workflow.
This changes scheduling, not application scope or model/tool verification gates.

**Owner clarification, 2026-10-28 at 17:12 EDT:** every iterative logical feature
requires acceptance testing by an agent other than its implementer. The main
orchestrator assigns and reviews that work; it does not substitute its own test
runs for independent QA. Return failures to the implementation owner, have QA
verify the repaired candidate, and finish the authorized commit/merge cycle only
after every required gate passes. Do not stop at a coding handoff or start the
next feature while acceptance/integration is unfinished. The first foundation
slice remains serial; a return to worktrees requires a subsequent allocation.

**Scoped foundation exception, October 28:** after recurring editor-exposure
failures, the owner requested direct repairs with no more subagents and then
explicitly accepted direct verification of commit `95da2b7` for the 0.4.0 merge.
This exception applies only to TASK-003; independent QA remains required for
future features. Record the direct checks honestly, not as a separate-agent PASS.

The [application execution plan](../plan/architecture-fieldlens-1.md) now defines
the task DAG, one implementation lane, critical-path checkpoints and acceptance sequence.
Its [feature index](specs/README.md) maps every project requirement to tests.
Use that plan for scheduling; the rules here remain the governing delivery policy.
The [first detailed packets](../plan/feature-foundation-workspace-1.md) define
foundation, project lifecycle and upload/jobs with file ownership, exact planned
checks and isolated resources. October 28 workflow/cohort approval is not proof
that these packets have been integrated or that a profile/runtime has been verified.

## 1. Roles and authoritative records

- **Owner:** approves feature outcomes/specs and material scope/compatibility changes.
- **Main agent / orchestrator:** maintains the backlog, identifies dependencies,
  agrees contracts, allocates the feature branch/resources, delegates implementation,
  reviews results, coordinates tests and owns integration/release metadata.
  Uses GPT-6 Astra with xhigh effort; it is not a default implementation worker.
- **Implementation subagent:** implements its assigned slice in the shared checkout
  on the orchestrator-selected feature branch as the sole active writer,
  tests it, updates feature-specific documentation, commits and returns a handoff.
  It does not switch branches, edit another checkout or merge the integration branch.
- **Reviewer/tester:** a separate configured agent independently verifies every
  logical feature. Known-command checks use the Terra task worker; risk-based
  acceptance uses the Sonnet QA role. The orchestrator assigns the checks and
  reviews evidence, including combined-result checks, rather than executing them.

[BACKLOG](BACKLOG.md) is the persistent cross-session ledger.
[Feature specs](specs/FEATURE_TEMPLATE.md) define acceptance and contracts.
[VERSION](../VERSION) is the single application/project version source.
[CHANGELOG](../CHANGELOG.md) records user/developer-visible changes by integration.
Session todos and chat messages supplement these files; they do not replace them.

The main agent may directly maintain planning, integration, agent configuration
and documentation.
The default for **feature implementation** is delegation, not several agents
editing the primary working directory. A documentation-only governance update,
such as this one, does not require launching implementation agents.

## 2. Lifecycle and gates

`proposed -> specifying -> ready -> in_progress -> testing -> integration_pending -> done`

`blocked` can interrupt any unfinished state; record reason, dependency, owner and
resume state. `cancelled` requires an explicit owner decision and retained rationale.

| Stage | Required action and exit gate |
|---|---|
| Backlog definition | Assign a stable ID, outcome, priority, owner and actual prerequisite IDs. Separate mandatory scope from optional extensions. |
| Feature spec | Define scope, input/output contracts, evidence, failures, numerical thresholds, tests and shared-file ownership. Get owner approval; a draft is not ready. |
| Ready / scheduling | All hard prerequisites are integrated; agreed interfaces/resources exist. Record role/tier rationale, verify profile/model/effort/tools, and record the integration base commit, feature branch, absolute checkout path and pre-existing dirty files before delegation. |
| Implementation | One active feature branch and one writer in the shared checkout. The orchestrator pauses its writes until the worker returns. Build a complete bounded slice; update its own spec and related documentation. Escalate scope or shared-contract changes. |
| Test | A separate agent checks all acceptance criteria plus affected type/build gates on a stable candidate. Record exact commands, commit, environment, fixtures and live/stub status. Return failures to the implementer and independently re-verify fixes. Failed or unrun required tests block integration. |
| Commit / handoff | Commit tested feature work and related docs; send the contract below. Suggest a bump/changelog entry without allocating a final version. |
| Integration preparation | Main agent incorporates latest target changes, resolves shared edits, delegates combined checks and finalizes version/changelog/docs before the integration commit/merge. Re-verify affected behavior if the tested candidate changes. |
| Merge | Confirm the tested candidate still matches the target base; integrate using approved Git policy. Record success only after checking the resulting target commit. |
| Backlog reconciliation | Mark done with integrated commit, version and acceptance evidence. Settle workers/checks/helpers and preserve dirty files before the orchestrator switches branches for the next feature. |

Backlog state changes are persisted as work proceeds. `Verified` in a feature spec
means its acceptance checks passed; it does not by itself mean merged or released.
Only integration plus recorded evidence permits `done`.

Product increments must end with an owner-verifiable browser workflow using real
API/database persistence: projects/uploads, source inspection/chat, reconstruction
review, then scene/history/context/charts. Numeric engines and provider adapters
are supporting tasks, not substitute UX milestones. Record which qualified source
subset and which live/mock provider mode each checkpoint uses; partial acceptance
cannot mark a complete feature or final demo verified. Review the checkpoint
before widening scope so identity, temporal or UX drift is visible early.

## 3. Dependency-aware serial execution

- Model real prerequisites, not just list order. Split foundational shared schema,
  API and asset-ID contracts into small approved work before dependent implementers
  need them. Coordinate migration identifiers and generated client ownership.
- Independent slices remain eligible in the DAG but execute sequentially, not
  concurrently. Finish, test and integrate the active feature before starting
  another. For partially dependent work, record frozen interfaces and allowed
  stubs explicitly; live-dependent acceptance still requires integrated prerequisites.
- Tests using mocks do not satisfy live database/provider/feature acceptance.
  Rerun dependent checks against the integrated implementation before merging.
- Minimize shared-file overlap. One owner edits a shared schema, lockfile or
  generated artifact at a time; other agents request changes through the main agent.
- The main agent alone edits global backlog/release records between worker turns.
  Subagents report status and supply proposed release notes in their feature spec.
- Each agent uses only relevant skills. Deferring a runtime LangGraph/multi-agent
  framework does not change this development scheduling policy.

### Model-tier routing and escalation

Apply the [routing policy and examples](../.github/agents/README.md#routing-policy),
not a blanket "all implementation is simple" or "all domain work is expensive":

- **Terra / low:** exact-pattern boilerplate, mechanical changes and known
  test/build commands with frozen contracts and low risk.
- **Sonnet / medium:** the relevant frontend, backend, 3D/motion, research,
  ingestion, RAG, geospatial or QA specialist for interconnected, evidence-sensitive
  or performance-constrained work.
- **Sol / high:** one bounded gap in the plan/contract, returning evidence and a
  proposed amendment to Astra/owner; no speculative implementation.
- **Astra / xhigh:** global decisions, orchestration and integration only.

Under Claude Code the tiers map to Claude aliases (see [section 9](#9-claude-code-harness)).

One role owns each slice; its domain does not force that model for trivial work.
Do not create tier duplicates for every role. Workers return blockers instead of
spawning other workers or escalating their own model. Two attempts without new
evidence end the worker assignment; the orchestrator diagnoses, narrows or re-plans
before authorizing another attempt. Failed checks are not permission to lower ACs.

Verify actual model/effort using host selection/trace metadata; self-identification
is not evidence. Use profile defaults, check user-level overrides and stop on
missing capabilities instead of silent fallback. Keep token/cost estimates labeled;
record unavailable telemetry as unavailable. Bound assignment time, attempts,
context and host resources; never duplicate the USD 150 Meta budget per worker.

### Offline equipment asset assignments

The existing 3D/motion role uses the
[Blender skill](../.github/skills/fieldlens-blender-assets/SKILL.md) when an
approved equipment slice needs offline modeling. Simple tubes/markers remain
procedural; adding the skill does not approve installation or specific assets.
Assign source/dimension evidence, local axes/pivot and part IDs, output/storage
ownership, exact Blender build, export/reload checks and browser/compute budgets.
Keep `.blend` sources/reviewed scripts separate from runtime GLB and engineering
records. Terra may run a reviewed deterministic export/check, not design its mesh.
No new agent, Blender service or runtime code execution is implied.

## 4. Shared checkout and resource isolation

Current integration branch is `master`; confirm it before each assignment. Do not
assume a branch called `main`, or dispatch implementation against uncommitted contracts.
Persist the approved spec/contract at the recorded base before the agent starts.

Naming convention: branch `feature/<slice>-<slug>` (or `fix/` / `docs/` as appropriate)
in `/home/slimco/code/FieldLens`. Use a new unoccupied branch name if a preserved
worktree already owns the original name; never force-checkout that branch.

Before creating/switching branches, check Git status and existing branches/worktrees.
Preserve pending work; do not stash, commit or discard unrelated changes implicitly.
Only the orchestrator switches branches, after all workers and branch-bound
tests/watchers/servers have stopped. Never switch while a worker is still running.
Before the first write, the subagent verifies its actual working directory and
branch against the assignment; a mismatch blocks work.
Launch subagents from the main session with that same checkout and branch.
Use one writer at a time, including orchestrator documentation edits. QA and
read-only reviewers run against a stable candidate after the implementation turn.

Sequential branches still share the host. They do **not** isolate:

- **Ports/processes:** assign non-conflicting ports and track specific process IDs.
  Never stop another agent's server or use name-based process killing.
- **Databases/volumes:** use separate test databases or schemas, plus unique Compose
  project/volume names; never run migrations or destructive tests on the demo DB.
- **Dependencies:** use project-local environments and lockfile-based installation.
  Reconcile dependencies to the selected branch before checks; never reuse an
  environment while another process is modifying or running against it.
- **Data/secrets:** provide minimal authorized read access; never commit/copy
  credentials indiscriminately. Immutable source files may be shared read-only;
  generated outputs/caches must be isolated or revision-keyed and concurrency-safe.
- **Compute/API credit:** one active implementation worker and one heavy workload
  on this WSL host. Reserve the shared Meta budget; each feature does not get USD 150.

Subagents must not push, tag, publish, force-rewrite branches, or merge `master`
without explicit orchestration/authorization. Repository instructions do not
override user permissions or branch protection.

## 5. Assignment and handoff contract

Record in the feature spec before launch:

```text
Backlog ID / approved spec / acceptance criteria:
Configured agent role / complexity-risk rationale:
Requested model/effort / actual host selection evidence:
Base commit / integration target:
Feature branch / absolute checkout path / pre-existing dirty files:
Prerequisites and frozen contracts:
Owned files; shared files requiring coordination:
Test data/database/ports/Compose project:
Required test/type/build commands:
External-data permissions and shared budget allocation:
Time/tool/test-attempt bounds / context and compute limits:
Stop/escalation conditions:
```

Return after implementation:

```text
Backlog ID / branch / checkout:
Feature commit(s) and tested HEAD:
Implemented outcomes and affected contracts:
Commands + results + fixture/environment + live/stub status:
Actual model/effort evidence / attempts / elapsed time / exposed usage:
Known limitations and remaining blockers:
Proposed bump (major/minor/patch) and compatibility rationale:
Proposed changelog entry + migration/operator documentation:
Resources still running; cleanup/handoff status:
```

No success-only summary: include skipped checks, blocked acceptance and residual
risks. Do not mark another agent's dependency done based on a message alone.

## 6. Integration and version allocation

The main agent integrates the active feature before assigning the next feature
branch. Only it allocates the next version.

1. Receive the tested feature commits and handoff. Confirm the target base, scoped
   changes, acceptance evidence and prerequisite commits.
2. Bring the candidate onto the current integration tip using an agreed merge or
   rebase policy. No force push, unapproved history rewrite or blind conflict
   resolution. Review cross-feature schema/API/generated-file compatibility.
3. Run feature and affected integration/type/build checks on this combined tree.
   Regenerate derived types/locks through their tooling; do not hand-merge them
   merely to remove conflict markers.
4. Against the **current target VERSION**, classify the combined change, assign
   its next version, finalize CHANGELOG, and update feature/operator documentation.
   The backlog remains `integration_pending` with planned version/test evidence.
5. Verify release metadata and any version-dependent build/tests, then commit
   finalization before merge. This is the feature's versioned integration candidate.
   Implementer WIP and test-fix commits do not each become release milestones.
6. Integrate only if the target tip is unchanged from the tested base. If it moved,
   reconcile, reallocate the version and rerun affected checks. Prefer a fast-forward
   of a validated descendant; if policy requires a merge commit or PR, validate its
   combined tree and obey protection rules. Do not let an automatic merge bypass gates.
7. Confirm the resulting integration commit, version and changelog. Then reconcile
   the backlog to `done` and record that commit. Do not fabricate the final hash in
   a pre-merge file: commits cannot contain their own eventual hash.

If work/tests/merge fail, keep the item blocked or integration-pending, not done;
keep candidate notes pending and do not announce a release. Once a version has
been integrated, a later revert/fix is a new assessed change, not silent reuse.
Tags/publishing are separate authorized actions, not implied by a local merge.

Post-merge bookkeeping may need a small commit containing **only** status,
integrated hashes and verification references. Such administrative reconciliation
does not increment the product version or add a recursive changelog entry.
Actual feature/fix/documentation changes cannot hide in that exception.

## 7. Version and changelog policy

Use SemVer-shaped `MAJOR.MINOR.PATCH`, with the owner's strict compatibility rule
even during 0.x development:

| Change | Update | Example |
|---|---|---|
| Breaking API/schema/tool/behavior contract | Increment major; reset minor and patch | `0.4.2 -> 1.0.0` |
| Backward-compatible new feature | Increment minor; reset patch | `0.4.2 -> 0.5.0` |
| Backward-compatible fix or documentation change | Increment patch | `0.4.2 -> 0.4.3` |

Assess behavior, persisted data/migrations, API payloads, tool schemas and user
workflows, not just file extensions or commit prefixes. Document impact and
migration steps for breaking changes. If a candidate includes several change
types, use the highest required bump. Keep integrations feature-sized; do not
batch unrelated completed features merely to avoid versioning them individually.

There is **one bump per accepted integration**, not one for implementation commits
and another for the merge. Two independent features integrated consecutively from
`0.1.0` become `0.2.0`, then `0.3.0`, even if both branches started at `0.1.0`.
Feature commits may inherit their base's version until serialized finalization.

Bootstrap exception: this previously unversioned, documentation-only repository
initializes [VERSION](../VERSION) to `0.1.0`. Its initial changelog remains under
`Unreleased` until actually integrated; no historical release/tag is invented.
After initialization, documentation-only integrations are patch changes.

At finalization, turn the candidate notes into a dated version section (date in
America/New_York), leave an empty `Unreleased` section for future work, and ensure
VERSION matches the newest version entry in the candidate. That version becomes
integrated only after a successful merge. Record backlog IDs, user-visible
changes, compatibility/migration notes and verification/limitations. A requirement
documented is not a feature implemented; label it accordingly.

Future package/build metadata must derive from VERSION or be synchronized by
documented tooling and checked for equality. Do not create dummy application
manifests now. Application version, source dataset revision, migration ID and
embedding-model revision remain distinct.

## 8. Cleanup and completion

**Progress reporting and tracker mirror.** The orchestrator sends a Telegram message at each
transition (start, handoff, QA verdict, repair, merge/release, blocker, owner decision,
cleanup) via `scripts/notify.py`; action-required messages carry the 🔴 ACTION NEEDED marker.
`docs/BACKLOG.md` item blocks are validated by `uv run python scripts/track.py check` before
every backlog commit and mirrored one way into the Taiga sprint `Hackathon` with
`uv run python scripts/track.py sync --apply`. Tracker edits are overwritten; owner decisions
go through the repository. Spec: [TRACKING](specs/TRACKING.md).

After successful integration, record the target commit/version and actual test
evidence in the backlog/spec. Stop owned helpers, confirm the branch's work is
contained in the target, and inspect the shared checkout for pending work before
switching branches. Preserve dirty/unmerged work and all inactive legacy worktrees.
Their removal requires separate approval; no forced removal or automatic cleanup.

Done means persistent code/docs, passing required checks, confirmed integration,
matching version/changelog and a reconciled backlog. A subagent saying "finished,"
a clean feature test run, or a prepared commit alone is not done.

## 9. Claude Code harness

The workflow above is harness-neutral. It was first verified with GitHub Copilot
profiles in `.github/agents/`; the same roles are also defined as Claude Code
subagents in `.claude/agents/` (registry: [README](../.claude/agents/README.md);
project instructions: [CLAUDE.md](../CLAUDE.md)). The two sets are maintained
separately. Roles, gates, ownership, handoff and integration rules are identical;
only the model names and activation mechanics differ. Use one harness per feature.

| Role | Copilot profile model | Claude Code model / effort |
|---|---|---|
| Orchestrator (Astra / xhigh) | GPT-6 Astra | `sonnet` / high (owner decision) |
| Task worker (Terra / low) | GPT-6.1 Terra | `haiku` / low |
| Domain specialists and QA | Sonnet 5.5 / medium | `sonnet` / medium |
| Plan repair (Sol / high) | GPT-6.1 Sol | `sonnet` / high |

Wherever this document says Astra, Terra or Sol, read the Claude Code column when
running under Claude Code. Differences that matter:

- **Orchestrator is the main session.** Start it with
  `claude --agent fieldlens-orchestrator`. Claude Code subagents cannot spawn
  subagents, so it cannot be delegated to; it launches workers with the Agent tool.
  Workers still never delegate.
- **Verification.** Confirm the worker is listed as an available agent type and its
  frontmatter `model`/`effort`/`tools` match the table; do not pass `model`
  overrides at launch; check `~/.claude/agents/` for shadowing. Agent files load
  at session start, so restart after editing. Self-identification is still not evidence.
- **Tools.** Research and plan-repair are restricted to read/search (plus web for
  research) via `tools:`; other workers inherit all tools and their limits remain
  instructions, not isolation.
- **Skills.** `.claude/skills` is a symlink to `.github/skills`, so both harnesses
  share the same skill files. Workers read only the skills linked from their profile.
- **Records.** In the assignment/handoff contract, "Requested model/effort / actual
  host selection evidence" refers to the Claude Code frontmatter values and the
  session/trace metadata. Claude Code usage is development usage, separate from the
  USD 150 Meta application credit.
- **Unchanged.** Branch/worktree policy, independent QA, version/changelog
  allocation, notifications, tracker sync and the no-push/no-destructive-cleanup
  rules apply as written.
