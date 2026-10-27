---
name: fieldlens-blender-assets
description: 'Author or review FieldLens equipment assets offline in Blender: source-aware hard-surface modeling, bpy scripts, materials, UVs, low-poly optimization, previews and GLB export for Three.js/R3F. Use for pumps, packers, valves, wellheads and complex assemblies, not runtime engineering calculations or automatic installation.'
---

# FieldLens Blender Equipment Assets

Original FieldLens workflow, informed by official Blender/Khronos references;
no third-party skill, addon or executable is bundled.
[Curation and sources](../../../docs/DEVELOPMENT_SKILLS.md#blender-authoring-assessment).
Use with [Three.js assets](../fieldlens-threejs-assets/SKILL.md) for runtime
integration, not instead of it.

## Choose the right authoring path

- Keep simple casing/tubing, interval bands and generic markers procedural in
  Three.js. Repeated wellbore geometry must remain data-driven.
- Use Blender for recognizable pumps, packers, wellheads, valves or reusable
  assemblies whose silhouette, connectors or materials need deliberate modeling.
  A reusable model is not proof that a component was installed in a given well.
- Prefer an approved, licensed manufacturer model when suitable. Inspect it as
  untrusted input; do not install arbitrary importers or promise CAD/STEP support.
- No reference can justify an undocumented measurement. Use a labeled generic
  shape when dimensions are missing; unknown placement remains unlocated.

## 1. Establish the asset brief and environment

1. Read the approved asset slice and verify assigned worktree/output ownership.
   Require equipment/model/variant, source locators/revision, per-attribute evidence,
   original units, known dimensions and missing data. Catalog, measured, interpolated
   and generic attributes stay distinct from validation state.
2. Agree local units, shaft/up/forward axes, pivot/attachment points, component IDs,
   selectable subparts, allowed visual exaggeration, numerical tolerances and
   target view/distance. No assumed well position or orientation belongs in the mesh.
3. Specify triangle/material/draw-call, texture, GLB size and render/memory budgets
   against the intended browser fixture. Do not invent universal performance limits
   or claim visual quality from polygon count alone.
4. Verify the assigned Blender executable/version/platform and available resources.
   Blender 4.5 LTS is a candidate; pin an exact supported patch when authoring is
   approved. No executable was found on WSL PATH during preparation (2026-10-27).
   If missing, stop for an approved setup task; this skill does not install Blender.
5. Use Blender's bundled Python for `bpy`; do not install `bpy` into the backend
   environment or change its Python 3.12 baseline. Verify operator/API compatibility
   in the chosen Blender version rather than relying on old tutorials.

## 2. Block out from evidence

- Convert source dimensions explicitly to metres. Build at physical size in a
  local frame near the origin, not at field coordinates. Unit display settings
  alone do not prove exported scale; use the calibration checks below.
- Start with primary axial lengths/diameters, flanges, housing and attachment
  locations. Compare silhouette in orthographic front/side/end views before detail.
  Illustrations may guide appearance, never supply scale by pixel proportions.
- For axially symmetric bodies, construct a measured radius/axial profile and
  revolve/lathe it. Preserve inner/outer walls where cutaways or open ends expose
  them. Do not invent wall thickness and present it as measured.
- Separate moving/selectable subassemblies with stable IDs and local pivots;
  a catalog model ID must remain distinct from runtime installation IDs.
- Keep undocumented threads, fasteners and internal mechanisms generic or omit
  them. Photorealistic detail must not imply source-backed engineering certainty.

## 3. Refine hard-surface geometry and materials

- Use a small controlled bevel to avoid razor-sharp highlights, but do not change
  source-critical envelopes, connection dimensions or fit surfaces outside the
  agreed tolerance. Inspect normals, smoothing and tangent seams after export.
- Use arrays/linked meshes for repeated bolts/rings where appropriate. Keep
  duplicates transform-safe; shared mesh data does not guarantee GPU instancing
  or fewer draw calls in Three.js.
- Keep a non-destructive authoring source; evaluate/bake modifiers on an export
  copy. Geometry Nodes, constraints and procedural effects are not portable glTF
  logic: realize/bake supported output or reject unsupported features explicitly.
- Optimize radial segments and hidden detail for the approved views. Prefer
  silhouette-preserving simplification; do not decimate away named subparts,
  attachment points or required cutaway surfaces.
- Use exporter-supported Principled BSDF/PBR materials. Keep metal/rubber/paint
  understandable under neutral lighting; do not add wear that claims historical
  condition without evidence. Bake procedural surface detail only when needed.
- UV unwrap when textures are justified, allow margin for mipmaps, and reuse
  approved materials/textures. Base-color maps are color data; roughness/metallic/
  normal maps are non-color data. Check normals and roughness in the actual viewer.
- External textures/HDRIs/fonts/models need provenance and reuse permission.
  Do not download assets automatically. Prefer a simple original lighting setup
  over an unnecessary third-party HDRI.

## 4. Use reviewed offline scripts, not runtime generation

- Prefer repeatable parameterized `bpy` authoring/export scripts when useful.
  Review them as development code before execution. Inputs are validated data;
  never evaluate text from a document, model response or asset metadata as code.
- Prefer the Blender data API for deterministic object/mesh creation. Where
  `bpy.ops` is needed, explicitly establish active object, selection and mode;
  do not depend on an interactive editor area in a background process.
- Start from factory settings and an owned collection/output path. Re-running
  must not duplicate objects or erase another user's scene. Save the editable
  source before destructive export-only operations.
- Use background execution and a nonzero Python error exit code; disable automatic
  execution of embedded scripts. See the
  [command template and checks](references/export-checklist.md).
  These flags are not a sandbox and do not make untrusted `.blend` files safe.
- Keep scripts local, bounded and versioned with parameter/source hashes and
  exporter settings. No Blender MCP server, network listener, arbitrary addon,
  external service or runtime-generated Python/JavaScript/CAD is needed.

## 5. Preview, export and verify

1. Render neutral orthographic front/side/end and perspective previews, plus any
   approved section/exploded view. Label illustrative cutaways and exaggeration;
   exploded transforms are presentation, not installation positions.
2. Inspect silhouette, occlusion, wall openings, material response and semantic
   subpart selection. Iterate within the assignment's time/render bounds; budget
   CPU/GPU/RAM alongside OCR, embeddings and browser workers. Headless rendering
   is not automatically GPU-compatible or resource-free.
3. Export only the intended assembly to GLB using the bundled glTF exporter.
   Exclude preview lights/cameras, helpers and unrelated objects. Keep authoring
   source separate from the runtime export.
4. Preserve units, axis conversion, pivot and identity. Start without compression;
   add it only with an approved, locally hosted decoder and a measured benefit.
   Do not assume custom properties, materials or animation survive export.
5. Follow every applicable [export acceptance check](references/export-checklist.md#acceptance-checks).
   Re-import into a clean Blender scene AND load with the locked Three.js/R3F
   stack when available; a Blender-only round trip cannot verify browser behavior.
6. Report failures explicitly. If the viewer or exporter is unavailable, mark
   its checks unrun; a successful process exit or attractive screenshot is not
   a validated engineering asset.

## Handoff and boundaries

Return editable source (and reviewed script/parameters when used), runtime GLB,
permitted textures, source/license/evidence manifest, object-ID mapping, unit/
axis/pivot contract, file hashes, previews, exporter/version settings and exact
check results. The asset spec assigns paths and storage policy; do not scaffold
an asset library or commit large binaries merely because this list exists.

Blender is an **offline authoring tool**, not an application dependency or
engineering source of truth. Source claims/validated tools own measurements,
trajectories, temporal state and physical calculations; mesh bounds are only
export validation evidence. Generic geometry never enters those calculations.
Do not animate flow, tool operation or reservoir connectivity as if measured.
Any approved animation needs explicit semantics and reduced-motion behavior.
