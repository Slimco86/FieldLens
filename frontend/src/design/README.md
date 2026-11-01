# Design system (TASK-034, UI-1 to UI-9)

Light theme only, large-screen layout (1920x1080 primary, 2560x1440). Spec: `docs/specs/UI_DESIGN_SYSTEM.md`.

- `tokens.ts` is the single source of colors, type scale, spacing (8 px grid), radii, shadows, motion and layout
  sizes. `cssVariables()` publishes them as `--fl-*`; `theme.ts` maps them into the one Mantine theme object.
  Outside this folder write `var(--fl-...)` or Mantine style props (`p="md"`), never a color or a pixel literal:
  `tests/tokens.test.ts` scans `src/` (UI-1) and fails the unit tests. `1px`/`2px` strokes are
  `--fl-border-width` and `--fl-border-width-strong`.
- Contrast: `contrastPairs()` lists every text/background and UI-part pair used; the same test enforces WCAG 2.2 AA
  (4.5:1 text, 3:1 UI). Add a pair there when you add a token pairing.
- Components: `StatusChip` / `Chip` / `EvidenceClassChip` (text label plus icon, never color alone; vocabularies are
  typed against the generated DTO enums), `Callout` (notice/warning/error block), `LoadingState` / `EmptyState` /
  `ErrorState` (skeleton, designed empty state, alert with request ID and retry), `KeyValueList`.
- Fonts and icons are self-hosted (`@fontsource-variable/inter`, `lucide-react` named imports). Nothing is loaded from
  a CDN; `tests/e2e/shell.spec.ts` asserts zero external requests.
- Tests render inside `tests/render.tsx` (`DesignProvider test`), which disables portals and transitions in jsdom.
