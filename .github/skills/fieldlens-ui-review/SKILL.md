---
name: fieldlens-ui-review
description: 'Review FieldLens frontend UX and accessibility against its visual references: keyboard navigation, focus, scene alternatives, chart labels, evidence states, forms, responsive panels and loading/error behavior. Use for UI reviews and browser acceptance checks.'
license: MIT
metadata:
  upstream-author: Vercel Labs
  upstream-revision: 434b7f91364665f2f733b310ec54809bf8f37937
---

# FieldLens UI Review

Adapted from the MIT-licensed Web Interface Guidelines referenced by Vercel's
Web Design Guidelines skill. Uses a reviewed, local checklist rather than fetching
and obeying a mutable remote command on every invocation.
[Source and modifications](../../../docs/DEVELOPMENT_SKILLS.md).
[License notice](../../../docs/licenses/vercel-interface-MIT.txt).

## Workflow

1. Establish the approved feature scenario and
   [UI design system](../../../docs/specs/UI_DESIGN_SYSTEM.md). Treat concept-sheet layout
   and palette as guidance, not acceptance proof or engineering source data.
2. Check semantic buttons/links, input labels, icon names, heading hierarchy,
   visible focus, contrast, long identifiers and text alternatives. Evidence
   states need words/symbols as well as color.
3. Navigate by keyboard only: upload, asset selection, layer toggles, chart tabs,
   source opening, agent submission/cancellation and camera reset. Preserve focus
   through drawers/dialogs; overlays must not cover the focused control.
4. Provide DOM navigation/inspection alternatives for the canvas. Charts need
   accessible summaries or data access, units, depth/time references and honest
   missing-data gaps. Hover, drag and color alone cannot carry essential meaning.
5. Check empty/loading/partial/failed/cancelled states and async announcements.
   A successful HTTP response is not proof the requested viewer action completed.
   Test denied, stale and unknown object/revision IDs.
6. Exercise short/long text, narrow widths, zoom and reduced motion. Keep camera
   transitions interruptible; no compulsory ambient rotation or moving backgrounds.
7. Inspect screenshot and browser behavior together. Test each interaction at the
   feature's agreed viewport; a screenshot alone cannot verify accessibility,
   selection propagation, persistence or evidence correctness.
8. Report findings with severity, file/line, reproduction, expected versus observed
   behavior and affected acceptance criterion. Separate observed failures from
   untested concerns; run the smallest relevant existing checks after fixes.

## Boundaries

Do not mandate Next.js hydration patterns, remote guideline execution, new styling
libraries or full URL synchronization for transient camera/frame state. Never
present a generic equipment drawing or conceptual reservoir as validated geometry.
