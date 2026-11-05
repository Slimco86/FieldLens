---
name: fieldlens-r3f
description: 'Implement or review the FieldLens React Three Fiber viewer: Canvas, camera controls, picking, highlights, resource ownership, loading, frame-loop behavior and rendering performance. Use for R3F/Drei interaction and scene integration.'
license: MIT
metadata:
  upstream-author: three-agent-skills
  upstream-revision: f950f95ae3b13581546e6d6d8b2f88a08eb3e577
---

# FieldLens R3F

Adapted from React Three Fiber Best Practices; physics, decorative animation,
postprocessing and additional state/debug libraries are deliberately not adopted.
[Source and modifications](../../../docs/DEVELOPMENT_SKILLS.md).
[License notice](../../../docs/licenses/three-agent-skills-MIT.txt).

## Workflow

1. Read the approved viewer spec and
   [UI design system](../../../docs/specs/UI_DESIGN_SYSTEM.md). Verify the installed
   React/R3F/Drei compatibility and use the stable WebGL2 path.
2. Establish geometry ownership, local origin, axis mapping and physical scale
   before mounting objects. Meshes must carry stable domain IDs, not scene-index
   identities. Geometry input must already be validated by engineering code.
3. Size the Canvas through its container. Choose demand rendering for a static
   scene when appropriate; call `invalidate()` after imperative changes. Continuous
   controls/animation need the correct frame-loop integration.
4. Mutate refs in `useFrame`; never call React state setters for frame-rate changes.
   Use elapsed delta for animations, not fixed increments. Keep parsing, proximity
   calculations and allocations out of the frame loop.
5. Reuse resources deliberately. Visibility toggles avoid repeated construction,
   but hidden objects can still consume memory and run callbacks. Dispose only
   resources this component owns; shared geometry/materials need an explicit owner.
   A `primitive` object and cached GLTF assets need special ownership review.
6. Map picking/highlight actions back to validated IDs and current revisions.
   Occlusion and pointer propagation must not select a different well underneath.
   Provide keyboard-accessible equivalents via the DOM asset tree and controls.
7. Pair Suspense with meaningful progress and error handling. Do not place arbitrary
   DOM elements directly into the Three scene. Keep unavailable models visibly
   unavailable; do not turn failed loads into unlabeled generic equipment.
8. Measure the approved orbit/selection scenario. Check frame time, draw calls,
   resource counts and repeated mount/unmount cycles. Record browser, viewport,
   dataset and measurement method; verify local-origin precision.

## Boundaries

No automatic rotation, Rapier physics, Leva, Zustand, WebGPU, environment downloads
or postprocessing dependencies without a feature requirement. Camera focus and
highlight requests do not authorize changing engineering records. Respect reduced
motion, preserve user camera control, and acknowledge completed viewer actions.

Use the [Three.js asset skill](../fieldlens-threejs-assets/SKILL.md) for geometry
construction/export rather than duplicating that workflow.
