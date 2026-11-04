import { lazy, Suspense, useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { ExploreWorkspace } from "../../app/shell/ExploreWorkspace";
import type { ExploreStageContext } from "../../app/shell/exploreStage";
import { ExploreCommandsProvider } from "./ExploreCommandsContext";
import { EmptyState, ErrorState, LoadingState } from "../../design";
import { getExposure } from "../pipeline/api";
import { useScopedResource } from "../projects/scope";
import { generateAssetSpec, getAssetSpec, type VisualAssetSpecRecord } from "./api";
import { ComponentList } from "./ComponentList";
import { Inspector } from "./Inspector";
import { buildSceneModel, defaultExaggeration, locatedMdMax, KIND_LABEL, placementText, type SceneModel } from "./sceneModel";
import { inputOf, loadTrajectory, placeholderReason } from "./trajectorySource";
import { WellPath } from "./trajectory";
import type { TrajectoryState } from "./trajectorySource";
import { FieldSceneView } from "./FieldScene";
import { useFieldSpecs } from "./fieldData";
import type { FieldSpecState } from "./fieldModel";
import { webgl2Available } from "./webgl";
import type { LabelMode, ViewerCommands, ViewerOptions } from "./Viewer3D";
import styles from "./Scene.module.css";

const Viewer3D = lazy(() => import("./Viewer3D"));

const EXAGGERATIONS = [1, 5, 8, 10, 20, 50, 100, 200, 500] as const;
const SURFACE_SCALES = [1, 2, 4] as const;

interface WellboreRef {
  id: string;
  name: string;
}

/** Owns the Explore command bus for everything below it (viewers, charts, assistant dock). */
export function ExploreScene({ projectId }: { projectId: string }) {
  return (
    <ExploreCommandsProvider>
      <ExploreSceneInner projectId={projectId} />
    </ExploreCommandsProvider>
  );
}

function ExploreSceneInner({ projectId }: { projectId: string }) {
  const exposure = useScopedResource(`exposure/${projectId}`, (signal) => getExposure(projectId, signal));
  const [picked, setPicked] = useState<string | null>(null);
  // `null` = automatic: the field view for two or more wellbores, the wellbore view for one.
  const [mode, setMode] = useState<"field" | "wellbore" | null>(null);
  const [fieldSelected, setFieldSelected] = useState<string | null>(null);
  // True after "← Field view": the field view then takes focus to its selected list item.
  const [returning, setReturning] = useState(false);
  const exposed = exposure.state.kind === "ready" ? exposure.state.data : null;
  const wellbores: WellboreRef[] = useMemo(
    () => (exposed === null ? [] : exposed.wells.flatMap((w) => w.wellbores.map((b) => ({ id: b.wellbore_id, name: `${w.name} / ${b.wellbore_name}` })))),
    [exposed],
  );
  // One spec read per wellbore, shared by the field view and the wellbore dropdown (see `reconstructed`).
  const { specs, retry: retrySpecs } = useFieldSpecs(projectId, wellbores);

  if (exposure.state.kind === "loading") return <LoadingState label="Loading wellbores" />;
  if (exposure.state.kind === "error") {
    return (
      <ErrorState
        message={`Wellbores could not be loaded: ${exposure.state.error.message}`}
        requestId={exposure.state.error.requestId}
        onRetry={exposure.reload}
      />
    );
  }
  const current = wellbores.find((w) => w.id === picked) ?? wellbores[0];
  if (current === undefined) {
    return (
      <ExploreWorkspace
        stage={<EmptyState title="No wellbores yet">Resolve identities in the Reconstruction tab to explore a wellbore.</EmptyState>}
      />
    );
  }
  if ((mode ?? (wellbores.length >= 2 ? "field" : "wellbore")) === "field") {
    return (
      <FieldSceneView
        projectId={projectId}
        wellbores={wellbores}
        specs={specs}
        retrySpecs={retrySpecs}
        selectedId={fieldSelected}
        onSelect={setFieldSelected}
        restoreFocus={returning}
        onOpen={(id) => {
          setReturning(false);
          setPicked(id);
          setFieldSelected(id);
          setMode("wellbore");
        }}
      />
    );
  }
  return (
    <WellboreScene
      key={current.id}
      projectId={projectId}
      wellbore={current}
      wellbores={dropdownWellbores(wellbores, specs, current.id)}
      onPick={setPicked}
      onSpecChanged={() => retrySpecs([current.id])}
      onField={
        wellbores.length >= 2
          ? () => {
              setReturning(true);
              setMode("field");
            }
          : undefined
      }
    />
  );
}

/** Single-view dropdown: reconstructed wellbores only (plus the one shown, so it never vanishes, e.g. before its stub spec is generated). */
export function dropdownWellbores(all: readonly WellboreRef[], specs: ReadonlyMap<string, FieldSpecState>, currentId: string): WellboreRef[] {
  return all.filter((w) => w.id === currentId || specs.get(w.id)?.kind === "ready");
}

interface WellboreSceneProps {
  projectId: string;
  wellbore: WellboreRef;
  wellbores: WellboreRef[];
  onPick: (id: string) => void;
  /** The current wellbore's spec was (re)generated: refresh the shared "has a spec" signal. */
  onSpecChanged?: (() => void) | undefined;
  /** Back to the field view (only offered when the project has two or more wellbores). */
  onField?: (() => void) | undefined;
}

function WellboreScene({ projectId, wellbore, wellbores, onPick, onField, onSpecChanged }: WellboreSceneProps) {
  const spec = useScopedResource(`asset-spec/${projectId}/${wellbore.id}`, (signal) =>
    getAssetSpec(projectId, wellbore.id, signal),
  );
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const { replace } = spec;

  const generate = useCallback(async () => {
    setGenerating(true);
    setGenError(null);
    try {
      replace(await generateAssetSpec(projectId, wellbore.id, {}));
      onSpecChanged?.();
    } catch (e) {
      setGenError(e instanceof Error ? e.message : "Generation failed.");
    } finally {
      setGenerating(false);
    }
  }, [projectId, wellbore.id, replace, onSpecChanged]);

  const picker = (
    <>
      {onField !== undefined && (
        <button type="button" onClick={onField} data-testid="back-to-field">
          ← Field view
        </button>
      )}
      <label>
        Wellbore{" "}
        <select value={wellbore.id} onChange={(e) => onPick(e.target.value)} aria-label="Wellbore">
          {wellbores.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
      </label>
    </>
  );
  const generateButton = (
    <button type="button" onClick={() => void generate()} disabled={generating} data-testid="generate-stub">
      {generating ? "Generating…" : "Generate (stub)"}
    </button>
  );

  if (spec.state.kind === "ready") {
    return (
      <SceneBody
        record={spec.state.data}
        projectId={projectId}
        wellbore={wellbore}
        picker={picker}
        generateButton={generateButton}
        genError={genError}
      />
    );
  }
  let body: ReactNode;
  if (spec.state.kind === "loading") body = <LoadingState label="Loading asset spec" />;
  else if (spec.state.error.status === 404) {
    body = (
      <EmptyState title="No visual asset yet">
        <p>
          No visual asset spec exists for this wellbore. The stub generator builds one from its equipment candidates
          (no model call).
        </p>
        {generateButton}
        {genError !== null && <p role="alert">{genError}</p>}
      </EmptyState>
    );
  } else {
    body = (
      <ErrorState
        message={`The asset spec could not be loaded: ${spec.state.error.message}`}
        requestId={spec.state.error.requestId}
        onRetry={spec.reload}
      />
    );
  }
  return (
    <ExploreWorkspace
      context={{ kind: "wellbore", wellboreId: wellbore.id }}
      stage={
        <div className={styles.view}>
          <div className={styles.toolbar}>{picker}</div>
          {body}
        </div>
      }
    />
  );
}

interface SceneBodyProps {
  record: VisualAssetSpecRecord;
  projectId: string;
  wellbore: WellboreRef;
  picker: ReactNode;
  generateButton: ReactNode;
  genError: string | null;
}

function SceneBody({ record, projectId, wellbore, picker, generateButton, genError }: SceneBodyProps) {
  const [exaggeration, setExaggeration] = useState<number>(() => defaultExaggeration(locatedMdMax(record.spec)));
  const [view, setView] = useState<"wellhead" | "whole" | "selection">("wellhead");
  const [surfaceScale, setSurfaceScale] = useState<number>(1);
  const [cutaway, setCutaway] = useState(true);
  const wbContext = useMemo<ExploreStageContext>(() => ({ kind: "wellbore", wellboreId: wellbore.id }), [wellbore.id]);
  const [labels, setLabels] = useState<LabelMode>("all");
  const [depthMarks, setDepthMarks] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [lost, setLost] = useState(0);
  const commands = useRef<ViewerCommands | null>(null);
  const [gl] = useState(() => webgl2Available());

  const spec = record.spec;
  const survey = useScopedResource(`trajectory/${projectId}/${wellbore.id}`, (signal) => loadTrajectory(projectId, wellbore.id, signal));
  // Keyed on the loaded data (stable), not on the resource wrapper (new object every render).
  const loaded = survey.state.kind === "ready" ? survey.state.data : null;
  const surveyKind = survey.state.kind;
  const surveyState: TrajectoryState = useMemo(
    () => loaded ?? (surveyKind === "error" ? { kind: "error", reason: "the survey could not be loaded" } : { kind: "loading" }),
    [loaded, surveyKind],
  );
  const model: SceneModel = useMemo(() => {
    const mdMax = Math.max(locatedMdMax(spec), 100);
    const input = inputOf(surveyState);
    const path = input !== null ? WellPath.fromTrajectory(input, mdMax) : WellPath.unavailable(mdMax, placeholderReason(surveyState));
    return buildSceneModel(spec, path, { surfaceScale });
  }, [spec, surveyState, surfaceScale]);

  const options: ViewerOptions = { exaggeration, surfaceScale, cutaway, labels, depthMarks };
  const select = useCallback((id: string | null) => {
    setSelectedId(id);
    if (id !== null) {
      setView("selection");
      commands.current?.focus(id);
    }
  }, []);
  const selected = selectedId === null ? null : (model.byId.get(selectedId) ?? null);

  const toolbar = (
    <div className={styles.toolbar} role="toolbar" aria-label="Scene controls">
      {picker}
      <button type="button" aria-pressed={view === "whole"} onClick={() => { setView("whole"); commands.current?.fitAll(); }}>
        Fit whole well
      </button>
      <button type="button" aria-pressed={view === "wellhead"} onClick={() => { setView("wellhead"); commands.current?.fitWellhead(); }}>
        Wellhead
      </button>
      <button
        type="button"
        onClick={() => {
          setSelectedId(null);
          setView("wellhead");
          commands.current?.fitWellhead();
        }}
      >
        Reset
      </button>
      <button type="button" aria-label="Zoom in" onClick={() => commands.current?.zoom(0.8)}>
        +
      </button>
      <button type="button" aria-label="Zoom out" onClick={() => commands.current?.zoom(1.25)}>
        −
      </button>
      <label>
        Radius exaggeration{" "}
        <select value={exaggeration} onChange={(e) => setExaggeration(Number(e.target.value))}>
          {EXAGGERATIONS.map((v) => (
            <option key={v} value={v}>
              {v}×
            </option>
          ))}
        </select>
      </label>
      <label>
        Surface scale{" "}
        <select value={surfaceScale} onChange={(e) => setSurfaceScale(Number(e.target.value))}>
          {SURFACE_SCALES.map((v) => (
            <option key={v} value={v}>
              {v}×
            </option>
          ))}
        </select>
      </label>
      <label>
        Labels{" "}
        <select value={labels} onChange={(e) => setLabels(e.target.value as LabelMode)}>
          <option value="all">All</option>
          <option value="selected">Selected</option>
          <option value="off">Off</option>
        </select>
      </label>
      <label>
        <input type="checkbox" checked={cutaway} onChange={(e) => setCutaway(e.target.checked)} /> Cutaway
      </label>
      <label>
        <input type="checkbox" checked={depthMarks} onChange={(e) => setDepthMarks(e.target.checked)} /> Depth marks
      </label>
      {generateButton}
      <span className={styles.badge} data-testid="illustrative-badge">
        Illustrative visual — not an engineering model
      </span>
    </div>
  );

  const notes = (
    <details className={styles.note} data-testid="scene-notes">
      <summary>Scale and trajectory notes</summary>
      Downhole radii exaggerated {exaggeration}× (lengths and depths true scale); surface equipment at {surfaceScale}×.{" "}
      {model.path.available
        ? `Trajectory: ${model.path.sourceLabel}.`
        : `Trajectory unavailable (${placeholderReason(surveyState)}): vertical placeholder, depths shown as measured depth.`}
      {model.notes.length > 0 ? ` ${model.notes.join(" ")}` : ""}
      {genError !== null ? ` ${genError}` : ""}
    </details>
  );

  const fallback = (
    <table className={styles.fallbackTable} data-testid="scene-fallback">
      <caption>3D view unavailable (WebGL2 not supported or context lost). Components as a list:</caption>
      <thead>
        <tr>
          <th>Component</th>
          <th>Kind</th>
          <th>Placement</th>
        </tr>
      </thead>
      <tbody>
        {model.elements.map((el) => (
          <tr key={el.id}>
            <td>{el.label}</td>
            <td>{KIND_LABEL[el.kind]}</td>
            <td>{placementText(el)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const stage = (
    <div className={styles.view}>
      {toolbar}
      {notes}
      <div className={styles.stageCol} data-testid="scene-stage" data-view={view} data-exaggeration={exaggeration}>
        {gl && lost === 0 ? (
          <Suspense fallback={<LoadingState label="Loading 3D view" />}>
            <Viewer3D
              model={model}
              options={options}
              selectedId={selectedId}
              onSelect={select}
              commands={commands}
              wellboreId={wellbore.id}
              onContextLost={() => setLost((n) => n + 1)}
            />
          </Suspense>
        ) : (
          fallback
        )}
      </div>
    </div>
  );

  return (
    <ExploreWorkspace
      context={wbContext}
      tree={<ComponentList model={model} selectedId={selectedId} onSelect={select} />}
      stage={stage}
      inspector={<Inspector element={selected} survey={surveyState} />}
    />
  );
}
