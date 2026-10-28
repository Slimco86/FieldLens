# Specification: Evidence-aware installed equipment reconstruction

> **Spec type:** Product/feature. **Backlog:** FL-007.
> **Load-bearing frameworks:** F1, F2, F3, F4. **Supporting:** F5, F6.
> **Date:** 2026-10-27. **Decision owner:** project owner.
> **Status:** Design complete; installed pilot assembly still unverified.
> **Zero-Question Score:** 0 unowned design questions; DF-9 acceptance remains gated.

## How to Read This Spec

Executor: placement/catalog contracts. QA: EQ tests. Owner: installed-evidence gate.
Covers project AC-4/8/9; consult [actual source assessment](../EQUIPMENT_DATA_FEASIBILITY.md).

## Notation Key

`[Validated]` = required truth boundary. `[Assumed: verify]` = proposed fixture/limit.
H/M/L are confidence; AC score 3 is binary, not proof of verified installation.

## 1. Outcome Statement

Selecting equipment reveals a correctly scoped historical instance with
attribute-level evidence or clearly labeled generic/unlocated limitations.
Verification: EQ-1 through EQ-6. Outcome score 3.

## 2. Scope

### IN Scope

Installed configurations, tubular envelopes, located device meshes, missing-data
states and bounded cited catalog matching. `[Validated: owner equipment policy]`

### OUT of Scope

Full mechanical CAD, invented internals, flow simulation, manufacturer identity
from appearance, automatic installation dates, and a generic-only successful demo.
Blender art polish is optional; evidence-backed equipment is mandatory.

### Scope Dependencies

FL-005-B source claims and FL-006-B scene/trajectory precede FL-007-A.
DF-9 must pass before real installed-equipment acceptance. Optional FL-007-B
Blender export requires an approved source/model asset assignment.

### Open Scope Tensions

Drilling assemblies contain real dimensions but are not permanent completions.
Keep run/configuration types separate, even when XML calls a component "tubing."

## 3. Acceptance Criteria

| ID | Type | Pass condition | Score | Annotation | Test |
|---|---|---|---|---|---|
| EQ-1 | Behavioral | Source-dimensioned casing/tubing follows validated MD ranges and IDs/ODs; clicking a component opens the right attribute evidence and effective configuration. | 3 | [Validated] | `test_equipment_placement`, browser evidence |
| EQ-2 | Behavioral | A catalog fixture fills only missing model-specific dimensions, cites exact variant/revision/page, and never changes installed depth/quantity/date. | 3 | [Validated] | `test_catalog_match` |
| EQ-3 | Negative | Unknown placement stays unlocated; generic dimensions are excluded from physical computation/export; drilling/design-only records cannot pass installed-state acceptance. | 3 | [Validated] | `test_generic_and_drilling_boundaries` |
| EQ-4 | Edge case | Conflicting OD/ID, invalid length, overlapping incompatible configurations, unavailable catalog and multiple variants expose affected issues without hiding unrelated valid components. | 3 | [Validated] | `test_equipment_conflicts` |
| EQ-5 | Non-behavioral | Required equipment is included in the scene AC-9 benchmark; field view uses instancing/shared materials and detail assets load only on demand. Generic/exaggeration labels remain visible. | 3 | [Assumed: verify workload] | equipment browser benchmark |
| EQ-6 | Dependency | One pilot configuration passes DF-9 with installed casing/tubing and a located discrete completion device; all required dimensions/placement open their evidence. | 3 | [Assumed: verify DF-9 threshold] | `test_pilot_installed_assembly` |

Synthetic source/catalog/generic fixtures prove fallback logic, not EQ-6.

## 4. Context and Decisions

Owner: `fieldlens-3d-motion`; paths `frontend/src/features/equipment/`,
`backend/fieldlens/equipment/` and tests. Source ambiguities return to ingestion;
bounded public model research routes to `fieldlens-research` separately.

Instance record: component UUID, bore/configuration ID and configuration kind
`installed/drilling/planned/unknown`, effective-time evidence, component type,
sequence, source/catalog model IDs, attributed dimensions and optional MD interval.
Dimensions and placement are independently valid/unknown/conflicting.
Stored `length` must distinguish individual device length from total string tally.
Assembly sequence uses explicit sequence claims, not XML ordering.

Render manifest chooses a registered primitive or reviewed GLB by type/model.
Tube paths use authoritative trajectory MD interpolation; scalar OD is metres,
ID <= OD and lengths positive when known. Preserve source precision; radius
exaggeration affects only the manifest's display transform.
Unknown component orientation is not a claimed installation orientation.
If an illustrative axial orientation is needed, label it display-only.

Catalog research uses only public manufacturer/model/variant identifiers already
documented in the source. Maximum three queries and five inspected pages per
missing-model request, 60 seconds wall time, disabled without explicit permission/
budget. Return verified match, alternatives, unavailable or budget-exhausted.
No arbitrary user/model URLs are fetched. Match facts attach to a catalog model,
never directly overwrite installation claims.

Optional Blender acceptance: documented build/export settings; metre scale,
part IDs/pivot/axes, valid GLB round trip, no external asset references, and bounds
within max(1 mm, 0.1% of source dimension). Maximum 50,000 triangles/device and
5 MiB/GLB; a field-view LOD <=2,000 triangles. These are proposed display budgets,
not engineering tolerances. Source/license approval precedes any model creation.

## 5. Failure Conditions

No documented model/placement -> generic/unlocated result, not speculative lookup.
DF-9 unavailable -> keep feature real-data acceptance blocked; do not relabel
the inspected F-4/F-7 drilling probes as a pilot production completion.
Worst misinterpretation: a beautiful GLB without installed evidence fails EQ-6.

## 6. Ambiguity Audit

Catalog identity, source dimensions, installation and mesh detail are separate.
Owner approves DF-9 and asset choice before real acceptance/optional Blender work.
No universal catalog or arbitrary CAD importer is required.

## 7. Implementation Guidance

FL-007-A delivers procedural geometry/inspector/fallbacks and EQ tests.
FL-007-B optional exports occur only after EQ-6 identifies an appropriate asset.
Planned checks: equipment Python and frontend tests, GLB inspection only if used,
type/build and integrated scene benchmark. No assets/tests have been produced.
Propose minor for new capability; no independent worker version allocation.

## Open Tensions

Required technical equipment evidence is not established merely by having a mesh.

## Assumption Registry

Pilot installed assembly is documented (M; DF-9). Source models can be matched
(M; EQ-2). Procedural envelopes suffice for the evidence available (H; revisit
only when approved drawings demand a different truthful representation).

## Adversarial Self-Critique

Tally length can be mistaken for one device: inspect field semantics.
Vendor BHI alone is not a model: require variant evidence.
Unknown placement can acquire a plausible default depth: test unlocated behavior.

## Revision Triggers

Reopen on absent installed evidence, incompatible historical model variants or
source drawings requiring geometry outside the approved primitive/asset set.
