import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ExploreWorkspace } from "../../app/shell/ExploreWorkspace";
import { EmptyState, KeyValue, KeyValueList, LoadingState } from "../../design";
import { useFieldSpecs, type WellboreRef } from "./fieldData";
import { activate, buildFieldPlan, FIELD_BADGE, summarize, type FieldPlan, type FieldWell } from "./fieldModel";
import type { FieldCommands } from "./FieldViewer3D";
import { useFieldTrajectories } from "./trajectoryData";
import { inputOf, placeholderReason, type TrajectoryState } from "./trajectorySource";
import { webgl2Available } from "./webgl";
import styles from "./Scene.module.css";

const FieldViewer3D = lazy(() => import("./FieldViewer3D"));

const STATUS_TEXT: Record<FieldWell["status"], string> = {
  spec: "Visual asset spec",
  missing: "No asset spec yet",
  error: "Spec could not be loaded",
  loading: "Loading spec…",
};

interface Props {
  projectId: string;
  wellbores: readonly WellboreRef[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** Open the single-wellbore view (back-navigation returns here with the selection kept). */
  onOpen: (id: string) => void;
  /** Returning from the wellbore view: move focus to the selected list item (or the first). */
  restoreFocus?: boolean | undefined;
}


export function FieldScene({ projectId, wellbores: listed, selectedId, onSelect, onOpen, restoreFocus }: Props) {
  // The listing is rebuilt on every parent render; keep a stable identity while ids and names are unchanged.
  const listKey = listed.map((w) => `${w.id}\u0000${w.name}`).join("\u0001");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const wellbores = useMemo(() => listed, [listKey]);
  const { specs, retry } = useFieldSpecs(projectId, wellbores);
  const { trajectories } = useFieldTrajectories(projectId, wellbores);
  const plan: FieldPlan = useMemo(
    () =>
      buildFieldPlan(
        wellbores.map((w) => ({ id: w.id, name: w.name, spec: specs.get(w.id) ?? { kind: "loading" } })),
        (id) => inputOf(trajectories.get(id)),
        (id) => placeholderReason(trajectories.get(id)),
      ),
    [wellbores, specs, trajectories],
  );
  const summary = summarize(plan);
  const commands = useRef<FieldCommands | null>(null);
  const [lost, setLost] = useState(0);
  const [gl] = useState(() => webgl2Available());
  const selected = selectedId === null ? null : (plan.byId.get(selectedId) ?? null);

  const activateWell = useCallback(
    (id: string) => {
      const next = activate(selectedId, id);
      if (next.open) {
        onOpen(id);
        return;
      }
      onSelect(next.selectedId);
      commands.current?.flyTo(id);
    },
    [selectedId, onSelect, onOpen],
  );
  const clear = useCallback(() => onSelect(null), [onSelect]);

  const toolbar = (
    <div className={styles.toolbar} role="toolbar" aria-label="Field view controls">
      <strong>Field view</strong>
      <span data-testid="field-summary">
        {summary.total} wellbore{summary.total === 1 ? "" : "s"}: {summary.withSpec} with asset spec
        {summary.missing > 0 ? `, ${summary.missing} without` : ""}
        {summary.failed > 0 ? `, ${summary.failed} failed` : ""}
        {summary.loading > 0 ? `, ${summary.loading} loading` : ""}
      </span>
      <button type="button" onClick={() => { onSelect(null); commands.current?.fitAll(); }} disabled={summary.withSpec === 0}>
        Fit field
      </button>
      <button type="button" aria-label="Zoom in" onClick={() => commands.current?.zoom(0.8)} disabled={summary.withSpec === 0}>
        +
      </button>
      <button type="button" aria-label="Zoom out" onClick={() => commands.current?.zoom(1.25)} disabled={summary.withSpec === 0}>
        −
      </button>
      <button type="button" onClick={() => selected !== null && onOpen(selected.id)} disabled={selected === null} data-testid="field-open">
        Open wellbore view
      </button>
      {summary.failed > 0 && (
        <button type="button" onClick={() => retry(plan.wells.filter((w) => w.status === "error").map((w) => w.id))}>
          Retry failed
        </button>
      )}
      <span className={styles.badge} data-testid="illustrative-badge">
        {FIELD_BADGE}
      </span>
      <span className={styles.badge} data-testid="field-layout-badge">
        {plan.layoutLabel}
      </span>
    </div>
  );

  let stage;
  if (summary.empty && summary.failed > 0 && summary.failed === summary.total) {
    stage = (
      <EmptyState title="Asset specs failed to load">
        The visual asset specs of all {summary.total} wellbores failed to load, so nothing can be drawn in the field view. Use Retry failed to try again.
      </EmptyState>
    );
  } else if (summary.empty) {
    stage = (
      <EmptyState title="No visual asset specs yet">
        None of the {summary.total} wellbores of this project has a visual asset spec, so there is nothing to draw in the field view. Select a wellbore in the
        list and open it to generate one (stub), or reconstruct equipment first.
      </EmptyState>
    );
  } else if (summary.withSpec === 0) {
    stage = <LoadingState label={`Loading asset specs for ${summary.total} wellbores`} />;
  } else if (gl && lost === 0) {
    stage = (
      <div className={styles.stageCol} data-testid="scene-stage" data-view={selected === null ? "field" : "focused"} data-selected={selectedId ?? ""}>
        <Suspense fallback={<LoadingState label="Loading 3D view" />}>
          <FieldViewer3D plan={plan} selectedId={selectedId} onActivate={activateWell} onClear={clear} commands={commands} onContextLost={() => setLost((n) => n + 1)} />
        </Suspense>
      </div>
    );
  } else {
    stage = <FieldFallback plan={plan} />;
  }

  return (
    <ExploreWorkspace
      tree={<WellboreList plan={plan} selectedId={selectedId} onActivate={activateWell} restoreFocus={restoreFocus} />}
      stage={
        <div className={styles.view}>
          {toolbar}
          <details className={styles.note} data-testid="field-notes">
            <summary>Scale, layout and level-of-detail notes</summary>
            Wellbores sit on a schematic grid in project-listing order: no validated coordinate source with a CRS/datum is available, so positions are not map
            positions. Trajectory tubes, wellhead glyphs and pads are drawn wider than physical size for legibility. Far wellbores show a trajectory tube, a
            wellhead glyph and coarse component markers (green: documented, grey: illustrative, orange: perforations); the selected wellbore shows full
            primitives. Hole depths are true scale; a vertical placeholder line means no survey is available. Wellbores without a spec are drawn as an
            outlined ring and listed with their state.
          </details>
          {stage}
        </div>
      }
      inspector={<FieldInspector well={selected} onOpen={onOpen} survey={selected === null ? undefined : trajectories.get(selected.id)} />}
    />
  );
}

function FieldFallback({ plan }: { plan: FieldPlan }) {
  return (
    <table className={styles.fallbackTable} data-testid="scene-fallback">
      <caption>3D view unavailable (WebGL2 not supported or context lost). Wellbores as a list ({plan.layoutLabel}):</caption>
      <thead>
        <tr>
          <th>Wellbore</th>
          <th>State</th>
          <th>Grid cell</th>
        </tr>
      </thead>
      <tbody>
        {plan.wells.map((w) => (
          <tr key={w.id}>
            <td>{w.name}</td>
            <td>{STATUS_TEXT[w.status]}</td>
            <td>
              column {w.cell.col + 1}, row {w.cell.row + 1}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Keyboard-navigable wellbore list: arrows move focus, Enter/Space selects and flies; again opens the wellbore view. */
function WellboreList({ plan, selectedId, onActivate, restoreFocus }: { plan: FieldPlan; selectedId: string | null; onActivate: (id: string) => void; restoreFocus?: boolean | undefined }) {
  const root = useRef<HTMLDivElement>(null);
  const first = useRef(restoreFocus === true);
  useEffect(() => {
    if (!first.current || root.current === null) return;
    first.current = false;
    const items = Array.from(root.current.querySelectorAll<HTMLButtonElement>("button[data-wellbore-id]"));
    (items.find((b) => b.dataset.wellboreId === selectedId) ?? items[0])?.focus();
  }, [selectedId]);
  const move = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key) || root.current === null) return;
    const items = Array.from(root.current.querySelectorAll<HTMLButtonElement>("button[data-wellbore-id]"));
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    let next = at;
    if (e.key === "ArrowDown") next = Math.min(items.length - 1, at + 1);
    if (e.key === "ArrowUp") next = Math.max(0, at - 1);
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = items.length - 1;
    e.preventDefault();
    items[next]?.focus();
  };
  return (
    // Key events bubble from the real buttons inside; the wrapper only adds arrow-key roving focus.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <div ref={root} onKeyDown={move} role="group" aria-label="Wellbores" data-testid="wellbore-list">
      <h3 className={styles.groupTitle}>Wellbores ({plan.wells.length})</h3>
      <ul className={styles.list}>
        {plan.wells.map((w) => (
          <li key={w.id}>
            <button type="button" className={styles.item} data-wellbore-id={w.id} data-status={w.status} aria-pressed={w.id === selectedId} onClick={() => onActivate(w.id)}>
              {w.name}
              <span className={styles.itemKind}>
                {STATUS_TEXT[w.status]}
                {w.status === "spec" ? ` · ${w.counts.components} components` : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FieldInspector({ well, onOpen, survey }: { well: FieldWell | null; onOpen: (id: string) => void; survey: TrajectoryState | undefined }) {
  if (well === null) {
    return (
      <div className={styles.inspector} data-testid="field-inspector">
        <p className={styles.note}>Select a wellbore in the list or the scene to fly to it. Select it again, or use Open, for the wellbore view.</p>
      </div>
    );
  }
  return (
    <div className={styles.inspector} data-testid="field-inspector">
      <h3 data-testid="field-inspector-name">{well.name}</h3>
      <KeyValueList compact>
        <KeyValue term="Asset spec">{STATUS_TEXT[well.status]}</KeyValue>
        <KeyValue term="Grid cell">
          column {well.cell.col + 1}, row {well.cell.row + 1} (schematic)
        </KeyValue>
        {well.status === "spec" && (
          <>
            <KeyValue term="Components">
              {well.counts.components} ({well.counts.downhole} downhole, {well.counts.surface} surface, {well.counts.unlocated} unlocated)
            </KeyValue>
            <KeyValue term="Illustrative">{well.counts.illustrative} of {well.counts.components}</KeyValue>
            <KeyValue term="Trajectory">
              <span data-testid="field-inspector-trajectory">
                {well.trajectoryAvailable ? (well.model?.path.sourceLabel ?? "From survey stations") : `Unavailable: vertical placeholder line (${placeholderReason(survey)})`}
              </span>
            </KeyValue>
            {survey?.kind === "ready" && survey.info.surfaceText !== null && (
              <KeyValue term="Location">
                <span data-testid="field-inspector-surface">{survey.info.surfaceText}</span>
              </KeyValue>
            )}
            <KeyValue term="Revision">{well.revision}</KeyValue>
          </>
        )}
      </KeyValueList>
      {well.status === "error" && <p role="alert">{well.message}</p>}
      {well.status === "missing" && <p className={styles.note}>This wellbore has no visual asset spec, so it is shown as a placeholder ring. Open it to generate one (stub).</p>}
      {well.counts.unlocated > 0 && <p className={styles.note}>Unlocated components are not drawn in the field view; the wellbore view shows them in its separate tray.</p>}
      <button type="button" onClick={() => onOpen(well.id)} data-testid="field-inspector-open">
        Open wellbore view
      </button>
    </div>
  );
}
