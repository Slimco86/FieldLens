# Curated FieldLens development skills

Reviewed 2026-10-27. Selected from the
[original conversation](https://chatgpt.com/share/6ae00399-28c4-83e9-b646-84ead55a2dfd)
for the [agreed stack](TECHNICAL_BASELINE.md), with one original domain-specific
research skill. These are **local, self-contained adaptations**, not unchanged
upstream installs or endorsements of an entire collection.

## Included and discoverable

Skills live under `.github/skills/<name>/SKILL.md`. Their names/descriptions support
Copilot discovery and explicit slash invocation. If the current session has not
refreshed customization discovery, reload/start a new chat; repository files alone
do not prove a running session has loaded them.

| Local skill | Upstream basis | Use in FieldLens |
|---|---|---|
| [fieldlens-react-ui](../.github/skills/fieldlens-react-ui/SKILL.md) | Vercel React Best Practices | Vite UI, state/data flow, linked charts and evidence, bundle/render performance |
| [fieldlens-r3f](../.github/skills/fieldlens-r3f/SKILL.md) | emalorenzo R3F Best Practices | Canvas, controls, picking, frame loop and GPU resource ownership |
| [fieldlens-threejs-assets](../.github/skills/fieldlens-threejs-assets/SKILL.md) | TerminalSkills Three.js | Procedural equipment meshes and validated GLB imports; evidence-tier rendering |
| [fieldlens-geospatial](../.github/skills/fieldlens-geospatial/SKILL.md) | K-Dense GeoPandas | CRS/datum/axis checks, layer alignment, planar-operation limits and join validation |
| [fieldlens-document-ingestion](../.github/skills/fieldlens-document-ingestion/SKILL.md) | K-Dense MarkItDown | Safe parser choice, text/OCR completeness and original-source provenance |
| [fieldlens-ui-review](../.github/skills/fieldlens-ui-review/SKILL.md) | Vercel Web Interface Guidelines, referenced by Web Design Guidelines | Keyboard/accessibility review, error states, charts and scene alternatives |
| [fieldlens-equipment-research](../.github/skills/fieldlens-equipment-research/SKILL.md) | Original FieldLens workflow | Bounded manufacturer research, variant matching and catalog-versus-installed facts |

Use only the skills matching the task, not all seven on every request. The
always-on project instructions and approved feature specs govern scope. Skills
do not approve implementation, authorize external data transmission, install
dependencies, or expose runtime tools to the application agent.
For parallel work, the orchestrator assigns these skills to configured development
agents under the [worktree workflow](DEVELOPMENT_WORKFLOW.md). Skills do not create
agent roles or isolated worktrees. Custom-agent definitions remain deferred.

## Foundational collections: selective adoption

| Collection from the conversation | Decision |
|---|---|
| [Agent Skills specification](https://github.com/agentskills/agentskills) | Format/discovery reference, not a separate installed skill |
| [Vercel Agent Skills](https://github.com/vercel-labs/agent-skills) | Adapt the client React guidance; use its UI-review direction through the separately licensed interface rules |
| [K-Dense Scientific Agent Skills](https://github.com/K-Dense-AI/scientific-agent-skills) | Adapt GeoPandas and MarkItDown only; do not install the large scientific catalog |
| [Anthropic Skills](https://github.com/anthropics/skills) | Reference only. PDF skill has distinct proprietary terms; generic creative/office workflows do not justify copying the collection |
| [LangChain Skills](https://github.com/langchain-ai/langchain-skills) | Defer. LangGraph is not in the initial application stack |
| [skills.sh](https://skills.sh/) | Discovery directory only, not a dependency or trusted automatic installer |
| [Three Agent Skills](https://github.com/emalorenzo/three-agent-skills) | Adapt only relevant R3F rules, not physics/game/debug-tool workflows |
| [TerminalSkills](https://github.com/TerminalSkills/skills) | Adapt the Three.js asset guidance, not the general catalog |

## Specific skills not included

- **GeoMaster:** overlaps the focused geospatial skill and expands into unrelated
  remote sensing/scientific workflows.
- **PaddleOCR hosted skills:** provider/token coupling and duplicate OCR tooling;
  reconsider only if actual document samples defeat the agreed parser approach.
- **Blender Python / Blender Skill and CAD collections:** defer until an actual
  asset needs offline CAD/mesh processing. Simple tubing/casing does not justify
  an extra modeling stack or arbitrary runtime scripts.
- **Vercel AI SDK / LangGraph Quickstart:** would steer toward a different
  agent/backend stack. The Python Meta SDK plus validated tools remains baseline.
- **Generic research-agent services:** do not introduce a paid search subscription
  or unrestricted web access. The original equipment-research workflow fills the
  relevant gap without claiming an upstream runtime capability.
- **WebGPU, physics, decorative animation:** no demonstrated requirement.

## Adaptation assessment

These are deliberate changes, not silent upstream edits:

1. React guidance is narrowed to Vite/client behavior; Next.js APIs, server actions,
   SSR rules and automatic installation of SWR/stores are excluded.
2. R3F advice is contextual rather than absolute: hidden objects still consume
   resources, shared assets need ownership, and animation uses delta time. Upstream
   example-specific APIs are not accepted as verified against our future lockfile.
3. Three.js product/globe demos and unsafe casts are replaced with an engineering
   asset workflow. Runtime generated code and remote model/decoder fetches are barred.
4. GeoPandas and MarkItDown skills no longer reference absent helper scripts,
   install every extra, or prescribe an upstream environment snapshot. They remain
   useful without installing either library; use pyproj/native parsers when sufficient.
5. UI review is local and pinned; it does not fetch fresh instructions and execute
   them on every use. The underlying interface rules have an explicit MIT license;
   the short Web Design Guidelines wrapper is linked, not copied.
6. Equipment research is original and explicitly distinguishes development
   guidance from an implemented runtime agent tool.
7. FieldLens-only follow-up on 2026-10-27 adds selected historical time/revision
   consistency to UI/asset workflows for perforation state. Upstream revision
   fields below still identify the original basis, not these local additions.

## Pinned upstream provenance

Revisions identify the inspected upstream content, not the local adaptation's
runtime dependency version. Local bodies are intentionally rewritten and shorter.
No upstream scripts, nested instruction files, package manifests or installers
are bundled. No runtime package compatibility was tested by this documentation task.

| Basis | Pinned source | License evidence / retained notice |
|---|---|---|
| React | [SKILL.md at 6ec2693](https://github.com/vercel-labs/agent-skills/blob/6ec269328bc400712ee225a173a14b6b29128df7/skills/react-best-practices/SKILL.md) | Skill declares MIT; [notice](licenses/vercel-skills-MIT.txt). No root license file found |
| R3F | [SKILL.md at f950f95](https://github.com/emalorenzo/three-agent-skills/blob/f950f95ae3b13581546e6d6d8b2f88a08eb3e577/skills/r3f-best-practices/SKILL.md) | Skill declares MIT; [notice](licenses/three-agent-skills-MIT.txt). No root license file found |
| Three.js | [SKILL.md at 3bfbf7f](https://github.com/TerminalSkills/skills/blob/3bfbf7f76459d89422eddc0e5f572ad0e6c393c9/skills/threejs/SKILL.md) | Root Apache-2.0; [complete license](licenses/terminalskills-Apache-2.0.txt). No root NOTICE file found |
| GeoPandas | [SKILL.md at 5f2bc03](https://github.com/K-Dense-AI/scientific-agent-skills/blob/5f2bc0341354fd5590aef76a533ada1e1e5b4e62/skills/geopandas/SKILL.md) | Root and skill MIT; [copyright/license](licenses/k-dense-MIT.txt) |
| MarkItDown | [SKILL.md at 5f2bc03](https://github.com/K-Dense-AI/scientific-agent-skills/blob/5f2bc0341354fd5590aef76a533ada1e1e5b4e62/skills/markitdown/SKILL.md) | Root and skill MIT; [copyright/license](licenses/k-dense-MIT.txt) |
| UI guidelines | [command.md at 434b7f9](https://github.com/vercel-labs/web-interface-guidelines/blob/434b7f91364665f2f733b310ec54809bf8f37937/command.md) | Root MIT; [copyright/license](licenses/vercel-interface-MIT.txt) |

SHA-256 of the retrieved upstream source files, for reproducible updates:

| Source | SHA-256 |
|---|---|
| React | `71ed7794962fa6e803ee83030517b5b93a9f70fbfeb431ec4535c5480a8d8355` |
| R3F | `07ef389848b071e023b457b2b054abb4d1d7a35a4eb1cd9f6e5ef91c18fab18e` |
| Three.js | `1c0e6709549a2357ad29cbcf30e23bf5431ea4846f4090a6cbd6146c3e3275ac` |
| GeoPandas | `c03a46f911535326802af476208a1e04de13ea385f4d5309b022ad931826b222` |
| MarkItDown | `8c165c18ceaddc9367dd74f65fd60e42c1c3de9d180828ae1ff09a001af42339` |
| UI guidelines | `d246b026f4f29b5823a9cc857f9edf3d2507002e055e32040cadeaf3b38e0234` |

## Updating safely

Inspect upstream changes and licensing at a new commit; do not run a blanket skill
installer. Apply only useful changes, keep the FieldLens boundaries, update this
record and frontmatter revisions, and verify local links and name/description
metadata. Review any new scripts or network behavior before enabling them.
