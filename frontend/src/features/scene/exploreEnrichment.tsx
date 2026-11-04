import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { useExploreStage, type ExploreStageContext } from "../../app/shell/exploreStage";
import { publishExploreContext } from "../assistant/exploreBridge";
import { AsOfControl, ChartCursorProvider, ChartPanel, createChartCursorStore, type CursorWindow } from "../charts";
import { FormationPanel } from "../context/formations/FormationPanel";
import { formationFocusTarget } from "../context/formations/formationModel";
import { createFormationStore } from "../context/formations/formationStore";
import type { FormationTarget } from "../context/formations/formationTypes";
import { useFormationLayers } from "../context/formations/useFormationLayers";
import { useExploreCommandBus, useExploreCommandHandlers } from "./ExploreCommandsContext";
import type { ExploreCommandMap, SourceRef } from "./exploreCommands";
import type { ResolveFormationFocus } from "./formationFocus";
import type { SceneLayerContext, SceneLayers } from "./sceneLayers";

// The formation layer imports three/R3F: keep it out of the main chunk (it renders only inside the lazy viewers' Canvas).
const FormationLayer = lazy(() => import("../context/formations/FormationLayer").then((m) => ({ default: m.FormationLayer })));
// The PDF drawer is fetched on first open only (same component the SourceLink uses, TASK-088).
const DocumentViewer = lazy(() => import("../documents/DocumentViewer"));

/**
 * Explore enrichment wiring (TASK-105): one place that connects the formation layer, charts, assistant and source
 * viewer to the Explore stage. Every bus command has exactly one acting path here or in the viewers:
 *
 *   focusWellbore / focusElement / flyOver / stopFlyOver  viewers (camera)
 *   focusFormation                                         camera (moves) + FormationPanel (selects)
 *   openChart                                              ExploreWorkspace (reveals Charts) via `onOpenChart` below
 *   openSource                                             `SourceViewerHost` (PDF page) or the Sources tab (no page)
 *
 * Outside an `ExploreCommandsProvider` (a stand-alone scene) nothing is added.
 */
export interface ExploreEnrichmentInput {
  projectId: string;
  context: ExploreStageContext;
  /** Model/trajectory revision key: a changed value refetches the formation read model. */
  revision: string | number | null;
  /** Selected equipment element (sent as assistant context). */
  selectedElementId?: string | null;
}

export interface ExploreEnrichment {
  /** `layers` prop for Viewer3D / FieldViewer3D. */
  layers: SceneLayers;
  /** `resolveFormationFocus` prop for Viewer3D / FieldViewer3D. */
  resolveFormationFocus: ResolveFormationFocus;
  /** DOM companion of the layer; mount in a workspace region (inside the commands provider). */
  formationPanel: ReactNode;
  /** Spread into `<ExploreWorkspace>`. */
  workspace: {
    context: ExploreStageContext;
    charts: ReactNode;
    assistant: ReactNode;
    onOpenChart: (p: ExploreCommandMap["openChart"]) => boolean;
  };
}

export const targetOf = (c: ExploreStageContext): FormationTarget => (c.kind === "wellbore" ? { kind: "wellbore", wellboreId: c.wellboreId } : { kind: "field" });

/** Cursor window for an `openChart` window: ISO dates -> time axis (ms), numbers -> depth axis (m). Null when absent/invalid. */
export function cursorWindowOf(w: ExploreCommandMap["openChart"]["window"]): CursorWindow | null | "invalid" {
  if (w === undefined || w.from === undefined || w.to === undefined) return null; // a half-open window is not applied
  if (typeof w.from === "number" && typeof w.to === "number") {
    return Number.isFinite(w.from) && Number.isFinite(w.to) && w.from <= w.to ? { axis: "depth", from: w.from, to: w.to } : "invalid";
  }
  if (typeof w.from === "string" && typeof w.to === "string") {
    const from = Date.parse(w.from);
    const to = Date.parse(w.to);
    return Number.isFinite(from) && Number.isFinite(to) && from <= to ? { axis: "time", from, to } : "invalid";
  }
  return "invalid";
}

/** Reveal and focus one chart block inside the charts host; false when no loaded chart has that key. */
export function focusChartBlock(host: HTMLElement | null, kind: string): boolean {
  if (host === null) return false;
  const block = Array.from(host.querySelectorAll<HTMLElement>("[data-chart-key]")).find((el) => el.dataset["chartKey"] === kind);
  if (block === undefined) return false;
  // The pane may still be hidden this tick (the workspace reveals it right after); focus on the next task.
  window.setTimeout(() => {
    block.tabIndex = -1;
    block.scrollIntoView?.({ block: "nearest" });
    block.focus({ preventScroll: true });
  }, 0);
  return true;
}

export function useExploreEnrichment({ projectId, context, revision, selectedElementId = null }: ExploreEnrichmentInput): ExploreEnrichment | null {
  const bus = useExploreCommandBus();
  const hosted = bus !== null;
  const [store] = useState(createFormationStore);
  const [cursor] = useState(createChartCursorStore);
  const host = useRef<HTMLDivElement | null>(null);
  const target = useMemo(() => targetOf(context), [context]);
  const state = useFormationLayers(hosted ? projectId : null, target, revision);
  const data = state.data;

  const layers = useCallback(
    (ctx: SceneLayerContext) => (
      <Suspense fallback={null}>
        <FormationLayer ctx={ctx} data={data} store={store} />
      </Suspense>
    ),
    [data, store],
  );
  const resolveFormationFocus = useCallback<ResolveFormationFocus>(
    (wellboreId, formationId, ctx) => {
      const t = formationFocusTarget(data, formationId, ctx, wellboreId);
      return t === null ? null : { target: t.target, radius: t.radius };
    },
    [data],
  );

  const onOpenChart = useCallback(
    (p: ExploreCommandMap["openChart"]): boolean => {
      // A chart belongs to one set: the selected wellbore's, or the field's. Anything else is a stale target.
      const sameScope = context.kind === "wellbore" ? p.wellboreId === context.wellboreId : p.wellboreId === null;
      if (!sameScope) return false;
      const win = cursorWindowOf(p.window);
      if (win === "invalid") return false;
      if (!focusChartBlock(host.current, p.kind)) return false;
      if (win !== null) cursor.set(win, "assistant-link");
      return true;
    },
    [context, cursor],
  );

  // Selected historical view (ISO date or null = latest), shared by charts and the assistant.
  const [asOf, setAsOf] = useState<string | null>(null);
  const charts = useMemo(
    () => (
      <ChartHost hostRef={host}>
        <AsOfControl value={asOf} onChange={setAsOf} />
        <ChartCursorProvider store={cursor}>
          <ChartPanel projectId={projectId} context={context} asOf={asOf} />
        </ChartCursorProvider>
      </ChartHost>
    ),
    [projectId, context, cursor, asOf],
  );
  const wellboreId = context.kind === "wellbore" ? context.wellboreId : null;
  const assistant = useMemo(
    () => <ExploreContextPublisher projectId={projectId} wellboreId={wellboreId} selectedElementId={selectedElementId} asOf={asOf} />,
    [projectId, wellboreId, selectedElementId, asOf],
  );
  const formationPanel = useMemo(() => <FormationPanel state={state} store={store} wellboreId={wellboreId} />, [state, store, wellboreId]);

  return useMemo(
    () => (hosted ? { layers, resolveFormationFocus, formationPanel, workspace: { context, charts, assistant, onOpenChart } } : null),
    [hosted, layers, resolveFormationFocus, formationPanel, context, charts, assistant, onOpenChart],
  );
}

/** Plain wrapper so the charts pane can be searched without owning ChartPanel's internals. `display: contents` keeps layout. */
function ChartHost({ hostRef, children }: { hostRef: RefObject<HTMLDivElement | null>; children: ReactNode }) {
  return (
    <div ref={hostRef} style={{ display: "contents" }} data-testid="chart-host">
      {children}
    </div>
  );
}

/** Renders nothing: publishes the live stage selection to the project-level assistant (it narrows, never widens, scope). */
function ExploreContextPublisher({ projectId, wellboreId, selectedElementId, asOf }: { projectId: string; wellboreId: string | null; selectedElementId: string | null; asOf: string | null }) {
  const stage = useExploreStage();
  const view = stage?.mode ?? "3d";
  useEffect(() => {
    publishExploreContext({ projectId, wellboreId, selectedElementId, asOf, view });
  }, [projectId, wellboreId, selectedElementId, asOf, view]);
  useEffect(() => () => publishExploreContext(null), []);
  return null;
}

/**
 * The single `openSource` handler. A page-addressed source opens in the embedded PDF viewer drawer (TASK-088); a
 * source without a page goes to the Sources tab row (`onOpenSource`). Without that callback the command is refused
 * (`unhandled`), never silently dropped.
 */
export function SourceViewerHost({ projectId, onOpenSource }: { projectId: string; onOpenSource?: ((documentId: string) => void) | undefined }) {
  const [open, setOpen] = useState<{ documentId: string; page: number } | null>(null);
  useExploreCommandHandlers({
    openSource: (p: { source: SourceRef }) => {
      const { documentId, page } = p.source;
      if (documentId === "") return false;
      if (typeof page === "number" && Number.isInteger(page) && page > 0) {
        setOpen({ documentId, page });
        return true;
      }
      if (onOpenSource === undefined) return false;
      onOpenSource(documentId);
      return true;
    },
  });
  // A different project closes any open drawer.
  useEffect(() => setOpen(null), [projectId]);
  if (open === null) return null;
  return (
    <Suspense fallback={<span role="status">Loading viewer…</span>}>
      <DocumentViewer projectId={projectId} documentId={open.documentId} filename={null} page={open.page} onClose={() => setOpen(null)} />
    </Suspense>
  );
}
