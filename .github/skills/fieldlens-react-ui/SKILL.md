---
name: fieldlens-react-ui
description: 'Build, review, or optimize FieldLens React and TypeScript UI: asset selection, linked panels, charts, evidence viewers, data fetching, render performance, and Vite bundle size. Use for frontend components, not Three.js frame-loop work.'
license: MIT
metadata:
  upstream-author: vercel
  upstream-revision: 6ec269328bc400712ee225a173a14b6b29128df7
---

# FieldLens React UI

FieldLens adaptation of Vercel React Best Practices. This is a Vite client with
a Python API, not a Next.js application.
[Source and modifications](../../../docs/DEVELOPMENT_SKILLS.md).
[License notice](../../../docs/licenses/vercel-skills-MIT.txt).

## Workflow

1. Read the approved feature spec and the
   [visual references](../../../docs/design/README.md). Identify the selected
   dataset revision, stable asset IDs, loading/error states and evidence links.
2. Trace shared selection across the asset tree, scene, chart and document panel.
   Store IDs and small UI state; keep bulk logs, meshes and source buffers outside
   React state. Derive display state instead of duplicating it in effects.
   Historical perforation views share as-of time/precision and dataset revision.
   Preserve log/series acquisition dates; unknown history is not zero or "closed."
3. Start independent requests together. Cancel or disregard stale responses when
   selection changes. Do not display a previous well's response under a new name.
   Cache/deduplicate through the project's existing data layer, not a new library.
4. Lazy-load heavy chart/PDF/inspector views with React lazy/Suspense or dynamic
   imports appropriate to Vite. Provide visible loading and failure boundaries.
   Avoid barrel imports that pull unused engines into the initial bundle.
5. Subscribe only to required state. Use refs for transient values and stable
   identities for list keys. Profile before adding memoization; do not use
   memoization to conceal stale values or broken dependencies.
6. Keep expensive updates interruptible. A deferred chart must identify the
   selection/revision it still represents; never temporarily mislabel its data.
7. Test fast selection changes, missing series, failed requests, panel reopening,
   long identifiers and evidence navigation. Run the affected interaction tests,
   TypeScript check and build using commands actually present in the project.

## Boundaries

- Do not add Next.js, server components/actions, a Node API, SWR or another store
  just because upstream examples use them.
- Do not cache engineering results without dataset/source revision keys.
- Include historical time/precision in state cache keys and reject stale time-selection
  responses, just as for asset changes; do not silently substitute latest state.
- Do not suppress errors, use unsafe casts, or introduce static mock data as live data.
- Leave per-frame updates to R3F refs; this skill does not own GPU lifecycle.
- Report measured bottlenecks and validation results, not assumed performance wins.
