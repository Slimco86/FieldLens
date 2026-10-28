# FieldLens

**From historical engineering records to an explorable, evidence-backed oilfield.**

FieldLens will reconstruct well trajectories and equipment from uploaded field
records, combine them with terrain/bathymetry and reservoir/formation context,
and attach production and well-log charts to the resulting 3D assets. A
Meta-powered assistant will retrieve evidence, investigate engineering questions,
invoke deterministic spatial tools, and navigate the same scene the user sees.
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
The selected stack and system boundaries are defined; real pilot feasibility,
resolved package compatibility and account-specific API access remain execution
gates, not claims of successful implementation.

Deadline: **November 4, 2026, 9 PM Eastern Time**. API credit budget: **USD 150**.
The demo runs locally on the development WSL machine.
Owner-confirmed submission: **indie track**, **public repository**, and a
**three-minute recorded demo**. Containerized local execution is also acceptable.

The **0.3.0** preparation baseline, including the offline Blender skill, is
committed in `88b177e`; there is still no application release. **0.3.1** is the
pending documentation checkpoint for the architecture/specification package and
data-source assessment.
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
- [Implementation sequence](plan/architecture-fieldlens-1.md): 24 explicit tasks,
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

**Next execution step:** approve and integrate the design/specification package,
verify agent activation, then run the foundation and source-independent contract
slices while resolving pilot access. The native pilot-import slice waits for its
approved source mappings. Both chart families and all contextual layers remain
required; incomplete data is not permission to omit them.
Sign-in succeeded, but the installed shared catalog currently lacks its advertised
public data volume. Pilot access needs owner/provider resolution or an authorized
local copy. Small public equipment probes demonstrate available fields, not a
verified installed pilot completion. No paid infrastructure was created.
