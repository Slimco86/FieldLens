# FieldLens

**From historical engineering records to an explorable, evidence-backed oilfield.**

Users create a project and upload related engineering records. A Meta-powered
agent will identify composite entities, establish source-backed relationships and
dated configurations, and present a reconstructed asset model for inspection.
Deterministic services derive trajectories/equipment and align geological context;
linked 3D, production/log charts and conversation expose the same evidence.
Parsing and RAG support reconstruction, rather than a chatbot being added after
the scene is built.
Historical perforation events will support date-specific interval/state inspection,
including MD/TVD placement, perforated length, production/injection, shut-in and
reperforation history without conflating wellbore and individual interval status.

The initial demonstration targets a small Volve subset, typically 3-5 wellbores.
That number is not a product limit. The defining capability is reconstruction
from uploaded evidence, not a pre-authored 3D scene with a chatbot attached.

## Current state

Requirements, architecture, feature specifications, dependency-aware execution
plan and development-agent profiles are documented. No application, database,
containers, dataset ingestion or paid model calls have been created by this work.
The October 28 architecture revision proposes project uploads, reconstruction
review and early source chat before 3D. Detailed defaults await owner review.
Local source access is established; final pilot qualification, package compatibility
and account-specific API access remain execution gates, not implementation claims.

Deadline: **November 4, 2026, 9 PM Eastern Time**. API credit budget: **USD 150**.
The demo runs locally on the development WSL machine.
Owner-confirmed submission: **indie track**, **public repository**, and a
**three-minute recorded demo**. Containerized local execution is also acceptable.

The **0.3.1** initial architecture package was integrated in `4ae7f7b`; there is
still no application release. **0.3.2** is the pending documentation checkpoint
for source inspection and the revised project/reconstruction/UI-first design.
See [VERSION](VERSION) and [CHANGELOG](CHANGELOG.md).

## Development documents

- [Copilot instructions](.github/copilot-instructions.md): always-on project rules.
- [Project specification](docs/PROJECT_SPEC.md): required outcomes, exclusions,
  acceptance criteria, and explicitly owned open questions.
- [Application architecture](docs/ARCHITECTURE.md): module/process boundaries,
  selected stack, data flow, engineering authority, UI and resource budgets.
- [Feature specs and traceability](docs/specs/README.md): complete feature
  breakdown and project requirement-to-test mapping.
- [Shared contracts](docs/specs/SHARED_CONTRACTS.md): identity, evidence,
  revision/time, API, errors, caches and validated actions.
- [Project workspace](docs/specs/PROJECT_WORKSPACE.md): source categories,
  incremental uploads, isolation and source/model revision boundaries.
- [Composite reconstruction](docs/specs/ASSET_RECONSTRUCTION.md): primary agent
  workflow, evidence-linked entities/relationships, review and live evaluation.
- [Implementation sequence](plan/architecture-fieldlens-1.md): 31 explicit tasks,
  dependency DAG, parallel lanes, agent/worktree ownership and deadline checkpoints.
- [Technical baseline](docs/TECHNICAL_BASELINE.md): agreed stack, rationale,
  engineering conventions, and observed local tooling.
- [Source assessment](docs/SOURCE_ASSESSMENT.md): conversation analysis,
  verified claims, data candidates, and feasibility gates.
- [Volve data discovery](docs/VOLVE_DATA_DISCOVERY.md): proposed F-12/F-14/F-5
  cohort, exact candidate-file list, official access steps, rights and known gaps.
- [Data-feasibility spec](docs/specs/DATA_FEASIBILITY.md): draft bounded sample
  audit; metadata discovery is not engineering-data verification.
- [Equipment-data feasibility](docs/EQUIPMENT_DATA_FEASIBILITY.md): actual
  dimensioned XML probes, additional source assessment, and the remaining
  installed-completion go/no-go gate.
- [Feature specification template](docs/specs/FEATURE_TEMPLATE.md): use before
  each implementation increment.
- [Visual reference gallery](docs/design/README.md): the conversation wireframe
  and original FieldLens UX reference sheets, with provenance and design lessons.
- [Curated development skills](docs/DEVELOPMENT_SKILLS.md): selected local skills
  for frontend, 3D assets, geospatial validation, ingestion and equipment research.
- [Blender equipment skill](.github/skills/fieldlens-blender-assets/SKILL.md):
  offline modeling, reviewed bpy scripts and validated GLB export; installation
  and actual assets are deferred, and simple tubes remain procedural in Three.js.
- [Perforation history spec](docs/specs/PERFORATION_HISTORY.md): draft event/state,
  depth, perforated-length and temporal acceptance contracts.
- [Development workflow](docs/DEVELOPMENT_WORKFLOW.md): parallel agent worktrees,
  ownership, testing, integration and version/changelog policy.
- [Development agents](.github/agents/README.md): ten specialists, the main
  orchestrator, model/effort routing and activation instructions.
- [Agent configuration spec](docs/specs/DEVELOPMENT_AGENTS.md): approved scope,
  acceptance and static versus runtime verification.
- [Backlog](docs/BACKLOG.md): persistent feature IDs, prerequisites and delivery state.

## Delivery workflow

The main agent plans and orchestrates; implementation agents work in separate
worktrees on approved, dependency-ready feature specs. Each integration requires
tests, related documentation, and an assessed major/minor/patch update before merge.
After integration, the orchestrator reconciles the backlog. Select
**fieldlens-orchestrator** in the Copilot harness after refreshing agent discovery;
verify **GPT-6 Astra / xhigh** in the host. Workers use Terra low, Sonnet medium
or Sol high according to the task. Repository profiles do not switch an existing
chat or create worktrees; verify the chosen worker/model/tools before execution.

**Next step:** review the draft workflow defaults and sequence before implementation.
Then qualify the host and deliver browser-visible projects/uploads, source inspection
and early chat, reconstruction review, and finally the linked scene/history/context/
charts. Each real-data increment needs its qualified subset; full demo acceptance
still requires the final manifest and live evaluations.
The owner supplied the local data, including actual F-14 installed dimensions.
Remaining F-12/F-5 extraction/coverage and reference/history questions are recorded,
not solved by this architecture. Both chart families and all contextual layers
remain mandatory. No application or paid infrastructure was created.
