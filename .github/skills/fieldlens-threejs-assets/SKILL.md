---
name: fieldlens-threejs-assets
description: 'Create, import, inspect, or optimize FieldLens procedural Three.js equipment meshes and GLB/glTF assets. Use for tubing, casing, packers, pumps, perforation markers, mesh materials, asset validation, and source-aware generic geometry.'
license: Apache-2.0
metadata:
  upstream-author: terminal-skills
  upstream-revision: 3bfbf7f76459d89422eddc0e5f572ad0e6c393c9
---

# FieldLens Three.js Assets

Modified FieldLens adaptation of TerminalSkills' Three.js skill, not an unchanged
upstream installation. Product configurator/globe demos, unsafe casts, speculative
version requirements, automatic CDN fetching and unrelated visual effects are omitted.
[Source and modifications](../../../docs/DEVELOPMENT_SKILLS.md).
[Apache-2.0 license](../../../docs/licenses/terminalskills-Apache-2.0.txt).

## Workflow

1. Read the approved feature contract. Classify each attribute independently:
   source-measured, catalog-derived, interpolated or generic. Identify the source
   revision, units, dimensions, placement, orientation and known missing fields.
2. Select the least complex shape that communicates the documented equipment:
   cylinders/tubes, interval bands or a validated imported asset. Do not derive
   engineering dimensions from an illustration's pixel proportions.
3. Keep physical parameters separate from tessellation and display exaggeration.
   Use server-derived trajectory positions/tangents for equipment placement.
   A smoothed display spline must not redefine the survey or measured depths.
   Perforation markers consume the selected as-of state/dataset revision from
   deterministic tools; do not render every historical event simultaneously.
   Follow the [history spec](../../../docs/specs/PERFORATION_HISTORY.md): repeated
   events must not double-count length, and shut-in must not erase physical coverage.
4. For imported GLB/glTF, inspect units, orientation, bounds, topology/materials,
   external resources and licensing. Reject unsupported or unsafe dependencies.
   Self-host approved decoders; never fetch arbitrary model-provided URLs.
5. Use compatible `three/addons` APIs from the locked Three.js version. Configure
   color textures as sRGB and data maps with the appropriate linear interpretation.
   Reuse geometry/materials and instance repeated shapes when measurement justifies it.
6. Preserve picking IDs and evidence metadata through instancing, merging and
   export. Check normals, finite coordinates, expected physical dimensions and
   local-origin transforms. Record simplification/compression parameters.
7. Make generic shapes visibly generic. Unknown location means an unlocated
   inspection representation; no fabricated well depth. Generic mesh bounds
   must not become input to distances, clearance or other engineering calculations.
8. Test all three equipment evidence tiers, export/reload where applicable,
   repeated resource disposal and selection. Compare against deterministic
   dimensions/placement fixtures, not only a screenshot.

## Boundaries

The runtime agent supplies validated declarative tool arguments, never generated
JavaScript, Python, CAD scripts or scene programs. Blender/build123d can be
separately approved offline asset tools; they are not prerequisites for tubes or
generic markers. UI meshes do not provide reservoir simulation or certified
anti-collision analysis.
