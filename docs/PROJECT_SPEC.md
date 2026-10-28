# Specification: Upload-driven, evidence-backed oilfield exploration

> **Spec type:** Product/feature.
> **Load-bearing frameworks:** F1 outcome, F2 acceptance, F3 scope, F4 executor context.
> **Supporting:** F5 failure conditions, F6 ambiguity audit.
> **Date:** 2026-10-26, America/New_York.
> **Updated:** 2026-10-27: historical perforations, versioned delivery and data-first planning/submission decisions.
> **Author:** Copilot-assisted synthesis. **Decision owner:** project owner.
> **Status:** Product scope approved; DRAFT for implementation until external gates close.
> **Zero-Question Score:** 0 unowned questions; 5 explicitly owned TBDs below still block affected work.

## How to Read This Spec

| Reader | Start here | Then consult |
|---|---|---|
| Owner | Outcome, Scope, Open Tensions | Assumption Registry |
| Implementer / AI coding agent | Scope, Acceptance Criteria, Context | Technical baseline and feature template |
| Tester | Acceptance Criteria, Failure Conditions | Data manifest once approved |

## Notation Key

- `[Validated]`: confirmed by the owner or a named source; not proof of implementation.
- `[Assumed: verify]`: proposed choice requiring the named owner's confirmation.
- `[Unknown: TBD]`: unresolved, with owner and deadline in the ambiguity audit.
- H / M / L: high (>70%), medium (40-70%), low (<40%) confidence estimates,
  not statistical probabilities.
- AC scores: 0 subjective; 1 requires unstated context; 2 outsider-testable;
  3 explicit pass/fail measurement or observable state.
- Owned TBDs make uncertainty explicit; they do not make a blocked feature executable.

## 1. Outcome Statement

After implementation, a user can upload the agreed historical field dataset and
inspect its evidence-backed wellbores, equipment, terrain/bathymetry and
reservoir/formation layers and date-specific perforation state in a linked 3D/chart
interface, using a Meta-powered assistant to answer source-grounded questions and
navigate those same assets.

**Verification:** execute AC-1 through AC-10 against an approved, versioned demo
manifest, with a live Meta integration and a fresh import.
**Outcome rubric score:** 3, conditional on the manifest and layer definitions
being approved; these are explicit dependencies, not completed work.

## 2. Scope

### IN Scope

All rows are `[Validated: owner clarification in this session]`.

| ID | Required capability | Boundary | AC |
|---|---|---|---|
| S-1 | Upload and reconstruction | Supported, declared formats from the chosen subset; source traceability and repeatable ingestion | 1-3 |
| S-2 | Well trajectories | Shared spatial reference; real source measurements; target 3-5 wellbores without hard-coded count limits | 3 |
| S-3 | Equipment | Casing, tubing, pumps, packers, perforations or other components evidenced in the sample; three-tier fallback below | 4 |
| S-4 | Geographic/geological context | Terrain or offshore seabed/bathymetry as appropriate, plus reservoir/formation representation | 5 |
| S-5 | Linked charts | Both production time series and well-log depth charts; linked asset selection | 6 |
| S-6 | Agentic RAG | Exact/full-text/vector retrieval, typed knowledge graph relationships, cited answers and deterministic tools | 7 |
| S-7 | Catalog enrichment | Bounded web research for identified equipment whose uploaded specifications are insufficient | 4, 7 |
| S-8 | Reliable local demo | Explicit partial/error states, persistent revisions, bounded cost, responsive interaction | 8-10 |
| S-9 | Historical perforations | Dated events, MD/TVD intervals, perforated length, open/isolated state and separately evidenced producing/injecting/shut-in status; scoped to wellbore or interval | 4, 6-8 |

Equipment policy: prefer drawings and dimensions from source records; otherwise
research the documented manufacturer/model and label results as catalog-derived;
if identification/specifications remain unknown, show a generic asset with a
missing-information explanation. Unknown placement means an unlocated asset,
not a guessed installation depth. Display defaults are never engineering facts.
The owner reaffirmed that technical equipment evidence is essential. The
[data-feasibility spec's proposed DF-9 checkpoint](specs/DATA_FEASIBILITY.md)
requires a coherent source-backed pilot assembly before accepting equipment
feasibility; individual generic fallbacks do not make a generic-only scene
evidence-backed. Exact checkpoint thresholds remain subject to G1 approval.

Perforation events must preserve effective time and provenance so the state at a
selected date can be reconstructed, including repeated opening, shut-off, role
changes and reperforation. Use **total perforated length** (perforated footage when
in feet) for unique perforated MD coverage, and a separate **open perforated length**.
These are not horizontal displacement, TVD span, shot density or tunnel penetration.
Reperforation can extend coverage but repeated work over the same interval must not
double-count it. The [dedicated draft spec](specs/PERFORATION_HISTORY.md) defines
the proposed contract, fixtures and remaining source-data decisions.

### OUT of Scope

| Exclusion | Rationale / treatment |
|---|---|
| Universal PDF/CAD/engineering-format support | A heterogeneous-input vision does not imply every format works in v1. The audit selects formats; unsupported files get an explicit error. `[Assumed: verify with owner at G1]` |
| Live telemetry, operational control, reservoir simulation, anti-collision certification | Historical exploration cannot establish current operating state or safety. `[Validated: source conversation boundary]` |
| Inferring reservoir connectivity from well proximity | Geometry alone is insufficient. `[Validated: source conversation]` |
| Full CAD reverse engineering from arbitrary drawings or model names | Deterministic parametric visual assets first; complex CAD imports require a separate justified spec. `[Assumed: verify at G1]` |
| Dedicated graph DB, application-runtime multi-agent framework, separate Node API, Kubernetes | No demonstrated requirement; graph semantics remain in scope. This does not exclude the required parallel development agents/worktrees. `[Validated: accepted baseline; owner clarification 2026-10-27]` |
| Full manual conflict-resolution application | Owner defers this unless actual conflicts require it; detection and safe blocking remain mandatory. `[Validated]` |
| Hosted multi-user deployment and authentication product | Local single-user demo is accepted; local binding and secret protection still apply. `[Validated]` |
| Photorealism and WebGPU migration | Not a substitute for correct, navigable geometry. `[Validated: accepted baseline]` |

### Scope Dependencies

No excluded item is intentionally required by an included one. If selected data
needs an excluded CAD importer or manual-resolution workflow, escalate before
adding it. Terrain, geological layers, and both charts are NOT excluded.

### Open Scope Tensions

The owner requires the full enriched scene by November 4, but the complete,
compatible dataset has not been acquired. Preserve the requirement and audit
the minimum truthful representation for each layer. Do not count placeholder
terrain or invented reservoirs as fulfillment. Owner decision due at G1.

## 3. Acceptance Criteria

ACs are verification contracts, not claims about current capabilities. A test
depending on an unresolved manifest or threshold is blocked, not passed.

| ID | Type | Pass condition | Score | Annotation |
|---|---|---|---|---|
| AC-1 | Dependency | Approved manifest identifies every demo file, checksum, rights/access status, asset IDs, format, CRS/depth/unit references, expected outputs and numerical tolerances; includes every required layer, both chart families and perforation/state events with temporal precision and coverage limits. | 3 | `[Unknown: TBD, G1 / owner + implementer]` |
| AC-2 | Behavioral | Starting from an empty project dataset, uploading the manifest produces versioned records and source locators without hand-editing geometry. Re-importing identical content creates no duplicate facts; importing a changed source creates a traceable revision. | 3 | `[Validated: upload-driven objective; operational contract proposed for G1 approval]` |
| AC-3 | Behavioral | Every accepted survey reconstructs within the manifest's independently checked coordinate tolerances. Selection resolves to the correct wellbore/source. Counts come from imported records, not five fixed slots. | 3 | `[Validated: source-backed trajectories and non-limiting count]` |
| AC-4 | Behavioral / negative | Three equipment fixtures exercise documented, catalog-derived and unknown/generic states. Each shows its evidence/missing-data label. Generic dimensions and unknown placement never participate in physical measurements; catalog lookup cannot overwrite an installed configuration. Perforation fixtures pass the dedicated spec's historical-state, MD/TVD and unique-length checks, including shut-off/reopening and reperforation without duplicate footage. | 3 | `[Validated: owner scope; detailed temporal contract pending feature approval]` |
| AC-5 | Behavioral | The approved scene displays the manifest's terrain/bathymetry and reservoir/formation layers aligned to its wells. Every layer exposes source and measured/interpolated/illustrative status. A missing-data notice alone does not pass this requirement. | 3 | `[Validated: all layers mandatory; representation TBD at G1]` |
| AC-6 | Behavioral | Selecting an asset opens its production time series and depth-log chart where associated. Values, dates/depths, units and gaps match fixtures. Perforation overlays and the selected-date marker reflect the same as-of state; series retain their acquisition dates and are not relabeled as measurements at that instant. Asset/time changes cannot leak stale results. | 3 | `[Validated: both chart families and historical perforations required]` |
| AC-7 | Behavioral | A fixed evaluation set covers source lookup, equipment explanation, well navigation, chart retrieval, closest approach and dated perforation/state/length queries. Answers cite evidence and identify as-of time/revision; actions target the expected object; numbers match deterministic fixtures. Unanswerable controls report insufficient evidence, including interval production unknown despite well-level production. | 3 | `[Assumed: verify evaluation set with owner at G3]` |
| AC-8 | Edge case | Missing CRS, inconsistent depth units, conflicting dimensions or event order, unknown initial perforation history, unavailable catalog, and interrupted import each produce explicit affected-record/job states. No invented value is committed as verified; prior revisions remain available and distinguishable from incomplete work. | 3 | `[Validated: reliability requirement; exact states defined in feature specs]` |
| AC-9 | Non-behavioral | On the documented demo manifest/browser at 1920x1080, p95 frame duration during a 30-second orbit is <=33.3 ms after warmup; p95 local read API latency is <=1 s over 20 requests during one import. Report model latency separately. | 3 | `[Assumed: verify proposed budgets with owner at G1; not measured]` |
| AC-10 | Negative / non-behavioral | Provider failure, budget exhaustion, hostile document instructions and invalid tool IDs produce explicit safe failures. Browser bundles/logs contain no credentials. Default automated tests make zero paid calls; live validation records token/tool cost against the USD 150 balance. | 3 | `[Validated: cost and integrity constraints; tests to implement]` |

**Complexity:** complex, 10 project-level criteria; individual features need
smaller specs. **Definition of done:** all required ACs pass on the agreed data,
proposed thresholds are approved, external gates close, and evidence of validation
is recorded. A prerecorded or cached demo alone does not verify live integration.

## 4. Context and Decisions

### Executor Profile

Human developer and AI coding assistants; no existing application context may be
assumed. The project owner is available in this conversation for scope decisions.
The main agent plans, delegates and integrates. Implementation subagents use
separate worktrees under the [development workflow](DEVELOPMENT_WORKFLOW.md);
the [approved agent roster](../.github/agents/README.md) assigns Astra xhigh to
global orchestration, Terra low to exact low-risk work, Sonnet medium to substantive
domain execution and Sol high to bounded plan repair. These development models
do not replace the Meta application model or relax source/acceptance requirements.

### Glossary

| Term | Meaning here |
|---|---|
| Digital twin | Historical reconstructed representation; no implied live synchronization |
| Well / wellbore | Well identity versus an individual drilled path or sidetrack; not interchangeable |
| MD / TVD | Distance along the well path / vertical depth from a stated datum |
| Total perforated length | Unique perforated MD interval coverage, excluding gaps/overlap; a precisely defined project metric, not horizontal width |
| As-of state | State effective at the selected historical time, evaluated within an identified dataset revision |
| CRS / datum | Horizontal coordinate system / physical reference for positions or elevations |
| Completion | Installed well equipment and intervals for a specified configuration/date |
| Knowledge graph | Typed entities and evidence-backed relations; not necessarily a graph DB product |
| Catalog-derived | Specifications for an identified product, not proof that it was installed that way |
| Generic | Display-only representation of missing information, not inferred engineering truth |

### Decisions Already Made

Initial decisions dated 2026-10-26; additions dated explicitly below.
`[Validated: project owner in this session]`.

| Decision | Rationale |
|---|---|
| Local single-user demo; 3-5 wellbores are a dataset target | Demonstrate the complete workflow without arbitrary count limits |
| Full contextual scene and both chart families are required | Latest owner clarification supersedes earlier stretch-feature proposals |
| Python + React/TypeScript baseline | Engineering ecosystem, browser visualization, small operational footprint |
| PostgreSQL + pgvector + typed relation tables | Relational integrity, hybrid retrieval and initial graph in one datastore |
| Three-tier equipment rendering policy | Show incomplete information honestly rather than silently omitting or fabricating |
| Separate feature specs before implementation | Iterative, bounded, testable delivery |
| Historical perforation events, state and footage (2026-10-27) | Changes across completion/production/injection history must be inspectable |
| Parallel development agents in separate worktrees (2026-10-27) | Main-agent orchestration with independent implementation and serialized integration |
| Major/minor/patch version and changelog discipline (2026-10-27) | Breaking/features/fixes-docs assessed for each accepted integration |
| Inspect real samples before final architecture (2026-10-27) | Source probes inform the completed architecture; pilot mappings/feasibility remain gated rather than invented. Source-independent contracts do not assert pilot readiness |
| Indie track, public repository and three-minute recorded demo (2026-10-27) | Owner-confirmed submission constraints; full authenticated rules still need review |
| WSL-local or containerized runtime; owner can start Docker (2026-10-27) | No hosted deployment or cloud account is required by the product |
| Meta key ready; public-data processing permitted (2026-10-27) | Select an appropriate entitled model after bounded testing; no waiver of source/provider terms or Contributor-mode permission |

### Dependencies

| Dependency | Status | Owner | Blocker |
|---|---|---|---|
| Compatible surveys, equipment/perforation event documents, dated state evidence, context layers, production and logs | No prepared files; [metadata-only candidates](VOLVE_DATA_DISCOVERY.md) identified, actual sample access/audit pending | Owner + implementer | Yes, G1 |
| Meta account entitlement and remaining credit | Owner confirms local key and public-data processing permission; entitlement/balance/protocol untested | Owner + implementer | Yes, G2 |
| Supported frontend runtime and project packages | Python available; Node update and dependency resolution pending | Implementer | Before scaffolding |
| Detailed event rules and publication rights | Owner confirms track/public repo/video; Volve license reviewed, per-file/publication and authenticated-rule checks remain | Owner | G4, before publication |

### Constraints

Deadline: `2026-11-04T21:00:00-05:00`, confirmed by owner and public event page.
Budget: USD 150 API development/testing credit, owner-confirmed, not a verified
current balance. Use the current WSL host where reasonable; no OS-wide changes
or additional paid services are implied. `[Validated]`

### Stakeholders

Project owner approves scope, expenditure, sources and submission. Implementer
owns technical proposals, fixtures and validation. Judges are demo consumers;
their authenticated submission requirements remain to be checked.
The three-minute video must fit the owner-confirmed submission limit; a public
code repository does not imply publishing raw engineering files under its license.

## 5. Failure Conditions

| ID | Type | Assumption at risk / signal | Action | Severity |
|---|---|---|---|---|
| FC-1 | Data | No compatible source for a mandatory layer, trajectory reference or log series at G1 | Stop affected implementation; present evidence and obtain explicit scope/data decision from owner | Critical |
| FC-2 | Integration | Account cannot call the selected Meta model or its needed tools/outputs | Stop model-dependent work; verify entitlement/protocol, not a silent non-Meta replacement | Critical |
| FC-3 | Workflow | Reliable import would require extensive human adjudication | Quarantine affected claims; ask owner to select cleaner data or approve a minimal review feature | Major |
| FC-4 | Authorization | Data terms disallow intended sharing or provider processing | Do not transmit/publish affected content; request an authorized alternative | Critical |
| FC-5 | Resource | Parsing exhausts host memory or cannot meet the approved demo timings | Profile, bound work and test a smaller parser/sample; do not remove required capabilities without approval | Major |

**Worst Misinterpretation Test:** a hand-drawn scene is not reconstruction; a
generic pump is not verified pump geometry; vector similarity is not provenance;
a formation plane without evidence is not a reservoir model; an API error is not
an empty but successful answer. AC-2/4/5/7/8/10 explicitly reject these shortcuts.

## 6. Ambiguity Audit

Dates below are proposed decision checkpoints, not extra owner commitments.

| Gate | Question / resolution needed | Owner | Due | Confidence |
|---|---|---|---|---|
| G1 | Which files/formats, compatible assets, contextual layers, tolerances and performance fixture satisfy scope? Include perforation history coverage, event/time precision and state mappings; approve manifest and ingestion spec. | Owner + implementer | Proposed Oct 28 checkpoint; before pilot adapter/real-data acceptance, not synthetic foundation | M |
| G2 | Which model/version is entitled, what is the actual credit balance, and does the selected Responses/tool protocol work? Follow the bounded Meta spec; no paid extraction/streaming dependency unless required by an approved slice. | Owner + implementer | Before FL-003-B live smoke and live assistant acceptance | M |
| G3 | Evaluation composition/thresholds are specified in the retrieval/assistant spec; approve source-backed gold questions/answers and tolerances. | Owner + implementer | Before FL-011-A gold retrieval acceptance and FL-011-C live evaluation | M |
| G4 | Indie track, public repository and three-minute video confirmed by owner; review remaining authenticated rules and per-file/provider/publication constraints. | Owner | 2026-10-28; recheck before submission | M |
| G5 | Which pinned parser/embedding/library versions and optional container layout pass the sample/resource checks? Record in relevant feature specs. | Implementer, owner approval for material changes | 2026-10-28, before affected integration | M |

**Score:** 0 unowned questions, 5 owned gates unresolved. This is an approved
product direction; the [architecture](ARCHITECTURE.md) and
[feature specs](specs/README.md) now define the system with explicit execution gates.

## 7. Implementation Guidance

### Suggested Approach

Use separate specs for data feasibility/import, trajectory exploration, equipment,
perforation history, contextual layers, linked charts and agentic retrieval.
Sequence trajectory/evidence contracts first; delegate independent or contract-ready
slices in parallel worktrees. Track actual prerequisites in the
[backlog](BACKLOG.md), not assumed ordering. Apply the
[versioned integration workflow](DEVELOPMENT_WORKFLOW.md) before marking work done.
Detailed API/schema/service design belongs in feature specs, not this brief.

### Known Risks

Data compatibility and geological coverage: H impact. Unbounded drawing-to-CAD
expectations: H impact. Document parsing and local memory: M/H impact. Grounded
catalog matching: H impact. Mitigations are evidence gates, supported-format
boundaries, explicit unknowns and bounded workloads, not optimistic promises.

### Milestones / Checkpoints

1. Review/integrate the [design and task sequence](../plan/architecture-fieldlens-1.md);
   qualify source-independent foundation while G1/G2 proceed separately.
2. First real vertical slice after G1: upload -> validated trajectory -> source.
3. Enriched slices: sourced equipment/history/context -> both charts -> agent tools.
4. Rehearsal after all real/live gates: fresh import, model evaluation, failure
   tests and submission check.

Effort cannot be estimated credibly before the data audit; these are checkpoints,
not a promise that the full scope fits the remaining time.

## Open Tensions

- **Full scope vs. incomplete data/time:** preserve all requirements; owner decides
  any reduction after G1 evidence, not the implementer silently.
- **Automatic reconstruction vs. reliable data:** automate validated paths, expose
  missing information, and block only affected engineering conclusions. Manual
  resolution remains deferred unless actual failures force an owner decision.
- **Grounded chat vs. web enrichment:** field facts come from uploaded evidence;
  external sources may supply product specifications, never invented installed state.

## Assumption Registry

| ID | Assumption | Confidence | Evidence / invalidation |
|---|---|---|---|
| A-1 | A compact compatible Volve subset covers every mandatory layer | M | Broad dataset exists; invalidated by missing surveys, logs or geological coverage |
| A-2 | Account supports the documented Meta capabilities within remaining credit | M | Public docs and owner credit statement; invalidated by entitlement/balance smoke test |
| A-3 | Local hardware can process selected documents while keeping UI responsive | M | Observed host resources; invalidated by representative import benchmark |
| A-4 | Licensed catalog sources can identify relevant equipment | M | Plausible workflow, no sample models yet; invalidated by ambiguous/obsolete/absent specifications |

`[ASSUMPTION-HEAVY: four load-bearing assumptions remain unvalidated. Do not claim full feasibility.]`

## Adversarial Self-Critique

1. **Coverage may be mistaken for compatibility.** Large Volve archives may not
   cover the same wellbores/dates. Watch: candidate manifest needs unsupported joins.
2. **Catalog identity may be mistaken for installed geometry.** Product variants
   differ. Watch: inferred dimensions lack a matching revision or installation record.
3. **Context layers may overwhelm the schedule.** Genuine reservoir data may require
   specialized formats. Watch: G1 needs an importer outside the accepted first slice.

## Revision Triggers

Reopen this spec if G1 cannot source a mandatory layer; Meta entitlement/pricing
changes affect G2; measured workload violates AC-9; or authenticated rules require
hosting/additional deliverables. Revise Scope/ACs/Dependencies with owner approval.

## Appendix

[Source assessment](SOURCE_ASSESSMENT.md) records evidence and verification limits.
[Technical baseline](TECHNICAL_BASELINE.md) records implementation direction.
[Feature template](specs/FEATURE_TEMPLATE.md) is the per-increment starting point.
