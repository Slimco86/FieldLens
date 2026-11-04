import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ExploreWorkspace } from "../../app/shell/ExploreWorkspace";
import type { ExploreStageContext } from "../../app/shell/exploreStage";
import { useExploreEnrichment } from "./exploreEnrichment";
import { EmptyState, KeyValue, KeyValueList, LoadingState } from "../../design";
import { reconstructed, useFieldSpecs, type WellboreRef } from "./fieldData";
import { activate, buildFieldPlan, FIELD_BADGE, summarize, type FieldPlan, type FieldSpecState, type FieldWell } from "./fieldModel";
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


/** Stand-alone field view: loads the specs itself. ExploreScene shares one spec load with the dropdown via `FieldSceneView`. */
export function FieldScene({ wellbores: listed, ...rest }: Props) {
  // The listing is rebuilt on every parent render; keep a stable identity while ids and names are unchanged.
  const listKey = listed.map((w) => `${w.id}\u0000${w.name}`).join("\u0001");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const wellbores = useMemo(() => listed, [listKey]);
  const { specs, retry } = useFieldSpecs(rest.projectId, wellbores);
  return <FieldSceneView {...rest} wellbores={wellbores} specs={specs} retrySpecs={retry} />;
}

interface ViewProps extends Props {
  specs: ReadonlyMap<string, FieldSpecState>;
  retrySpecs: (ids?: readonly string[]) => void;
  /** Published model revision of the project; a change refetches the formation read model. */
  modelRevision?: string | null | undefined;
}

const FIELD_CONTEXT: ExploreStageContext = { kind: "field" };

export function FieldSceneView({ projectId, wellbores, specs, retrySpecs: retry, selectedId, onSelect, onOpen, restoreFocus, modelRevision = null }: ViewProps) {
  const enrich = useExploreEnrichment({ projectId, context: FIELD_CONTEXT, revision: modelRevision });
  // Surveys (and with them surface locations) are fetched only for reconstructed wellbores.
  const drawable = useMemo(() => reconstructed(wellbores, specs), [wellbores, specs]);
  const { trajectories, retry: retrySurveys } = useFieldTrajectories(projectId, drawable);
  const plan: FieldPlan = useMemo(
    () =>
      buildFieldPlan(
        wellbores.map((w) => ({ id: w.id, name: w.name, spec: specs.get(w.id) ?? { kind: "loading" } })),
        (id) => inputOf(trajectories.get(id)?.state),
        (id) => placeholderReason(trajectories.get(id)?.state),
        (id) => trajectories.get(id)?.surface ?? null,
      ),
    [wellbores, specs, trajectories],
  );
  const summary = summarize(plan);
  // The layout depends on every survey's location: wait until all reconstructed wellbores settled.
  const surveysPending = drawable.some((w) => {
    const k = trajectories.get(w.id)?.state.kind;
    return k === undefined || k === "loading";
  });
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
        {summary.total} wellbore{summary.total === 1 ? "" : "s"}: {summary.withSpec} reconstructed (with asset spec)
        {summary.missing > 0 ? `, ${summary.missing} not reconstructed (not listed or drawn)` : ""}
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
      {(summary.failed > 0 || drawable.some((w) => trajectories.get(w.id)?.state.kind === "error")) && (
        <button
          type="button"
          onClick={() => {
            retry(plan.wells.filter((w) => w.status === "error").map((w) => w.id));
            retrySurveys();
          }}
        >
          Retry failed
        </button>
      )}
      <span className={styles.badge} data-testid="illustrative-badge">
        {FIELD_BADGE}
      </span>
      <span className={styles.badge} data-testid="field-layout-badge" title={plan.layoutNote ?? undefined}>
        {plan.layoutLabel}
      </span>
    </div>
  );

  let stage;
  if (summary.empty && summary.failed > 0) {
    stage = (
      <EmptyState title="Asset specs failed to load">
        The visual asset specs of {summary.failed} wellbore{summary.failed === 1 ? "" : "s"} failed to load, so nothing can be drawn in the field view. Use Retry failed to try again.
      </EmptyState>
    );
  } else if (summary.empty) {
    stage = (
      <EmptyState title="No visual asset specs yet">
        None of the {summary.total} wellbores of this project has a visual asset spec, so there is nothing to draw in the field view. Only reconstructed
        wellbores are listed here; open a wellbore from the project to generate one (stub), or reconstruct equipment first.
      </EmptyState>
    );
  } else if (summary.withSpec === 0 || summary.loading > 0 || surveysPending) {
    stage = <LoadingState label={`Loading ${summary.total} wellbores (asset specs, surveys and surface locations)`} />;
  } else if (gl && lost === 0) {
    stage = (
      <div className={styles.stageCol} data-testid="scene-stage" data-view={selected === null ? "field" : "focused"} data-selected={selectedId ?? ""}>
        <Suspense fallback={<LoadingState label="Loading 3D view" />}>
          <FieldViewer3D
            plan={plan}
            selectedId={selectedId}
            onActivate={activateWell}
            onClear={clear}
            commands={commands}
            onContextLost={() => setLost((n) => n + 1)}
            {...(enrich === null ? {} : { layers: enrich.layers, resolveFormationFocus: enrich.resolveFormationFocus })}
          />
        </Suspense>
      </div>
    );
  } else {
    stage = <FieldFallback plan={plan} />;
  }

  return (
    <ExploreWorkspace
      {...(enrich === null ? {} : enrich.workspace)}
      tree={<WellboreList plan={plan} selectedId={selectedId} onActivate={activateWell} restoreFocus={restoreFocus} />}
      stage={
        <div className={styles.view}>
          {toolbar}
          <details className={styles.note} data-testid="field-notes">
            <summary>Scale, layout and level-of-detail notes</summary>
            Only reconstructed wellbores (with an asset spec) are listed and drawn; the others are counted in the summary. When every drawn wellbore states a
            planar surface location with the same CRS, datum and metre unit, wellheads sit at east/north offsets from the field centroid; otherwise
            (different or unstated CRS, datum or unit, or no locations) they sit on a schematic grid in listing order that is not a map. Nothing is
            reprojected or guessed; wellbores without a location in a located field wait in a labelled "unlocated" row south of the field. Trajectory tubes,
            wellhead glyphs and pads are drawn wider than physical size for legibility (pads shrink for wellheads a few metres apart). Far wellbores show a
            trajectory tube, a wellhead glyph and coarse component markers (green: documented, grey: illustrative, orange: perforations); the selected
            wellbore shows full primitives and a brighter trace. Hole depths are true scale; a vertical placeholder line means no survey is available.
          </details>
          {stage}
        </div>
      }
      inspector={
        <>
          <FieldInspector well={selected} onOpen={onOpen} survey={selected === null ? undefined : trajectories.get(selected.id)?.state} />
          {enrich?.formationPanel}
        </>
      }
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
          <th>Position</th>
        </tr>
      </thead>
      <tbody>
        {plan.wells.map((w) => (
          <tr key={w.id}>
            <td>{w.name}</td>
            <td>{STATUS_TEXT[w.status]}</td>
            <td>{placementText(w)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function placementText(w: FieldWell): string {
  if (w.placement === "schematic") return `column ${w.cell.col + 1}, row ${w.cell.row + 1} (schematic)`;
  if (w.placement === "unlocated") return "unlocated: no stated surface location (holding row, not a map position)";
  return `E ${Math.round(w.position[0])} m, N ${Math.round(-w.position[2])} m from the field centroid`;
}

/** Keyboard-navigable wellbore list: arrows move focus, Enter/Space selects and flies; again opens the wellbore view. */
function WellboreList({ plan, selectedId, onActivate, restoreFocus }: { plan: FieldPlan; selectedId: string | null; onActivate: (id: string) => void; restoreFocus?: boolean | undefined }) {
  const root = useRef<HTMLDivElement>(null);
  const first = useRef(restoreFocus === true);
  useEffect(() => {
    if (!first.current || root.current === null) return;
    const items = Array.from(root.current.querySelectorAll<HTMLButtonElement>("button[data-wellbore-id]"));
    // The list fills as specs arrive (only reconstructed wellbores are listed): wait for the first item.
    if (items.length === 0) return;
    first.current = false;
    (items.find((b) => b.dataset.wellboreId === selectedId) ?? items[0])?.focus();
  }, [selectedId, plan.wells.length]);
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
      <h3 className={styles.groupTitle}>Reconstructed wellbores ({plan.wells.length})</h3>
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
        <KeyValue term="Placement">
          <span data-testid="field-inspector-placement">{placementText(well)}</span>
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
      {well.placement === "unlocated" && <p className={styles.note}>No planar surface location is stated for this wellbore, so it waits in the unlocated row south of the field; this is not its map position.</p>}
      {well.counts.unlocated > 0 && <p className={styles.note}>Unlocated components are not drawn in the field view; the wellbore view lists them (list and inspector) but does not draw them.</p>}
      <button type="button" onClick={() => onOpen(well.id)} data-testid="field-inspector-open">
        Open wellbore view
      </button>
    </div>
  );
}
