import { buildSceneModel, locatedMdMax, type SceneModel, type VisualAssetSpec } from "./sceneModel";
import { WellPath, type TrajectoryInput, type Vec3 } from "./trajectory";

/**
 * Pure model of the field view: ALL wellbores of the project in one scene. Nothing here touches
 * the GPU, so layout, level of detail, instancing counts and selection are unit-tested.
 *
 * Positions: no validated API provides wellhead coordinates with a CRS/datum, so wellbores are
 * laid out on a schematic grid. The grid is a drawing aid ("schematic layout, not map positions");
 * the order is the order of the project listing, never a geographic guess.
 */

export const FIELD_LAYOUT_LABEL = "Schematic layout, not map positions";
export const FIELD_BADGE = "Illustrative visual — not an engineering model";

export type FieldSpecState =
  | { kind: "loading" }
  | { kind: "ready"; spec: VisualAssetSpec; revision: number }
  | { kind: "missing" }
  | { kind: "error"; message: string };

export interface FieldWellInput {
  id: string;
  name: string;
  spec: FieldSpecState;
}

export type FieldWellStatus = "spec" | "missing" | "error" | "loading";

export interface FieldCounts {
  components: number;
  downhole: number;
  surface: number;
  unlocated: number;
  /** Components whose geometry is not backed by the spec (generic or defaulted dimensions). */
  illustrative: number;
}

export interface FieldMarker {
  id: string;
  kind: string;
  /** Position in the wellbore's local render frame (origin = wellhead, metres, Y up). */
  position: Vec3;
  illustrative: boolean;
}

export interface FieldWell {
  id: string;
  name: string;
  status: FieldWellStatus;
  index: number;
  /** Schematic grid position of the wellhead (render metres, Y = 0). */
  position: Vec3;
  cell: { col: number; row: number };
  model: SceneModel | null;
  /** Hole length below the wellhead in metres (0 without a spec). */
  depthM: number;
  trajectoryAvailable: boolean;
  counts: FieldCounts;
  markers: FieldMarker[];
  revision: number | null;
  message: string | null;
}

export interface FieldPlan {
  wells: FieldWell[];
  byId: Map<string, FieldWell>;
  cols: number;
  rows: number;
  spacingM: number;
  /** Largest of the grid span and the deepest hole: drives display widths and camera framing. */
  extentM: number;
  /** Centre of the whole field in render coordinates. */
  center: Vec3;
  /** Display-only widths, exaggerated and labelled in the UI (never a hole size). */
  display: { tubeRadiusM: number; glyphHeightM: number; glyphRadiusM: number; markerRadiusM: number; padHalfM: number };
  layoutLabel: string;
}

const EMPTY_COUNTS: FieldCounts = { components: 0, downhole: 0, surface: 0, unlocated: 0, illustrative: 0 };

/** Grid dimensions for `n` wellbores (landscape, close to the 1.4 aspect of the stage). */
export function gridDimensions(n: number): { cols: number; rows: number } {
  if (n <= 0) return { cols: 0, rows: 0 };
  const cols = Math.min(n, Math.max(1, Math.ceil(Math.sqrt(n * 1.4))));
  return { cols, rows: Math.ceil(n / cols) };
}

/** Centred schematic grid positions in listing order (row-major). */
export function gridLayout(n: number, spacingM: number): { position: Vec3; col: number; row: number }[] {
  const { cols, rows } = gridDimensions(n);
  return Array.from({ length: n }, (_, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    return { col, row, position: [(col - (cols - 1) / 2) * spacingM, 0, (row - (rows - 1) / 2) * spacingM] as const };
  });
}

function depthOf(path: WellPath): number {
  let d = 0;
  for (const v of path.vertices()) d = Math.max(d, Math.abs(v.position[1]));
  return d;
}

function markersOf(model: SceneModel): FieldMarker[] {
  return model.downhole.map((el) => {
    const md = el.mdTopM !== null && el.mdBottomM !== null ? (el.mdTopM + el.mdBottomM) / 2 : (el.mdTopM ?? 0);
    return { id: el.id, kind: el.kind, position: model.path.at(md).position, illustrative: el.illustrative };
  });
}

/**
 * Builds the plan. `trajectoryOf` supplies validated survey stations when an API provides them
 * (today none does, so wells draw the labelled vertical placeholder like the single view).
 */
export function buildFieldPlan(inputs: readonly FieldWellInput[], trajectoryOf: (id: string) => TrajectoryInput | null = () => null): FieldPlan {
  const built = inputs.map((w) => {
    if (w.spec.kind !== "ready") return { w, model: null as SceneModel | null, depth: 0 };
    const mdMax = Math.max(locatedMdMax(w.spec.spec), 100);
    const traj = trajectoryOf(w.id);
    const path = traj !== null ? WellPath.fromTrajectory(traj, mdMax) : WellPath.unavailable(mdMax, "no survey is wired to this view");
    return { w, model: buildSceneModel(w.spec.spec, path), depth: depthOf(path) };
  });
  const maxDepth = Math.max(0, ...built.map((b) => b.depth));
  // Spacing follows the deepest hole so deep wells do not read as needles; a floor keeps shallow fields apart.
  const spacingM = Math.max(300, Math.round((maxDepth * 0.3) / 50) * 50);
  const layout = gridLayout(inputs.length, spacingM);
  const { cols, rows } = gridDimensions(inputs.length);
  const span = Math.max((cols - 1) * spacingM, (rows - 1) * spacingM, spacingM);
  const extentM = Math.max(span, maxDepth, 300);
  const wells: FieldWell[] = built.map(({ w, model, depth }, index) => {
    const cell = layout[index]!;
    const status: FieldWellStatus = w.spec.kind === "ready" ? "spec" : w.spec.kind;
    const counts: FieldCounts =
      model === null
        ? EMPTY_COUNTS
        : {
            components: model.elements.length,
            downhole: model.downhole.length,
            surface: model.surface.length,
            unlocated: model.unlocated.length,
            illustrative: model.elements.filter((e) => e.illustrative).length,
          };
    return {
      id: w.id,
      name: w.name,
      status,
      index,
      position: cell.position,
      cell: { col: cell.col, row: cell.row },
      model,
      depthM: depth,
      trajectoryAvailable: model?.path.available ?? false,
      counts,
      markers: model === null ? [] : markersOf(model),
      revision: w.spec.kind === "ready" ? w.spec.revision : null,
      message: w.spec.kind === "error" ? w.spec.message : null,
    };
  });
  return {
    wells,
    byId: new Map(wells.map((w) => [w.id, w])),
    cols,
    rows,
    spacingM,
    extentM,
    center: [0, -maxDepth / 2, 0],
    display: {
      tubeRadiusM: extentM * 0.0022,
      glyphHeightM: extentM * 0.028,
      glyphRadiusM: extentM * 0.007,
      markerRadiusM: extentM * 0.0045,
      padHalfM: Math.max(extentM * 0.028 * 1.6, spacingM * 0.16),
    },
    layoutLabel: FIELD_LAYOUT_LABEL,
  };
}

export type Lod = "full" | "markers" | "glyph";

/** Camera-distance multiples of a well's own size at which its coarse markers appear. */
export const MARKER_RANGE_FACTOR = 2.4;

/**
 * Level of detail of one wellbore: full primitives only for the focused one; the others show the
 * trajectory tube and wellhead glyph, plus coarse component markers when the camera is within
 * range (far away the markers would be sub-pixel noise).
 */
export function lodFor(focused: boolean, cameraDistanceM: number, wellSizeM: number): Lod {
  if (focused) return "full";
  return cameraDistanceM <= Math.max(wellSizeM, 100) * MARKER_RANGE_FACTOR ? "markers" : "glyph";
}

export interface InstanceCounts {
  /** Wellhead glyph instances (non-focused wells with a spec). */
  glyphs: number;
  /** Placeholder instances (wells without a spec, loading or failed). */
  placeholders: number;
  /** Coarse markers drawn (only wells in marker range). */
  markers: number;
  /** Pads under every wellbore (one instance each). */
  pads: number;
  /** Merged trajectory tube meshes: always 0 or 1, however many wellbores. */
  tubeMeshes: number;
  /** Draw calls for everything except the focused wellbore's full primitives and the backdrop. */
  drawCalls: number;
}

/** Counts of the instanced far set for a focus and per-well LOD; the draw-call figure is independent of N. */
export function instanceCounts(plan: FieldPlan, focusedId: string | null, lods: ReadonlyMap<string, Lod> = new Map()): InstanceCounts {
  let glyphs = 0;
  let placeholders = 0;
  let markers = 0;
  for (const w of plan.wells) {
    if (w.status !== "spec") {
      placeholders += 1;
      continue;
    }
    if (w.id === focusedId) continue;
    glyphs += 1;
    if ((lods.get(w.id) ?? "glyph") === "markers") markers += w.markers.length;
  }
  const tubeMeshes = glyphs > 0 ? 1 : 0;
  const pads = plan.wells.length;
  const drawCalls = tubeMeshes + (glyphs > 0 ? 1 : 0) + (placeholders > 0 ? 1 : 0) + (markers > 0 ? 1 : 0) + (pads > 0 ? 1 : 0);
  return { glyphs, placeholders, markers, pads, tubeMeshes, drawCalls };
}

export interface Activation {
  selectedId: string | null;
  /** True when the single-wellbore view should open. */
  open: boolean;
}

/**
 * Linked selection: activating an unselected wellbore (scene click, label or list) selects it and
 * flies there; activating the selected one again opens the single-wellbore view.
 */
export function activate(selectedId: string | null, id: string): Activation {
  return id === selectedId ? { selectedId: id, open: true } : { selectedId: id, open: false };
}

export interface FieldSummary {
  total: number;
  withSpec: number;
  missing: number;
  failed: number;
  loading: number;
  empty: boolean;
}

export function summarize(plan: FieldPlan): FieldSummary {
  const n = (s: FieldWellStatus) => plan.wells.filter((w) => w.status === s).length;
  const withSpec = n("spec");
  return { total: plan.wells.length, withSpec, missing: n("missing"), failed: n("error"), loading: n("loading"), empty: withSpec === 0 && n("loading") === 0 };
}
