# Development workflow: parallel implementation, serialized integration

Adopted 2026-10-27 from the owner's requirements. This governs **development
agents**, not the application's Meta reconstruction/exploration harness. The approved
[agent registry](../.github/agents/README.md) defines model-tier routing, role
boundaries and host activation checks. See [FL-001](specs/DEVELOPMENT_AGENTS.md)
for configuration versus runtime verification.

The [application execution plan](../plan/architecture-fieldlens-1.md) now defines
the task DAG, two resource lanes, critical-path checkpoints and acceptance sequence.
Its [feature index](specs/README.md) maps every project requirement to tests.
Use that plan for scheduling; the rules here remain the governing delivery policy.
The [first detailed packets](../plan/feature-foundation-workspace-1.md) define
foundation, project lifecycle and upload/jobs with file ownership, exact planned
checks and isolated resources. October 28 workflow/cohort approval is not proof
that these packets have been integrated or that a profile/runtime has been verified.

## 1. Roles and authoritative records

- **Owner:** approves feature outcomes/specs and material scope/compatibility changes.
- **Main agent / orchestrator:** maintains the backlog, identifies dependencies,
  agrees contracts, allocates worktrees/resources, delegates implementation,
  reviews results, coordinates tests and owns integration/release metadata.
  Uses GPT-6 Astra with xhigh effort; it is not a default implementation worker.
- **Implementation subagent:** implements its assigned slice in its own worktree,
  tests it, updates feature-specific documentation, commits and returns a handoff.
  It does not edit another worktree or merge the integration branch.
- **Reviewer/tester:** use a configured agent when independent verification adds
  value. Known-command checks use the Terra task worker; risk-based independent
  acceptance uses the Sonnet QA role. The orchestrator remains accountable for
  acceptance and tests on the combined result.

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
| Ready / scheduling | All hard prerequisites are integrated; agreed interfaces/resources exist. Record role/tier rationale, verify profile/model/effort/tools, and record the integration base commit, branch and absolute worktree path before delegation. |
| Implementation | One assigned branch/worktree per active implementation agent. Build a complete bounded slice; update its own spec and related documentation. Escalate scope or shared-contract changes. |
| Test | Run acceptance tests plus affected type/build checks. Record exact commands, commit, environment, fixtures and live/stub status. Failed or unrun required tests block integration. |
| Commit / handoff | Commit tested feature work and related docs; send the contract below. Suggest a bump/changelog entry without allocating a final version. |
| Integration preparation | Main agent incorporates latest target changes, resolves shared edits, runs combined checks and finalizes version/changelog/docs before the integration commit/merge. |
| Merge | Confirm the tested candidate still matches the target base; integrate using approved Git policy. Record success only after checking the resulting target commit. |
| Backlog reconciliation | Mark done with integrated commit, version and acceptance evidence. Clean up only the known, merged, clean worktree after handoff and running tasks are settled. |

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

## 3. Dependency-aware parallelism

- Model real prerequisites, not just list order. Split foundational shared schema,
  API and asset-ID contracts into small approved work before dependent implementers
  need them. Coordinate migration identifiers and generated client ownership.
- Independent slices can run concurrently. For partially dependent work, record
  the frozen interface, upstream ID/base and allowed stubs explicitly. Treat the
  contract-ready portion as a separate ready slice; the live-dependent portion
  remains blocked until its prerequisite is integrated and verified.
- Tests using mocks do not satisfy live database/provider/feature acceptance.
  Rerun dependent checks against the integrated implementation before merging.
- Minimize shared-file overlap. One owner edits a shared schema, lockfile or
  generated artifact at a time; other agents request changes through the main agent.
- The main agent alone edits global backlog/release records during parallel work.
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

## 4. Worktree and resource isolation

Current integration branch is `master`; confirm it before each assignment. Do not
assume a branch called `main`, or create a worktree from uncommitted spec changes.
Persist the approved spec/contract at the recorded base before the agent starts.

Naming convention: branch `feature/FL-<id>-<slug>` (or `fix/` / `docs/` as appropriate);
worktree in an explicit sibling directory such as
`/home/slimco/code/FieldLens-worktrees/FL-008-perforation-history`.
This is a naming example, not a directory created by this task.

Before creation, check Git status, existing branches/worktrees and path ownership.
Never reuse an active branch/path or delete an occupied directory to make room.
Before the first write, the subagent verifies its actual working directory and
branch against the assignment; a mismatch blocks work.
Research and plan repair are read-only and may use an explicitly assigned checkout.
QA needs a stable candidate and isolated test resources, not write ownership.
Read-only roles do not need speculative writable worktrees merely to read files.

Worktrees share Git history and the host. They do **not** isolate:

- **Ports/processes:** assign non-conflicting ports and track specific process IDs.
  Never stop another agent's server or use name-based process killing.
- **Databases/volumes:** use separate test databases or schemas, plus unique Compose
  project/volume names; never run migrations or destructive tests on the demo DB.
- **Dependencies:** use per-worktree environments and lockfile-based installation.
  Do not mutate a shared active environment or copy stale dependency directories.
- **Data/secrets:** provide minimal authorized read access; never commit/copy
  credentials indiscriminately. Immutable source files may be shared read-only;
  generated outputs/caches must be isolated or revision-keyed and concurrency-safe.
- **Compute/API credit:** the orchestrator limits concurrent workers on this WSL
  host and reserves the shared Meta budget. Every worktree does not get USD 150.

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
Feature branch / absolute worktree path:
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
Backlog ID / branch / worktree:
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

One main-agent integration lane prevents parallel branches from independently
claiming the same next version.

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

After successful integration, record the target commit/version and actual test
evidence in the backlog/spec. Stop owned helpers, confirm the branch's work is
contained in the target, and inspect the worktree for uncommitted or untracked work.
Remove only that known, clean worktree using Git worktree management. Preserve
dirty/unmerged work and ask before any destructive cleanup; no forced removal.

Done means persistent code/docs, passing required checks, confirmed integration,
matching version/changelog and a reconciled backlog. A subagent saying "finished,"
a clean feature test run, or a prepared commit alone is not done.
