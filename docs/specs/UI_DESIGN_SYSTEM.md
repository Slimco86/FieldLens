# Specification: Demo-grade application shell and visual design system

> **Spec type:** Product/feature.
> **Load-bearing frameworks:** outcome, acceptance, scope, context. **Supporting:** failure conditions, ambiguity audit.
> **Date:** 2026-10-30. **Author:** orchestrator (draft). **Decision owner:** project owner.
> **Status:** Approved by the owner on 2026-10-30 (section 6 records the decisions); implementing is not yet started.
> **Backlog ID:** FL-021 (TASK-033 approval, TASK-034 shell, TASK-037 polish). **Delivery state:** ready.
> **Approved spec revision/date:** r1, 2026-10-30 (owner answers to all section 6 questions). **Integration version:** pending.
> **Zero-Question Score:** 0 unowned questions blocking TASK-034. Sequencing (owner, October 30): upload and parsing come first, so TASK-034 follows TASK-039 and TASK-009; the exact brand color ramp is proposed by the implementer and signed off at the browser checkpoint.

> **Owner amendment, October 31 (dispatch):** the owner wants incremental, testable UI now. TASK-034 starts without
> waiting for TASK-039: remove/replace and project-delete controls are not shown until their backend exists (UI-6,
> PW-1: no fake controls) and arrive in TASK-049. A **data overview** (UI-13) is added as TASK-048, built on the
> existing project, document, job, coverage, identity, series and issue APIs only. Project edit stays; project
> deletion is PW-9 (backend TASK-039) and its confirmation dialog is TASK-049. The Mantine kit, Inter and
> lucide-react decisions below stand.

## How to Read This Spec

Owner: outcome, look-and-feel decisions (section 6). Frontend implementer: scope, tokens,
layout contract and ACs. QA/reviewer: ACs, failure conditions and the visual checklist.
Related: [visual references](../design/README.md) (conceptual only), [project workspace](PROJECT_WORKSPACE.md)
(PW-1/8 behavior that must not regress), [data quality](DATA_QUALITY.md), [trajectory viewer](TRAJECTORY_VIEWER.md).

## Notation Key

`[Validated]` = owner/source confirmed; `[Assumed: verify]` = proposed, owner approves in TASK-033.
AC score 3 = binary and outsider-testable; 2 = checklist-reviewed by someone other than the implementer.

## 1. Outcome Statement

After this increment the app opens into one coherent, readable light-theme product. A left sidebar manages
projects (list, create, edit, switch). Opening a project shows top tabs: **Sources** (manage the project's files:
upload, list, edit classification, remove with confirmation, replace; the backend arrives first in TASK-039), **Reconstruction** (the results of file
processing, information extraction and relationship building, shown as a logical log of agentic parsing) and
**Explore** (the human interface to the reconstructed 3D model with charts and the chat assistant). Everything is
built from one theme and a free open-source component kit, with documented regions inside Explore where the evidence
tree, 3D stage, inspector and assistant mount. A non-developer can create a project, upload files, read job/revision
status and see what is unavailable and why, without it looking like an unstyled HTML page.
Verification: UI-1 through UI-12; final visual judgment is the owner's browser checkpoint.
Outcome score: 3 for UI-1..9, 11 and 12; UI-10 combines a reviewer checklist with owner sign-off.

## 2. Scope

### IN Scope

- `[Validated: owner, October 30]` The current UI (a 136-line default-styled stylesheet, no layout structure,
  colors or design system) is not demo-suitable and gets proper UI work.
- `[Validated: owner, October 30]` Light theme only, vivid but conservative brand color suited to the oil and gas
  industry, large-screen focus, Mantine as the component kit, Inter and lucide-react (section 6).
- `[Validated: owner, October 30]` Navigation: project management lives in a left sidebar; opening a project shows
  top tabs Sources / Reconstruction / Explore (section 4 defines what each contains).
- Design tokens through one Mantine theme object plus CSS custom properties (color, type scale, spacing, radius,
  elevation, motion), with self-hosted fonts and icons.
- Application shell: left sidebar (brand, project list/management), top bar (project name, revision status, tabs)
  and, inside Explore, a workspace grid with four named regions: `tree`, `stage`, `inspector`, `dock`.
- Shared components and states from the kit, wrapped only where the product needs it: status chips for source/
  validation/job/evidence classes, empty/loading/error/partial states, upload dropzone, tables, dialogs, notifications.
- Evidence-state vocabulary as one component set: source/validation/job status and the evidence classes plus unknown,
  using text and icon, never color alone.
- Redesign of the existing Projects and Sources/upload/jobs/revisions screens with unchanged behavior, plus the
  already-supported classification edit. Unavailable capabilities (Reconstruction, Explore) show their real prerequisite.
- Polish pass over the integrated app near the end (TASK-037).

### OUT of Scope

- New product behavior, new API/DTOs or fake data/controls. File removal/replacement UI is not shown until its backend
  exists (TASK-039 precedes TASK-034, so remove/replace controls are expected in the Sources tab); placeholders state the prerequisite (consistent with PW-1: no fake controls).
- The 3D scene, charts, PDF viewer, chat, reconstruction log and review UI themselves (FL-006/010/011/016/022); they
  consume the shell.
- Dark theme, user theming, i18n, mobile/touch and small-screen layouts (large-screen demo focus).
- Bespoke components where the kit already provides one; custom CSS is limited to layout and theme tokens.
- Brand identity work beyond a wordmark and the brand color.

### Scope Dependencies

FL-004/015/005-A are integrated (0.8.0), so there is existing behavior and a test suite to preserve.
No dependency on parsers, agents or data. Later UI tasks depend on TASK-034 (see the backlog).

### Open Scope Tensions

1. **Redesign timing vs. TASK-009 (evidence UI).** Both touch `frontend/src`. Serial development means one writer;
   resolution: TASK-034 first if integrated by TASK-009's dispatch, else TASK-009 lands functionality on the old
   styles and TASK-034 absorbs its screens. Owner: orchestrator, recorded at dispatch.
2. **Polish scope creep.** Resolution: UI-10 is a checklist plus one owner sign-off; open-ended taste
   changes after sign-off are a new backlog item.

## 3. Acceptance Criteria

| ID | Type | Given / when / then or measured threshold | Score | Annotation | Test |
|---|---|---|---|---|---|
| UI-1 | Behavioral | All colors, font sizes, spacing, radii, shadows and durations used by application styles come from the Mantine theme object / CSS variables in the design folder; a check fails on literal colors or off-scale pixel values outside it. | 3 | [Validated: owner wants consistency across pages and tabs] | `tokens.test` (style scan) |
| UI-2 | Behavioral | At 1920x1080 and 2560x1440 each view fits without page-level horizontal scroll or clipped primary controls; the Explore stage keeps priority and the inspector/dock collapse to toggles. Below 1600 px width is unsupported for now (not verified, no responsive requirement). | 3 | [Validated: owner, large-screen focus] | Playwright screenshots + bounding-box assertions |
| UI-3 | Non-behavioral | Every text/background token pair used meets WCAG 2.2 AA (4.5:1 text, 3:1 large text and UI components); axe-core reports zero serious/critical issues on every view in the loaded, empty and error states. | 3 | [Assumed: verify] | contrast script over tokens; `@axe-core/playwright` (dev-only dependency) |
| UI-4 | Behavioral | Every async view uses shared loading (skeleton), empty, error and partial states; no bare "Loading..." paragraph or raw error text remains; errors keep their request ID and a retry action. | 3 | [Assumed: verify] | component tests + grep for removed patterns |
| UI-5 | Negative | Existing behavior is unchanged: all pre-change Vitest and Playwright checks for PW-1/2/5/8 and IN-1/3/4/5/7 pass with selectors updated only to accessible names/roles; no assertion is deleted or weakened. | 3 | [Validated] | full `npm --prefix frontend run test` and `test:e2e`; diff review by QA |
| UI-6 | Negative | Unavailable capabilities (Reconstruction, Explore, empty regions) state their real prerequisite derived from project revision pointers; no placeholder shows invented assets, numbers or enabled-looking dead controls. | 3 | [Validated] | `project-navigation.spec.ts` extended |
| UI-7 | Behavioral | Source, job, revision, validation and evidence-class statuses render through one chip component with text label and icon in addition to color, and with a 3:1 contrast against its background in grayscale. | 3 | [Assumed: verify] | component tests + grayscale screenshot check |
| UI-8 | Non-behavioral | The built app makes zero external network requests (fonts, icons, scripts all local) and its initial JavaScript stays within the budget below; heavy libraries (3D, charts, PDF.js) are lazy chunks. | 3 | [Assumed: verify; Mantine raises the baseline, so the budget is set from the measured TASK-034 build, ceiling proposed <= 250 KB gzip initial] | Playwright request assertion; `vite build` size report |
| UI-9 | Non-behavioral | Keyboard focus is always visible with a token-defined ring; tab order follows the visual order; `prefers-reduced-motion` disables non-essential motion; skip link and landmarks survive the shell. | 3 | [Validated: existing a11y baseline] | Playwright keyboard flow; reduced-motion emulation |
| UI-10 | Behavioral | At 1920x1080 and 2560x1440 a reviewer other than the implementer scores the screenshots against the visual checklist in section 7 with no blocker; the owner records sign-off in the browser checkpoint. | 2 | [Assumed: verify] | reviewer report + owner checkpoint |
| UI-11 | Behavioral | Inside Explore the four regions (`tree`, `stage`, `inspector`, `dock`) are documented layout components with collapse behavior; a test mounts a dummy panel in each without changing shell code, and an empty region renders nothing misleading. | 3 | [Assumed: verify] | `workspace-regions.test` |
| UI-12 | Behavioral | The left sidebar lists, creates, edits and switches projects; opening a project shows exactly the tabs Sources / Reconstruction / Explore, selected by URL and keyboard, and switching projects resets tab state and invalidates pending requests (PW-8 preserved). The Sources tab offers only supported actions (upload, list, classification edit); Reconstruction and Explore state their prerequisite until their features exist. | 3 | [Validated: owner navigation model] | `project-navigation.spec.ts` extended |
| UI-13 | Behavioral | A project **Overview** (the first view of the Sources tab, above the file table) shows from existing APIs only: counts of documents by processing state and by detected format, extraction coverage per record kind, issues by severity with the first items linking to their source locator, the resolved wells and wellbores with record counts per kind (identity API), the available log and production series per wellbore (series API: names, units, index range, sample counts, stated-vs-missing units) and the depth-default warnings; it states what is not available yet (equipment, reconstruction, scene) with its real prerequisite; every number is traceable to an API field (no client-side invention), every count is reproduced exactly against the API in a test, and a project with no data shows a designed empty state. | 3 | [Validated: owner request, October 31] | Vitest (fixtures from the generated types) + Playwright against a real lane with the seeded real subset |
| UI-14 | Behavioral | Owner request November 1. The Sources files table has separate **Your labels** and **Suggested labels** columns (each with text, icon and origin; suggestions are never shown as confirmed) and a separate **Tags** column; SHA-256, byte size detail and other identifiers move to an expandable row detail that stays keyboard-reachable and copyable. Rows are multi-selectable (checkbox column, select-all for the current filter); a bulk action assigns, adds or removes categories for all selected documents in one confirmation, reports per-document success/failure, and uses only the existing per-document category API unless the spec adds a batch endpoint. Upload-time selection offers the same batch assignment before sending. | 3 | [Proposed: owner request, November 1] | Vitest (columns, bulk apply, partial failure) + Playwright keyboard-only flow + axe |
| UI-15 | Behavioral | Owner request November 1. The Reconstruction tab opens with a **pipeline panel** that states the project's stage from existing APIs: (1) import and verification, native parsing and text indexing run automatically after upload with per-document state; (2) a deterministic **readiness checklist** per resolved wellbore (trajectory stations present, equipment sources, perforation events, production, logs, open conflicts) with each item `ready`, `gap` or `blocked` and its source locator; (3) an explicit **Start reconstruction** action that is disabled with the exact unmet condition until the minimum holds (no import or parse job running or failed-unseen, at least one wellbore identity resolved and at least one wellbore with a validated trajectory) and that lists any optional model-read steps (for example scanned completion pages) with their remaining-budget estimate and a separate confirmation; (4) after start, the activity log (AX-10), then review and publish. Gaps never block unrelated wellbores. | 3 | [Proposed: owner request, November 1; minimum conditions and the start/estimate contract to be agreed in the reconstruction spec] | Vitest (each readiness state) + Playwright against the seeded real subset |

> UI-13 traceability (TASK-048): `frontend/src/features/overview/` + `frontend/tests/overview.test.tsx`; Playwright/axe against a real lane is still open for independent QA. Series are grouped by the wellbore label as written (not mapped to resolved wellbores); issues are read per document because no project-wide issues API exists.
>
> UI-15 stage order, gates and owner decisions D1..D6 (processing without a label, OCR only if cheaper and faster, 500-page bound, trajectory as the minimum, unlocated (0, 0) display origin, AI merge review) are defined in [PROCESSING_FLOW.md](PROCESSING_FLOW.md).
>
> UI-15 as built (TASK-053, frontend only): the **Processing pipeline** panel sits in the Sources tab after the Overview (`features/pipeline/`). It shows the server's start-gate checklist (pass/warn/fail with the server's codes and messages; surface location is a warning, never a block), per-wellbore data exposure with truncation notices, and document processing (select, estimate, a separate "Confirm and start" step, per-document progress, cancel, retry). The Reconstruction tab still has no start action and merge-proposal review is not part of it. Confirm is the single call that starts a run (the API has no separate start endpoint); verified with mocked fetch only.
>
> UI-16 (TASK-063, [RECONSTRUCTION_TAB.md](RECONSTRUCTION_TAB.md)) supersedes that placement: the Overview (UI-13) and the pipeline panel are **removed from the Sources tab**, which now holds only the project header, the tabs, the upload section, the source revision and the revision files (with per-file re-run extraction). The **Reconstruction** tab (`features/pipeline/ReconstructionPanel.tsx`) lists identified wellbores in one table (ready first, highlighted and badged "Ready"; "Block not stated" badge; columns Wellbore, Readiness, Records per category, Sources, Action; gaps, conflicts and findings only in an expandable detail row), with per-wellbore Process and Process all ready wellbores. Readiness is the server's start gate; Process only requests an estimate for the documents carrying that wellbore's data (from exposure groups) that still need processing; the existing separate Confirm step and document processing runs follow below. A run is a stub step, not reconstruction. The Sources links switch to the Sources tab and focus the file row when it is in the loaded rows. The Overview code and `overview.test.tsx` were removed with it; verified with mocked fetch only.
>
> UI-17 (TASK-067, [RECONSTRUCTION_RUN.md](RECONSTRUCTION_RUN.md) RR-7/RR-8) changes the Reconstruction tab: the "Records per category" column is gone (columns Wellbore, Readiness, Sources, Action); the Sources column shows each category once as a heading with its record count ("Trajectory - 645 records") followed by its files, each with its own count, first human locator and a link to the file in Sources. The **Document processing** pane and the stub run list/run detail are removed from the UI (the 0.26.0 backend stays), and nothing is called "Processed". Ready rows show a visible but disabled **Reconstruct** button (description "Reconstruction start arrives in the next update") and a disabled "Reconstruct all ready wellbores (n)" sits above the list; non-ready rows keep the server reason. TASK-069 wires them. Per-file Re-run extraction in Sources is unchanged. Verified with mocked fetch only.

Definition of done: all ACs pass with recorded commands/results; owner browser checkpoint recorded; integration
follows the [workflow](../DEVELOPMENT_WORKFLOW.md) (independent acceptance, version/changelog, backlog reconciliation).

## 4. Context and Decisions

- Executor profile: `fieldlens-frontend` (React 19, strict TypeScript, Vite); skills `fieldlens-react-ui`, then
  `fieldlens-ui-review` for the reviewer. Glossary: *tokens* = named design values; *region* = named layout slot.
- Decisions already made: Vite/React/strict TypeScript; scene-first layout, one selection across tree/scene/charts/
  evidence, visible revision/reference/unit context ([visual references](../design/README.md), conceptual only);
  honest unavailable states; no new dependency without a demonstrated requirement (project rule).
- Component kit decision (orchestrator, authorized by the owner October 30): **Mantine** (`@mantine/core`,
  `@mantine/hooks`, `@mantine/dropzone`, `@mantine/notifications`; MIT; npm lists 9.7.4 with a React `^19.2` peer,
  matching our React 19). Rationale: it ships the pieces this product needs (app shell, tabs, tables, dropzone,
  notifications, skeletons, modals, a CSS-variable theme with one object for tokens), is accessible by default and
  has no runtime dependency on Tailwind. Rejected: shadcn/ui (Radix + Tailwind: copy-in components and a new
  styling system to maintain), Ant Design/MUI (heavier bundles and harder to keep a restrained look), Radix Themes
  (no dropzone/app-shell/table). Mantine's chart package is not used; ECharts stays the chart library. Risks:
  bundle size (UI-8 budget is measured from the first build) and ongoing major-version drift (pin exact versions,
  lockfile).
- Visual direction (owner): light theme for contrast; a vivid but conservative brand color for oil and gas, modern
  and not neon. Proposal for the implementer to realize and the owner to sign off from screenshots: a cobalt/azure
  blue ramp (anchor near `#1B5FD6`, about 5.7:1 against white) for primary actions and selection; cool neutral grays;
  conventional semantic colors; one warm amber reserved for selection/attention in the 3D scene and charts; a
  colorblind-safe evidence-class palette always paired with an icon and text. Dashboard readability practices: 14 px
  base text, 8 px spacing grid, restrained radii, thin borders over heavy shadows, tabular numerals and right-aligned
  numbers for measurements with units in the header, monospace for IDs/hashes, one primary action per view, limited
  palette, motion 120-200 ms. The 3D stage uses a light neutral background; line/mesh colors are chosen to keep
  3:1 contrast on it.
- Typography and icons (owner): self-hosted Inter variable (`@fontsource-variable/inter`) and `lucide-react`
  (named imports); no CDN, no icon fonts.
- Layout contract (owner navigation model): left sidebar with the brand, project list and project management
  (create, edit, switch); a project opens to top tabs Sources / Reconstruction / Explore. **Sources** = file management
  table with upload dropzone, job/revision status, classification edit, and remove (with an irreversible-deletion confirmation) and replace (INGESTION IN-9/IN-5).
  **Reconstruction** = results of processing, extraction and relationship building as a logical log of agentic
  parsing plus candidates and review (FL-022 TASK-038/040, FL-016 TASK-026). **Explore** = 3D stage with `tree | stage |
  inspector` regions and a collapsible `dock` for the assistant, plus the production and log charts; collapsed
  regions release their space to the stage.
- Implementation shape: `frontend/src/design/` (theme, global styles, status/evidence components),
  `frontend/src/app/shell/` (Shell, Sidebar, ProjectTabs, Explore workspace regions); feature folders use kit
  components and the design wrappers, not raw CSS. Mantine CSS plus Vite-native CSS Modules for layout only; no
  other CSS framework.
- Delegation: one writer, one branch; ownership `frontend/src/{design,app,features/projects,features/uploads}`,
  `frontend/tests`, `frontend/package.json` for approved dev dependencies only. No backend/contract change; if a
  DTO were needed, stop and return to the orchestrator. Isolated DB/ports per the dev-tooling lanes.
- Model routing: Sonnet 5.5 / medium `fieldlens-frontend` (interconnected UI work); verify actual host resolution
  at dispatch (TASK-001 policy). Independent acceptance by `fieldlens-qa` using `fieldlens-ui-review`.
- Contracts: none changed; status/evidence vocabularies reuse generated DTO enums (`frontend/src/api/generated.ts`).
- Historical semantics: not applicable here; the shell reserves a header slot for the selected as-of time and
  dataset revision but shows nothing until the features that own them exist.
- Agent/UI effects: not applicable; the assistant dock is a region only.

## 5. Failure Conditions

1. **Behavior regression hidden by a restyle.** Selectors or assertions are loosened until tests pass. Prevent:
   UI-5 requires assertion-for-assertion parity reviewed by QA; any removed check needs owner approval.
2. **Looks good only in screenshots.** Contrast, focus or collapse fails under keyboard/zoom/viewport change.
   Prevent: UI-2/3/9 are measured, not judged; zoom 200% is reviewed under UI-10.
3. **Fake-looking completeness.** Placeholders imply features exist. Prevent: UI-6; reserved regions render nothing.
4. **Design drift.** Later features hard-code colors or spacing. Prevent: UI-1 scan runs in lint/CI for all of
   `frontend/src`; TASK-037 re-checks.
5. **Dependency bloat or network use.** Fonts/icons from a CDN, large UI kit. Prevent: UI-8 and section 6 approval.

Failures return to the implementer; QA re-verifies the repaired candidate; the owner is escalated for decisions
in section 6 or for sign-off disputes. Never mark verified from screenshots alone.
Worst misinterpretation test: a change that only swaps colors/fonts passes UI-1/3 but not UI-2/6/7/11 or the
shell-structure outcome, so those criteria are kept binary.

## 6. Ambiguity Audit and Owner Decisions (TASK-033, answered 2026-10-30)

| # | Question | Owner decision `[Validated: owner, 2026-10-30]` |
|---|---|---|
| 1 | Theme | Light theme, for better contrast; no dark theme now. |
| 2 | Accent/brand | Vivid but conservative color suited to oil and gas; modern, not cyberpunk. Realized as the cobalt/azure proposal in section 4; the implementer supplies the exact ramp and the owner signs off from screenshots. |
| 3 | Typography | Self-hosted Inter, conservative and compatible with dashboard readability practice (section 4). |
| 4 | Icons | `lucide-react`. |
| 5 | Dependencies | Delegated to the orchestrator; minimize custom components and keep consistency across pages/tabs. Decision: Mantine (section 4) plus `@fontsource-variable/inter`, `lucide-react` and dev-only `@axe-core/playwright`. |
| 6 | Navigation model | Left sidebar manages projects; an opened project shows top tabs Sources / Reconstruction / Explore with the contents in section 4. |
| 7 | Supported viewports | Large screens only for now (1920x1080 primary, 2560x1440). |

Source removal/replacement semantics were decided October 30 (INGESTION IN-9). Project deletion/archiving stays out of scope until the owner asks for it.

## 7. Implementation Guidance

Smallest approach: (1) install the kit, land the theme and the shell (left project sidebar + project tabs) with the
existing views mounted unchanged; (2) migrate Projects, then Sources/upload/jobs/revisions to kit components
(dropzone, tables, chips, notifications); (3) add the Explore region layout, states and region tests; (4) run axe,
request, contrast and viewport checks and record the measured bundle; (5) screenshots for the reviewer.
Checkpoints: after (1) the full existing suite passes; after (3) UI-1/4/6/7/11/12; after (4) UI-2/3/8/9.
Do not claim proposed commands exist; add the token scan and checks to existing `lint`/`test` scripts.

Visual checklist for UI-10: clear hierarchy (one primary action per view); consistent spacing and alignment;
no truncated key identifiers without a tooltip/copy affordance; tables readable at 1920 px; statuses legible in
grayscale; empty/error/loading states look designed; nothing overlaps at 200% zoom; focus ring visible on every
interactive element; no leftover default browser styling.

### Implementation handoff and integration

| Field | Record before handoff / after integration |
|---|---|
| Feature commits / tested HEAD | pending |
| Verification | pending; record commands, viewports and fixtures |
| Execution usage | pending; actual model/effort evidence |
| Compatibility assessment | no API/schema/user-contract change expected |
| Proposed version bump | minor (user-visible redesign), orchestrator allocates |
| Proposed changelog entry | FL-021: designed shell and Projects/Sources screens |
| Related documentation | README run/test notes for new checks; design-system notes under `frontend/src/design/` |
| Residual blockers / owned resources | none yet |
| Integrated commit / final version | pending |
| Backlog status | ready |
