# FieldLens

**From historical engineering records to an explorable, evidence-backed oilfield.**

FieldLens will reconstruct well trajectories and equipment from uploaded field
records, combine them with terrain/bathymetry and reservoir/formation context,
and attach production and well-log charts to the resulting 3D assets. A
Meta-powered assistant will retrieve evidence, investigate engineering questions,
invoke deterministic spatial tools, and navigate the same scene the user sees.

The initial demonstration targets a small Volve subset, typically 3-5 wellbores.
That number is not a product limit. The defining capability is reconstruction
from uploaded evidence, not a pre-authored 3D scene with a chatbot attached.

## Current state

Initial requirements and engineering guidance only. No application, database,
containers, dataset ingestion, or paid model calls have been created by this work.
Product scope and the initial stack are agreed; data feasibility, exact package
compatibility, and account-specific API access remain unverified.

Deadline: **November 4, 2026, 9 PM Eastern Time**. API credit budget: **USD 150**.
The demo runs locally on the development WSL machine.

## Development documents

- [Copilot instructions](.github/copilot-instructions.md): always-on project rules.
- [Project specification](docs/PROJECT_SPEC.md): required outcomes, exclusions,
  acceptance criteria, and explicitly owned open questions.
- [Technical baseline](docs/TECHNICAL_BASELINE.md): agreed stack, rationale,
  engineering conventions, and observed local tooling.
- [Source assessment](docs/SOURCE_ASSESSMENT.md): conversation analysis,
  verified claims, data candidates, and feasibility gates.
- [Feature specification template](docs/specs/FEATURE_TEMPLATE.md): use before
  each implementation increment.
- [Visual reference gallery](docs/design/README.md): the conversation wireframe
  and original FieldLens UX reference sheets, with provenance and design lessons.
- [Curated development skills](docs/DEVELOPMENT_SKILLS.md): selected local skills
  for frontend, 3D assets, geospatial validation, ingestion and equipment research.

**Next step:** jointly inspect a compact, authorized data sample and approve its
feasibility/ingestion spec before committing to a detailed architecture. Both
chart families and all contextual layers remain required; incomplete data is a
scope risk to resolve, not permission to silently omit them.
