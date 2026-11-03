import { buildSceneModel, defaultExaggeration, locatedMdMax, type SceneModel, type VisualAssetSpec } from "./sceneModel";
import { WellPath, type TrajectoryInput, type Vec3 } from "./trajectory";

/**
 * Pure model of the field view: ALL wellbores of the project in one scene. Nothing here touches
 * the GPU, so layout, level of detail, instancing counts and selection are unit-tested.
 *
 * Only RECONSTRUCTED wellbores (with an asset spec) are listed and drawn; wellbores without one are
 * counted in the summary only. Failed spec loads stay listed (retryable).
 *
 * Positions: when every placed wellbore states a planar surface location (easting/northing) with the
 * same stated CRS, datum and a metre unit, wells sit at E/N offsets from the placed set's centroid
 * (double-precision maths, the centroid is subtracted before anything reaches float32). Otherwise
 * (mixed/unstated CRS, datum or unit, or no locations at all) a schematic grid in listing order is
 * used and labelled as such. Nothing is ever reprojected or guessed. Wells without a location in an
 * otherwise located set (and failed loads) go to a labelled "unlocated" holding row south of the field.
 */

export const FIELD_LAYOUT_LABEL = "Schematic layout, not map positions";
export const surfaceLayoutLabel = (crs: string): string => `Surface-location layout (E/N offsets from the field centroid, ${crs})`;
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

/** Planar surface location exactly as stated by the trajectory route (never reprojected). */
export interface SurfaceLocation {
  easting: number;
  northing: number;
  crs: string | null;
  datum: string | null;
  unit: string | null;
}

export type Placement = "surface" | "unlocated" | "schematic";

/** Default tube radius of a hole of this depth: the selected-state rule, so traces are visible unselected. */
export function tubeRadiusFor(depthM: number): number {
  return Math.max(0.05, defaultExaggeration(depthM) * 0.035);
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
  /** Wellhead position in render metres relative to the field centroid (Y = 0; x = east, z = -north). */
  position: Vec3;
  placement: Placement;
  /** Display-only pad half-width/glyph/tube sizes of this well (limited by its nearest neighbour). */
  padHalfM: number;
  glyphHeightM: number;
  glyphRadiusM: number;
  markerRadiusM: number;
  tubeRadiusM: number;
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
  layoutKind: "surface" | "schematic";
  /** Why the schematic grid is used (null for the surface layout). */
  layoutNote: string | null;
  /** Stated CRS / datum / unit of the surface layout. */
  layoutFrame: { crs: string; datum: string | null; unit: string } | null;
  /** Nearest-neighbour distance among drawn wellheads (null for fewer than two). */
  nearestM: number | null;
  /** Render-space bounds of wellheads and traces (X/Z) and the deepest trace: drives framing. */
  bounds: { minX: number; maxX: number; minZ: number; maxZ: number; depthM: number };
  /** Camera framing sphere (centre in render coordinates). */
  framing: { center: Vec3; radiusM: number };
  /** Wellbores of the project listing that are not drawn, kept for the summary. */
  totals: { listed: number; missing: number; loading: number };
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

/** Depth and horizontal extent (relative to the wellhead) of a path's vertices. */
function extentsOf(path: WellPath): { depth: number; minX: number; maxX: number; minZ: number; maxZ: number } {
  const e = { depth: 0, minX: 0, maxX: 0, minZ: 0, maxZ: 0 };
  for (const v of path.vertices()) {
    e.depth = Math.max(e.depth, Math.abs(v.position[1]));
    e.minX = Math.min(e.minX, v.position[0]);
    e.maxX = Math.max(e.maxX, v.position[0]);
    e.minZ = Math.min(e.minZ, v.position[2]);
    e.maxZ = Math.max(e.maxZ, v.position[2]);
  }
  return e;
}

const norm = (s: string | null): string | null => (s === null ? null : s.trim().replace(/\s+/g, " ").toLowerCase());
const METRE_UNITS = new Set(["m", "meter", "meters", "metre", "metres"]);

export interface SurfaceFrame {
  crs: string;
  datum: string | null;
  unit: string;
}

/**
 * The common frame of surface locations, or the reason there is none. Requires a stated CRS and a
 * metre unit on every location and identical CRS/datum/unit (case and whitespace insensitive; an
 * unstated datum only matches another unstated datum). Feet and other units are not converted.
 */
export function commonSurfaceFrame(locations: readonly SurfaceLocation[]): { frame: SurfaceFrame } | { reason: string } {
  if (locations.length === 0) return { reason: "no wellbore states a surface location" };
  const first = locations[0]!;
  if (first.crs === null || norm(first.crs) === "") return { reason: "a surface location does not state its CRS" };
  for (const l of locations) {
    if (l.crs === null || norm(l.crs) === "") return { reason: "a surface location does not state its CRS" };
    if (l.unit === null) return { reason: "a surface location does not state its unit" };
    if (!METRE_UNITS.has(norm(l.unit)!)) return { reason: `surface-location unit "${l.unit}" is not metres (no unit conversion is done)` };
    if (norm(l.crs) !== norm(first.crs)) return { reason: "surface locations use different CRSs" };
    if (norm(l.datum) !== norm(first.datum)) return { reason: "surface locations use different datums" };
  }
  return { frame: { crs: first.crs.trim(), datum: first.datum, unit: "m" } };
}

/** Nearest-neighbour distance of every point (Infinity for a single point). O(n²), n is the project's wellbore count. */
export function nearestNeighbours(points: readonly (readonly [number, number])[]): number[] {
  return points.map((p, i) => {
    let best = Infinity;
    points.forEach((q, j) => {
      if (i !== j) best = Math.min(best, Math.hypot(p[0] - q[0], p[1] - q[1]));
    });
    return best;
  });
}

function markersOf(model: SceneModel): FieldMarker[] {
  return model.downhole.map((el) => {
    const md = el.mdTopM !== null && el.mdBottomM !== null ? (el.mdTopM + el.mdBottomM) / 2 : (el.mdTopM ?? 0);
    return { id: el.id, kind: el.kind, position: model.path.at(md).position, illustrative: el.illustrative };
  });
}

/**
 * Builds the plan. `trajectoryOf` supplies validated survey stations when an API provides them
 * (a well without one draws the labelled vertical placeholder with `reasonOf`, like the single view).
 */
export function buildFieldPlan(
  inputs: readonly FieldWellInput[],
  trajectoryOf: (id: string) => TrajectoryInput | null = () => null,
  reasonOf: (id: string) => string = () => "no survey is available for this wellbore",
  surfaceOf: (id: string) => SurfaceLocation | null = () => null,
): FieldPlan {
  // Only reconstructed wellbores are drawn and listed (failed loads stay, so they can be retried).
  const drawn = inputs.filter((w) => w.spec.kind === "ready" || w.spec.kind === "error");
  const totals = {
    listed: inputs.length,
    missing: inputs.filter((w) => w.spec.kind === "missing").length,
    loading: inputs.filter((w) => w.spec.kind === "loading").length,
  };
  const built = drawn.map((w) => {
    if (w.spec.kind !== "ready") return { w, model: null as SceneModel | null, ext: extentsOf(WellPath.unavailable(100, "")), surface: null as SurfaceLocation | null };
    const mdMax = Math.max(locatedMdMax(w.spec.spec), 100);
    const traj = trajectoryOf(w.id);
    const path = traj !== null ? WellPath.fromTrajectory(traj, mdMax) : WellPath.unavailable(mdMax, reasonOf(w.id));
    const loc = surfaceOf(w.id);
    return { w, model: buildSceneModel(w.spec.spec, path), ext: extentsOf(path), surface: loc !== null && Number.isFinite(loc.easting) && Number.isFinite(loc.northing) ? loc : null };
  });
  const maxDepth = Math.max(0, ...built.map((b) => b.ext.depth));
  // Spacing follows the deepest hole so deep wells do not read as needles; a floor keeps shallow fields apart.
  const gridSpacingM = Math.max(300, Math.round((maxDepth * 0.3) / 50) * 50);

  // Layout decision. The placed set is the wells with a spec; wells without a location (or failed
  // loads) cannot be placed on a map and go to the holding row when the rest is located.
  const specBuilt = built.filter((b) => b.model !== null);
  const located = specBuilt.filter((b) => b.surface !== null);
  const common = commonSurfaceFrame(located.map((b) => b.surface!));
  const useSurface = located.length > 0 && "frame" in common;
  let layoutNote: string | null = null;
  if (!useSurface) layoutNote = "reason" in common ? common.reason : "no wellbore states a surface location";
  const frame = useSurface && "frame" in common ? common.frame : null;

  const positions: Vec3[] = [];
  const placements: Placement[] = [];
  const cells: { col: number; row: number }[] = [];
  let cols = 0;
  let rows = 0;
  let spacingM = gridSpacingM;
  if (frame !== null) {
    // Double precision for the offsets; the centroid is removed before anything becomes float32.
    const cE = located.reduce((s, b) => s + b.surface!.easting, 0) / located.length;
    const cN = located.reduce((s, b) => s + b.surface!.northing, 0) / located.length;
    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    for (const b of located) {
      const x = b.surface!.easting - cE;
      const z = -(b.surface!.northing - cN);
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minZ = Math.min(minZ, z);
      maxZ = Math.max(maxZ, z);
    }
    const spread = Math.max(maxX - minX, maxZ - minZ, 1);
    const held = built.filter((b) => b.surface === null || b.model === null).length;
    const gap = Math.max(spread * 0.25, 100);
    const heldStep = Math.max(spread * 0.1, 60);
    let heldIndex = 0;
    for (const b of built) {
      if (b.model !== null && b.surface !== null) {
        positions.push([b.surface.easting - cE, 0, -(b.surface.northing - cN)]);
        placements.push("surface");
      } else {
        positions.push([(minX + maxX) / 2 + (heldIndex - (held - 1) / 2) * heldStep, 0, maxZ + gap]);
        placements.push("unlocated");
        heldIndex += 1;
      }
      cells.push({ col: 0, row: 0 });
    }
    spacingM = Math.max(spread, 1);
  } else {
    const layout = gridLayout(built.length, gridSpacingM);
    const dims = gridDimensions(built.length);
    cols = dims.cols;
    rows = dims.rows;
    for (const c of layout) {
      positions.push([...c.position] as Vec3);
      placements.push("schematic");
      cells.push({ col: c.col, row: c.row });
    }
  }

  // Framing bounds: wellheads plus the horizontal reach of every trace, and the deepest hole.
  let bMinX = Infinity;
  let bMaxX = -Infinity;
  let bMinZ = Infinity;
  let bMaxZ = -Infinity;
  built.forEach((b, i) => {
    const p = positions[i]!;
    bMinX = Math.min(bMinX, p[0] + b.ext.minX);
    bMaxX = Math.max(bMaxX, p[0] + b.ext.maxX);
    bMinZ = Math.min(bMinZ, p[2] + b.ext.minZ);
    bMaxZ = Math.max(bMaxZ, p[2] + b.ext.maxZ);
  });
  if (built.length === 0) [bMinX, bMaxX, bMinZ, bMaxZ] = [0, 0, 0, 0];
  const horizontal = Math.max(bMaxX - bMinX, bMaxZ - bMinZ);
  const span = frame !== null ? horizontal : Math.max((cols - 1) * gridSpacingM, (rows - 1) * gridSpacingM, gridSpacingM);
  const extentM = Math.max(span, maxDepth, 300);
  const nn = nearestNeighbours(positions.map((p) => [p[0], p[2]] as const));
  const nearestM = built.length < 2 ? null : Math.min(...nn);
  // Display sizes: global caps from the field extent; each well is further limited by its nearest
  // neighbour (pad half-width 0.4 x distance, so pads never overlap) for same-platform wellheads a few
  // metres apart. Only a tiny absolute floor guards coincident wellheads: at field zoom such pads are
  // sub-pixel by design and become readable when the camera closes in.
  const globalPad = Math.max(extentM * 0.028 * 1.6, spacingM * 0.16);
  const padFloor = 0.5;
  const wells: FieldWell[] = built.map(({ w, model, ext }, index) => {
    const cell = cells[index]!;
    const depth = ext.depth;
    const pad = Math.min(globalPad, Math.max(padFloor, nn[index]! * 0.4));
    const s = pad / globalPad;
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
      position: positions[index]!,
      placement: placements[index]!,
      padHalfM: pad,
      glyphHeightM: extentM * 0.028 * s,
      glyphRadiusM: extentM * 0.007 * s,
      markerRadiusM: extentM * 0.0045 * Math.max(s, 0.25),
      tubeRadiusM: tubeRadiusFor(depth),
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
    center: [(bMinX + bMaxX) / 2, -maxDepth / 2, (bMinZ + bMaxZ) / 2],
    display: {
      // Same radius a selected tube has (per-well values are in `FieldWell.tubeRadiusM`); the field
      // value is the one of the deepest hole.
      tubeRadiusM: tubeRadiusFor(maxDepth),
      glyphHeightM: extentM * 0.028,
      glyphRadiusM: extentM * 0.007,
      markerRadiusM: extentM * 0.0045,
      padHalfM: globalPad,
    },
    layoutLabel: frame !== null ? surfaceLayoutLabel(frame.crs) : FIELD_LAYOUT_LABEL,
    layoutKind: frame !== null ? "surface" : "schematic",
    layoutNote,
    layoutFrame: frame,
    nearestM,
    bounds: { minX: bMinX, maxX: bMaxX, minZ: bMinZ, maxZ: bMaxZ, depthM: maxDepth },
    framing: {
      center: [(bMinX + bMaxX) / 2, -maxDepth * 0.5, (bMinZ + bMaxZ) / 2],
      radiusM: Math.max(0.85 * 0.5 * Math.hypot(bMaxX - bMinX, bMaxZ - bMinZ, maxDepth), 0.55 * maxDepth, 150),
    },
    totals,
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
  /** Screen-space minimum-width companion line of the tubes: one merged draw call, 0 or 1. */
  tubeLines: number;
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
  const tubeLines = tubeMeshes;
  const drawCalls = tubeMeshes + tubeLines + (glyphs > 0 ? 1 : 0) + (placeholders > 0 ? 1 : 0) + (markers > 0 ? 1 : 0) + (pads > 0 ? 1 : 0);
  return { glyphs, placeholders, markers, pads, tubeMeshes, tubeLines, drawCalls };
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
  const loading = plan.totals.loading;
  return { total: plan.totals.listed, withSpec, missing: plan.totals.missing, failed: n("error"), loading, empty: withSpec === 0 && loading === 0 };
}
