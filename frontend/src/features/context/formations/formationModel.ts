import { formationSurfaceColors } from "../../../design/formationPalette";
import type { SceneLayerContext } from "../../scene/sceneLayers";
import type { ExploreCommandBus, ExploreCommandOutcome, SourceRef } from "../../scene/exploreCommands";
import {
  LEVEL_PLANE_LABEL,
  LEVEL_PLANE_NOTE,
  type DepthValue,
  type EvidenceLink,
  type FormationLayerSet,
  type FormationPick,
  type FormationSurface,
  type Vec3,
} from "./formationTypes";

/*
 * Pure formation-layer model (TASK-098). No three.js and no React here: everything the viewer draws and
 * everything the panel says is derived from a `FormationLayerSet` by the functions below, so it is unit
 * tested without WebGL. Engineering values (MD/TVD/TVDSS, elevations) come from the read model untouched;
 * this file only converts them to render coordinates (x east, y up, z -north, metres) around the local
 * render origin of the viewer and never re-derives or smooths them.
 */

/** Marker shapes: surfaces are told apart by shape + glyph + name, never by colour alone. */
export const MARKER_SHAPES = ["sphere", "diamond", "box", "cone"] as const;
export type MarkerShape = (typeof MARKER_SHAPES)[number];
export const SHAPE_GLYPH: Record<MarkerShape, string> = { sphere: "●", diamond: "◆", box: "■", cone: "▲" };

export const SURFACE_COLORS = formationSurfaceColors;

export const MAX_MARKERS = 2000;
export const MAX_PLANES = 64;
export const MAX_LABELS = 48;
/** Base marker radius [m] at exaggeration 1; display size only. */
export const MARKER_BASE_RADIUS_M = 2.5;
export const MARKER_MAX_RADIUS_M = 40;

export type NotDrawnKind = "conflict" | "unsupported" | "blocked" | "unlocated" | "tier" | "limit";

export interface NotDrawnItem {
  id: string;
  kind: NotDrawnKind;
  name: string;
  /** Backend block-reason code, or a local code (`tier_not_rendered`, `limit`, `not_placed`, `not_validated`, `plane_unit`). */
  reason: string;
  message: string;
}

export interface MarkerPlacement {
  id: string;
  surfaceKey: string;
  surfaceName: string;
  name: string;
  /** Render position relative to the viewer origin (single-precision safe: the origin offset is removed in double first). */
  position: Vec3;
  styleIndex: number;
  shape: MarkerShape;
  color: string;
  /** Label chip text. */
  label: string;
  wellboreId: string;
}

export interface PlanePlacement {
  id: string;
  surfaceKey: string;
  name: string;
  center: Vec3;
  /** Extent along render x (east) and render z (north), metres, unexaggerated. */
  width: number;
  depth: number;
  styleIndex: number;
  color: string;
  label: string;
  note: string;
  sourceText: string;
  statusText: string;
}

export interface LegendItem {
  surfaceKey: string;
  name: string;
  tier: string;
  tierLabel: string;
  status: string;
  scope: string;
  styleIndex: number;
  shape: MarkerShape;
  glyph: string;
  color: string;
  markerCount: number;
  planeDrawn: boolean;
  /** Why the plane is not drawn (empty when drawn or when the surface has no plane tier). */
  planeBlocked: string[];
  evidenceCount: number;
}

export interface FormationScene {
  markers: MarkerPlacement[];
  planes: PlanePlacement[];
  legend: LegendItem[];
  notDrawn: NotDrawnItem[];
  /** Set when nothing at all can be shown. */
  emptyText: string | null;
}

const NOT_VALIDATED = new Set(["invalid", "unsupported", "conflicting"]);

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
const isMetre = (u: string | null | undefined) => u !== null && u !== undefined && ["m", "metre", "metres", "meter", "meters"].includes(u.trim().toLowerCase());

/** Render coordinates of an ENU point: subtract the frame origin in double precision, then offset by the viewer origin. */
export function enuToRender(enu: readonly number[], frameOrigin: readonly number[] | null | undefined, origin: Vec3): Vec3 {
  const o = frameOrigin ?? [0, 0, 0];
  const e = (enu[0] ?? 0) - (o[0] ?? 0);
  const n = (enu[1] ?? 0) - (o[1] ?? 0);
  const u = (enu[2] ?? 0) - (o[2] ?? 0);
  return [origin[0] + e, origin[1] + u, origin[2] - n];
}

export function markerRadius(exaggeration: number | null): number {
  const f = exaggeration !== null && Number.isFinite(exaggeration) && exaggeration > 0 ? exaggeration : 1;
  return Math.min(MARKER_MAX_RADIUS_M, MARKER_BASE_RADIUS_M * Math.max(1, f));
}

/** Plane fill opacity: translucent, and only a faint fill through the cutaway so the sectioned equipment stays readable. */
export function planeOpacity(base: number, cutaway: boolean): number {
  const b = Math.min(0.6, Math.max(0.05, base));
  return cutaway ? Math.min(b, 0.1) : b;
}

const fmtNum = (v: number): string => String(Number(v.toFixed(2)));
const REF_TEXT: Record<DepthValue["reference"], string> = { md: "MD", tvd: "TVD", tvdss: "TVDSS", scene_elevation: "Scene elevation" };

export function datumText(d: DepthValue): string {
  if (d.datum_status === "stated") return `datum ${d.datum ?? "stated"}`;
  if (d.datum_status === "unknown") return "datum unknown, not assumed";
  return d.reference === "scene_elevation" ? "scene frame, from trajectory" : "along bore";
}

/** `TVDSS 2100 m (datum MSL)`; unknown depths state why instead of showing a number. */
export function formatDepth(d: DepthValue | null | undefined, fallbackRef: DepthValue["reference"]): string {
  const ref = REF_TEXT[d?.reference ?? fallbackRef];
  if (d === null || d === undefined) return `${ref} not stated`;
  if (d.value === null || d.value === undefined) return `${ref} unknown - ${d.unknown_reason ?? "no reason given"}`;
  return `${ref} ${fmtNum(d.value)} ${d.unit ?? ""} (${datumText(d)})`.replace("  ", " ");
}

function evidenceCount(s: FormationSurface): number {
  return s.evidence.length + s.picks.reduce((n, p) => n + p.evidence.length, 0);
}

function planeSourceText(s: FormationSurface): string {
  const pick = s.plane?.source_pick_id ? s.picks.find((p) => p.pick_id === s.plane?.source_pick_id) : undefined;
  const from = pick ? `pick "${pick.name}"${pick.md?.value != null ? ` at ${formatDepth(pick.md, "md")}` : ""}` : "stated picks";
  const n = evidenceCount(s);
  return `source: ${from}, ${n} source link${n === 1 ? "" : "s"}`;
}

/** Stable style slot per surface: independent of response order. */
function styleIndexes(set: FormationLayerSet): Map<string, number> {
  const keys = [...new Set(set.surfaces.map((s) => s.surface_key))].sort();
  return new Map(keys.map((k, i) => [k, i]));
}

export function buildFormationScene(set: FormationLayerSet | null, ctx: Pick<SceneLayerContext, "origin">): FormationScene {
  const out: FormationScene = { markers: [], planes: [], legend: [], notDrawn: [], emptyText: null };
  if (set === null) return out;
  const frameOrigin = set.frame.origin_enu;
  const styles = styleIndexes(set);
  const conflicted = new Map(set.conflicts.map((c) => [c.pick_id, c]));

  for (const b of set.blocked) out.notDrawn.push({ id: `layer:${b.reason}`, kind: "blocked", name: "Formation layer", reason: b.reason, message: b.message });
  for (const c of set.conflicts) {
    out.notDrawn.push({ id: `conflict:${c.pick_id}`, kind: "conflict", name: pickName(set, c.pick_id), reason: c.reason, message: c.message });
  }
  for (const u of set.unsupported) {
    out.notDrawn.push({
      id: `unsupported:${u.pick_id}`,
      kind: "unsupported",
      name: u.surface_name ?? "Formation pick",
      reason: u.reason,
      message: u.qualifier ? `${u.message} (qualifier ${u.qualifier})` : u.message,
    });
  }

  const planeCandidates: PlanePlacement[] = [];
  for (const s of set.surfaces) {
    const si = styles.get(s.surface_key) ?? 0;
    const shape = MARKER_SHAPES[si % MARKER_SHAPES.length] as MarkerShape;
    const color = SURFACE_COLORS[si % SURFACE_COLORS.length] as string;
    let markerCount = 0;
    for (const p of s.picks) {
      const reason = pickBlock(p, conflicted.has(p.pick_id));
      if (reason !== null) {
        // Conflicts are already listed from `set.conflicts`; do not list them twice.
        if (!conflicted.has(p.pick_id)) out.notDrawn.push({ id: `pick:${p.pick_id}`, kind: reason.code === "not_placed" ? "unlocated" : "blocked", name: p.name, reason: reason.code, message: reason.message });
        continue;
      }
      if (out.markers.length >= MAX_MARKERS) {
        out.notDrawn.push({ id: `pick:${p.pick_id}`, kind: "limit", name: p.name, reason: "limit", message: `Marker limit (${MAX_MARKERS}) reached; pick listed, not drawn.` });
        continue;
      }
      markerCount += 1;
      out.markers.push({
        id: p.pick_id,
        surfaceKey: s.surface_key,
        surfaceName: s.name,
        name: p.name,
        position: enuToRender(p.position_enu as number[], frameOrigin, ctx.origin),
        styleIndex: si,
        shape,
        color,
        label: `${p.name} (${p.label})`,
        wellboreId: p.wellbore_id,
      });
    }

    const planeBlocked: string[] = [];
    let planeDrawn = false;
    if (s.tier === "T2") {
      const plane = s.plane;
      if (s.blocked.length > 0) {
        for (const b of s.blocked) {
          planeBlocked.push(`${b.reason}: ${b.message}`);
          out.notDrawn.push({ id: `blocked:${s.surface_key}:${b.reason}`, kind: "blocked", name: s.name, reason: b.reason, message: `Level plane not drawn. ${b.message}` });
        }
      } else if (plane === null || plane === undefined) {
        const msg = "The surface carries no level plane.";
        planeBlocked.push(`no_plane: ${msg}`);
        out.notDrawn.push({ id: `blocked:${s.surface_key}:no_plane`, kind: "blocked", name: s.name, reason: "no_plane", message: `Level plane not drawn. ${msg}` });
      } else if (!finite(plane.elevation.value) || !isMetre(plane.elevation.unit)) {
        const msg = "The plane elevation is not a metre value in the scene frame.";
        planeBlocked.push(`plane_unit: ${msg}`);
        out.notDrawn.push({ id: `blocked:${s.surface_key}:plane_unit`, kind: "blocked", name: s.name, reason: "plane_unit", message: `Level plane not drawn. ${msg}` });
      } else {
        const f = plane.footprint;
        const cx = (f.min_east + f.max_east) / 2;
        const cn = (f.min_north + f.max_north) / 2;
        planeCandidates.push({
          id: planeId(s.surface_key),
          surfaceKey: s.surface_key,
          name: s.name,
          center: enuToRender([cx, cn, plane.elevation.value as number], frameOrigin, ctx.origin),
          width: f.max_east - f.min_east,
          depth: f.max_north - f.min_north,
          styleIndex: si,
          color,
          label: `${s.name}: ${plane.label || LEVEL_PLANE_LABEL}`,
          note: plane.note || LEVEL_PLANE_NOTE,
          sourceText: planeSourceText(s),
          statusText: `status: ${plane.status}`,
        });
        planeDrawn = true;
      }
    } else if (s.tier === "T3" || s.tier === "T4") {
      const msg = `${s.tier_label}: this build draws pick markers and level planes only; picks stay visible.`;
      planeBlocked.push(`tier_not_rendered: ${msg}`);
      out.notDrawn.push({ id: `tier:${s.surface_key}`, kind: "tier", name: s.name, reason: "tier_not_rendered", message: msg });
      for (const b of s.blocked) out.notDrawn.push({ id: `blocked:${s.surface_key}:${b.reason}`, kind: "blocked", name: s.name, reason: b.reason, message: b.message });
    } else {
      for (const b of s.blocked) {
        planeBlocked.push(`${b.reason}: ${b.message}`);
        out.notDrawn.push({ id: `blocked:${s.surface_key}:${b.reason}`, kind: "blocked", name: s.name, reason: b.reason, message: b.message });
      }
    }

    out.legend.push({
      surfaceKey: s.surface_key,
      name: s.name,
      tier: s.tier,
      tierLabel: s.tier_label,
      status: s.status,
      scope: s.scope,
      styleIndex: si,
      shape,
      glyph: SHAPE_GLYPH[shape],
      color,
      markerCount,
      planeDrawn,
      planeBlocked,
      evidenceCount: evidenceCount(s),
    });
  }

  // Fixed draw order: deepest (lowest) plane first, so translucent layers blend in a stable order without per-frame sorting.
  planeCandidates.sort((a, b) => a.center[1] - b.center[1] || a.surfaceKey.localeCompare(b.surfaceKey));
  planeCandidates.forEach((p, i) => {
    if (i < MAX_PLANES) out.planes.push(p);
    else {
      out.notDrawn.push({ id: `limit:${p.surfaceKey}`, kind: "limit", name: p.name, reason: "limit", message: `Plane limit (${MAX_PLANES}) reached; surface listed, not drawn.` });
      const l = out.legend.find((x) => x.surfaceKey === p.surfaceKey);
      if (l) {
        l.planeDrawn = false;
        l.planeBlocked.push("limit: plane limit reached");
      }
    }
  });

  if (out.markers.length === 0 && out.planes.length === 0 && set.surfaces.length === 0 && out.notDrawn.length === 0) {
    out.emptyText = set.empty_reason ?? "No formation picks for this scope";
  } else if (out.markers.length === 0 && out.planes.length === 0) {
    out.emptyText = "Nothing can be drawn for this scope; see the reasons below.";
  }
  return out;
}

export const planeId = (surfaceKey: string) => `plane:${surfaceKey}`;

function pickName(set: FormationLayerSet, pickId: string): string {
  for (const s of set.surfaces) {
    const p = s.picks.find((x) => x.pick_id === pickId);
    if (p) return p.name;
  }
  return "Formation pick";
}

function pickBlock(p: FormationPick, conflicted: boolean): { code: string; message: string } | null {
  if (conflicted) return { code: "tvd_conflict", message: "Source depth conflicts with the trajectory." };
  if (NOT_VALIDATED.has(p.validation_state)) return { code: "not_validated", message: `Pick is ${p.validation_state}; listed, not drawn.` };
  const e = p.position_enu;
  if (!e || e.length !== 3 || !e.every(finite)) return { code: "not_placed", message: "Pick has no placed position (unlocated); not drawn." };
  return null;
}

export interface LabelItem {
  id: string;
  kind: "pick" | "plane";
  position: readonly [number, number, number];
  lines: string[];
  selected: boolean;
}

/** Which labels are drawn: bounded count, the selected/hovered one always first. Pure; exported for tests. */
export function pickLabels(
  markers: readonly MarkerPlacement[],
  planes: readonly PlanePlacement[],
  mode: "all" | "selected" | "off",
  selectedId: string | null,
  hoverId: string | null,
): LabelItem[] {
  if (mode === "off") return [];
  const all: LabelItem[] = [
    ...planes.map<LabelItem>((p) => ({
      id: p.id,
      kind: "plane",
      position: [p.center[0] - p.width / 2, p.center[1], p.center[2] + p.depth / 2],
      lines: p.id === selectedId ? [p.label, p.note, p.statusText, p.sourceText] : [p.label, p.note],
      selected: p.id === selectedId,
    })),
    ...markers.map<LabelItem>((m) => ({ id: m.id, kind: "pick", position: m.position, lines: [m.label], selected: m.id === selectedId })),
  ];
  const hot = (l: LabelItem) => l.id === selectedId || l.id === hoverId;
  const ranked = [...all.filter(hot), ...(mode === "all" ? all.filter((l) => !hot(l)) : [])];
  return ranked.slice(0, MAX_LABELS);
}

// ---------------------------------------------------------------------------------------------------------------------
// Inspector
// ---------------------------------------------------------------------------------------------------------------------

export interface InspectorRow {
  label: string;
  value: string;
}

export interface InspectorModel {
  id: string;
  kind: "pick" | "plane";
  title: string;
  /** Always shown: tier and interpretation wording. */
  tierLabel: string;
  statusText: string;
  rows: InspectorRow[];
  notes: string[];
  evidence: EvidenceLink[];
  /** Wellbore the camera focus request targets; null when the surface spans several. */
  wellboreId: string | null;
}

export function inspectorModel(set: FormationLayerSet | null, id: string | null): InspectorModel | null {
  if (set === null || id === null) return null;
  for (const s of set.surfaces) {
    const p = s.picks.find((x) => x.pick_id === id);
    if (p) return pickInspector(s, p);
    if (planeId(s.surface_key) === id && s.plane) return planeInspector(s);
  }
  return null;
}

function pickInspector(s: FormationSurface, p: FormationPick): InspectorModel {
  const rows: InspectorRow[] = [
    { label: "Surface", value: s.name },
    { label: "MD", value: formatDepth(p.md, "md") },
    { label: "TVD", value: formatDepth(p.tvd, "tvd") },
    { label: "TVDSS", value: formatDepth(p.tvdss, "tvdss") },
  ];
  if (p.twt) rows.push({ label: "TWT", value: formatDepth(p.twt, "md").replace(/^MD/, "TWT") });
  if (p.scene_elevation) rows.push({ label: "Scene elevation", value: formatDepth(p.scene_elevation, "scene_elevation") });
  rows.push({ label: "Qualifier", value: p.qualifier ?? "none" });
  rows.push({ label: "Validation", value: p.validation_state });
  rows.push({ label: "Extraction method", value: p.extraction_method ?? "not stated" });
  const notes: string[] = [];
  if (p.source_dip || p.source_azimuth) notes.push("Source dip/azimuth are attributes only; planes stay level.");
  return {
    id: p.pick_id,
    kind: "pick",
    title: p.name,
    tierLabel: `${p.tier} pick marker`,
    statusText: p.label || `pick - ${p.status}`,
    rows,
    notes,
    evidence: p.evidence,
    wellboreId: p.wellbore_id,
  };
}

function planeInspector(s: FormationSurface): InspectorModel {
  const plane = s.plane as NonNullable<FormationSurface["plane"]>;
  const f = plane.footprint;
  return {
    id: planeId(s.surface_key),
    kind: "plane",
    title: s.name,
    tierLabel: s.tier_label,
    statusText: `${plane.label || LEVEL_PLANE_LABEL} (${plane.status})`,
    rows: [
      { label: "Surface", value: s.name },
      { label: "Elevation", value: formatDepth(plane.elevation, "scene_elevation") },
      { label: "Footprint", value: `E ${fmtNum(f.min_east)}..${fmtNum(f.max_east)} m, N ${fmtNum(f.min_north)}..${fmtNum(f.max_north)} m (margin ${fmtNum(f.margin_m)} m)` },
      { label: "Source", value: planeSourceText(s) },
    ],
    notes: [plane.note || LEVEL_PLANE_NOTE, "Drawn at true scale, not vertically exaggerated."],
    evidence: s.evidence.length > 0 ? s.evidence : (s.picks.find((p) => p.pick_id === plane.source_pick_id)?.evidence ?? []),
    wellboreId: s.wellbore_ids.length === 1 ? (s.wellbore_ids[0] as string) : null,
  };
}

// ---------------------------------------------------------------------------------------------------------------------
// Focus target for the camera lane (pure: the rig decides how to fly)
// ---------------------------------------------------------------------------------------------------------------------

export interface FormationFocusTarget {
  id: string;
  kind: "pick" | "plane";
  /** Point to look at, render coordinates (metres). */
  target: Vec3;
  /** Radius of what should be framed, metres. */
  radius: number;
  /** Suggested camera distance from the target, metres. */
  distance: number;
  wellboreId: string | null;
}

/**
 * Pose request for `focusFormation`. `formationId` is a pick id, a surface key or `plane:<surfaceKey>`.
 * Returns null for ids that are unknown, belong to another wellbore, or cannot be placed (the camera then ignores
 * the command and the caller announces it).
 */
export function formationFocusTarget(
  set: FormationLayerSet | null,
  formationId: string,
  ctx: Pick<SceneLayerContext, "origin">,
  wellboreId: string | null = null,
): FormationFocusTarget | null {
  if (set === null) return null;
  const scene = buildFormationScene(set, ctx);
  const marker = scene.markers.find((m) => m.id === formationId);
  if (marker && (wellboreId === null || marker.wellboreId === wellboreId)) {
    return { id: marker.id, kind: "pick", target: marker.position, radius: 25, distance: 80, wellboreId: marker.wellboreId };
  }
  const key = formationId.startsWith("plane:") ? formationId.slice(6) : formationId;
  const surface = set.surfaces.find((s) => s.surface_key === key);
  if (!surface || (wellboreId !== null && !surface.wellbore_ids.includes(wellboreId))) return null;
  const plane = scene.planes.find((p) => p.surfaceKey === key);
  if (plane && (formationId.startsWith("plane:") || !scene.markers.some((m) => m.surfaceKey === key && (wellboreId === null || m.wellboreId === wellboreId)))) {
    const radius = Math.hypot(plane.width, plane.depth) / 2;
    return { id: plane.id, kind: "plane", target: plane.center, radius, distance: Math.max(80, radius * 2), wellboreId: surface.wellbore_ids.length === 1 ? (surface.wellbore_ids[0] as string) : null };
  }
  const first = scene.markers.find((m) => m.surfaceKey === key && (wellboreId === null || m.wellboreId === wellboreId));
  if (first) return { id: first.id, kind: "pick", target: first.position, radius: 25, distance: 80, wellboreId: first.wellboreId };
  return null;
}

/** Selection id for a formation reference (pick id, surface key or plane id), or null when unknown. */
export function resolveFormationId(set: FormationLayerSet | null, formationId: string, wellboreId: string | null = null): string | null {
  if (set === null) return null;
  for (const s of set.surfaces) {
    if (wellboreId !== null && !s.wellbore_ids.includes(wellboreId)) continue;
    if (s.picks.some((p) => p.pick_id === formationId)) return formationId;
    if (formationId === s.surface_key || formationId === planeId(s.surface_key)) {
      if (s.plane) return planeId(s.surface_key);
      const p = s.picks[0];
      if (p) return p.pick_id;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------------------------------------------------
// Command-bus helpers (explicit outcome handling)
// ---------------------------------------------------------------------------------------------------------------------

/** Source reference for the evidence viewer; null when the link names no document. */
export function evidenceToSourceRef(link: EvidenceLink): SourceRef | null {
  const loc = link.locator as { kind: string; document_id?: string; page?: number; table_id?: string | null; cell_id?: string | null };
  const documentId = link.document_id ?? loc.document_id ?? null;
  if (documentId === null) return null;
  const ref: SourceRef = { documentId };
  if (loc.kind === "pdf" && finite(loc.page)) {
    ref.page = loc.page;
    const extra = [loc.table_id ? `table ${loc.table_id}` : null, loc.cell_id ? `cell ${loc.cell_id}` : null].filter(Boolean);
    if (extra.length > 0) ref.locator = extra.join(", ");
  } else ref.locator = loc.kind;
  return ref;
}

export interface CommandResult {
  ok: boolean;
  /** Text to announce; null when the command was handled. */
  message: string | null;
  outcome: ExploreCommandOutcome | "no-bus" | "no-document";
}

export function openSourceMessage(outcome: ExploreCommandOutcome): string | null {
  if (outcome === "handled") return null;
  if (outcome === "unhandled") return "The source document could not be opened (it may have been removed).";
  return "The source viewer is not available in this view.";
}

export function openFormationSource(bus: Pick<ExploreCommandBus, "dispatch"> | null, link: EvidenceLink): CommandResult {
  const source = evidenceToSourceRef(link);
  if (source === null) return { ok: false, message: "This evidence link names no document.", outcome: "no-document" };
  if (bus === null) return { ok: false, message: openSourceMessage("no-subscriber"), outcome: "no-bus" };
  const outcome = bus.dispatch({ type: "openSource", source });
  return { ok: outcome === "handled", message: openSourceMessage(outcome), outcome };
}

export function focusFormationMessage(outcome: ExploreCommandOutcome): string | null {
  if (outcome === "handled") return null;
  if (outcome === "unhandled") return "That formation is not in the loaded data (stale or missing); the camera did not move.";
  return "The camera is not available to focus this formation.";
}

export function requestFocusFormation(bus: Pick<ExploreCommandBus, "dispatch"> | null, wellboreId: string, formationId: string): CommandResult {
  if (bus === null) return { ok: false, message: focusFormationMessage("no-subscriber"), outcome: "no-bus" };
  const outcome = bus.dispatch({ type: "focusFormation", wellboreId, formationId });
  return { ok: outcome === "handled", message: focusFormationMessage(outcome), outcome };
}
