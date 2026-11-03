import type { components } from "../../api/generated";
import { WellPath, type Vec3 } from "./trajectory";

type S = components["schemas"];
export type AssetComponent = S["AssetComponent"];
export type VisualAssetSpec = S["VisualAssetSpec"];
export type ComponentKind = S["ComponentKind"];
export type Representation = S["Representation"];

/** Every kind the renderer registers; mirrors the closed backend enum (a test pins the equality). */
export const COMPONENT_KINDS: readonly ComponentKind[] = [
  "casing",
  "liner",
  "tubing",
  "packer",
  "pump_esp",
  "bearing",
  "plug",
  "nipple",
  "valve",
  "mandrel",
  "perforation_interval",
  "wellhead",
  "christmas_tree",
  "generic_block",
  "separator",
  "choke",
  "manifold",
  "tank",
  "flowline",
  "pump_surface",
];

export type Zone = "downhole" | "surface" | "unlocated";
/** Where a dimension came from: the spec, a tasteful default (illustrative), or derived for display. */
export type DimSource = "spec" | "default" | "interval" | "derived";

const TUBE_KINDS: ReadonlySet<ComponentKind> = new Set(["casing", "liner", "tubing"]);
/** Kinds drawn at surface scale even when the spec locates them at MD (top of hole). */
const WELLHEAD_KINDS: ReadonlySet<ComponentKind> = new Set(["wellhead", "christmas_tree"]);
export const SURFACE_KINDS: ReadonlySet<ComponentKind> = new Set(["separator", "choke", "manifold", "tank", "flowline", "pump_surface"]);

export const isTubeKind = (k: ComponentKind): boolean => TUBE_KINDS.has(k);
export const isSurfaceKind = (k: ComponentKind): boolean => SURFACE_KINDS.has(k);

/** Illustrative defaults in metres: outside diameter and length (or height). Never engineering values. */
export const DEFAULT_DIMS: Record<ComponentKind, { od: number; length: number; id?: number }> = {
  casing: { od: 0.2445, id: 0.2205, length: 100 },
  liner: { od: 0.1778, id: 0.1594, length: 100 },
  tubing: { od: 0.0889, id: 0.0762, length: 100 },
  packer: { od: 0.14, length: 2.2 },
  pump_esp: { od: 0.14, length: 24 },
  bearing: { od: 0.12, length: 1.4 },
  plug: { od: 0.14, length: 1.2 },
  nipple: { od: 0.1, length: 0.8 },
  valve: { od: 0.12, length: 1.6 },
  mandrel: { od: 0.12, length: 3 },
  perforation_interval: { od: 0.25, length: 20 },
  wellhead: { od: 1.1, length: 1.8 },
  christmas_tree: { od: 0.9, length: 3 },
  generic_block: { od: 1.2, length: 2 },
  separator: { od: 2.4, length: 8 },
  choke: { od: 0.35, length: 1.2 },
  manifold: { od: 0.4, length: 6 },
  tank: { od: 6, length: 8 },
  flowline: { od: 0.25, length: 30 },
  pump_surface: { od: 0.7, length: 3 },
};

/** Length of the sample piece shown for an unlocated downhole component (illustrative only). */
const UNLOCATED_SAMPLE_M: Partial<Record<ComponentKind, number>> = { casing: 8, liner: 8, tubing: 8, perforation_interval: 6, pump_esp: 12 };

const M_PER: Record<S["SizeUnit"], number> = { mm: 0.001, in: 0.0254, m: 1, ft: 0.3048 };
export const sizeToMetres = (q: S["SizeQuantity"]): number => q.value * M_PER[q.unit];
export const lengthToMetres = (value: number, unit: S["LengthUnit"]): number => value * (unit === "ft" ? 0.3048 : 1);

export interface PlacementSummary {
  state: "located" | "unlocated" | "surface";
  /** Located: the interval as given (value + unit) and the depth reference. */
  md?: { top: number; bottom: number; unit: S["LengthUnit"]; reference: string };
  /** Why the component is unlocated (spec reason or the viewer's own: outside the MD range). */
  reason?: string;
  /** Surface layout offset (m east/north of the wellhead) and whether the spec gave it or the viewer chose it. */
  offset?: { east: number; north: number; fromSpec: boolean };
}

export interface SceneElement {
  id: string;
  kind: ComponentKind;
  label: string;
  zone: Zone;
  representation: Representation;
  placement: PlacementSummary;
  /** Interval along the path in metres (downhole). */
  mdTopM: number | null;
  mdBottomM: number | null;
  /** Physical outer radius and length (metres, before exaggeration). */
  outerRadiusM: number;
  innerRadiusM: number | null;
  lengthM: number;
  dims: { od: DimSource; id: DimSource; length: DimSource };
  /** Base-centre anchor and axis direction in render coordinates (local origin = wellhead). */
  position: Vec3;
  tangent: Vec3;
  /** Metres above the ground this item starts (a tree stacks on the wellhead). */
  baseOffsetM: number;
  /** Flowline route points, ground-relative (render coordinates), else null. */
  route: Vec3[] | null;
  /** True when the geometry is not backed by the spec (generic or defaulted dimensions). */
  illustrative: boolean;
  /** Scale class: `exaggerated` follows the radius exaggeration, `surface` the surface scale. */
  scaleClass: "exaggerated" | "surface";
  source: AssetComponent;
}

export interface SceneModel {
  path: WellPath;
  elements: SceneElement[];
  downhole: SceneElement[];
  surface: SceneElement[];
  unlocated: SceneElement[];
  /** Centre of the unlocated tray and its half extents (render coordinates), or null when empty. */
  tray: { center: Vec3; halfX: number; halfZ: number } | null;
  byId: Map<string, SceneElement>;
  notes: string[];
}

export interface ModelOptions {
  /** Multiplier on surface equipment and unlocated samples (labelled in the UI). */
  surfaceScale: number;
}

const TRAY_WEST_M = 40;
const TRAY_GAP_M = 4;

/**
 * Pure mapping from a spec and a path to renderable descriptors. Placement rules:
 * located -> interpolated by MD along the path; surface -> ground layout near the wellhead;
 * unlocated (or MD outside the path) -> the separate tray, never an invented depth.
 */
export function buildSceneModel(spec: VisualAssetSpec, path: WellPath, options: ModelOptions = { surfaceScale: 1 }): SceneModel {
  const notes: string[] = [];
  const comps = spec.components ?? [];
  const elements: SceneElement[] = [];
  let surfaceSlot = 0;
  let trayCursor = 0;
  const wh = comps.find((c) => c.kind === "wellhead");
  const whLen = wh?.params?.length ? sizeToMetres(wh.params.length) : DEFAULT_DIMS.wellhead.length;
  const treeBase = wh ? whLen : 0;

  const baseDims = (c: AssetComponent) => {
    const d = DEFAULT_DIMS[c.kind];
    const od = c.params?.od ? sizeToMetres(c.params.od) : null;
    const id = c.params?.id ? sizeToMetres(c.params.id) : null;
    const len = c.params?.length ? sizeToMetres(c.params.length) : null;
    return { d, od, id, len };
  };

  for (const c of comps) {
    const { d, od, id, len } = baseDims(c);
    const dims = {
      od: (od !== null ? "spec" : "default") as DimSource,
      id: (id !== null ? "spec" : "default") as DimSource,
      length: (len !== null ? "spec" : "default") as DimSource,
    };
    let outerR = (od ?? d.od) / 2;
    let innerR: number | null = id !== null ? id / 2 : d.id !== undefined && (c.kind === "casing" || c.kind === "liner" || c.kind === "tubing") ? ((od ?? d.od) / d.od) * (d.id / 2) : null;
    if (innerR !== null && innerR >= outerR) innerR = outerR * 0.9;
    let length = len ?? d.length;
    const placement = c.placement;
    let zone: Zone = "unlocated";
    const summary: PlacementSummary = { state: placement.state };
    let position: Vec3 = [0, 0, 0];
    let tangent: Vec3 = [0, 1, 0];
    let mdTopM: number | null = null;
    let mdBottomM: number | null = null;
    let route: Vec3[] | null = null;
    let baseOffset = 0;
    const scaleClass: SceneElement["scaleClass"] = isSurfaceKind(c.kind) || WELLHEAD_KINDS.has(c.kind) ? "surface" : "exaggerated";

    const toTray = (reason: string) => {
      zone = "unlocated";
      summary.state = "unlocated";
      summary.reason = reason;
      const sample = UNLOCATED_SAMPLE_M[c.kind];
      length = len ?? sample ?? d.length;
      if (len === null) dims.length = "default";
      mdTopM = null;
      mdBottomM = null;
      const w = Math.max(outerR * 2 * options.surfaceScale, 1.2) + TRAY_GAP_M;
      position = [-TRAY_WEST_M, 0, -(trayCursor + w / 2)];
      trayCursor += w;
      tangent = [0, 1, 0];
    };

    if (placement.state === "located") {
      const top = lengthToMetres(placement.md_top, placement.unit);
      const bottom = lengthToMetres(placement.md_bottom, placement.unit);
      summary.md = { top: placement.md_top, bottom: placement.md_bottom, unit: placement.unit, reference: placement.depth_reference };
      if (!path.covers(top) || !path.covers(bottom)) {
        toTray(`MD interval lies outside the trajectory range ${path.mdMin.toFixed(0)}-${path.mdMax.toFixed(0)} m; not placed.`);
        zone = "unlocated";
      } else {
        zone = "downhole";
        mdTopM = top;
        mdBottomM = bottom;
        const mid = path.at((top + bottom) / 2);
        position = mid.position;
        // Local +Y points down-hole -> up-hole is -tangent; the builder uses +Y as the axis, so aim it uphole.
        tangent = [-mid.tangent[0], -mid.tangent[1], -mid.tangent[2]];
        length = bottom - top;
        dims.length = "interval";
        if (WELLHEAD_KINDS.has(c.kind)) {
          // Top of hole: stand on the ground at the path start, stacked on a wellhead if one exists.
          const start = path.at(top).position;
          length = len ?? d.length;
          dims.length = len !== null ? "spec" : "default";
          baseOffset = c.kind === "christmas_tree" ? treeBase : 0;
          position = [start[0], 0, start[2]];
          tangent = [0, 1, 0];
        }
      }
    } else if (placement.state === "surface") {
      zone = "surface";
      if (WELLHEAD_KINDS.has(c.kind)) {
        position = [0, 0, 0];
        baseOffset = c.kind === "christmas_tree" ? treeBase : 0;
        summary.offset = { east: 0, north: 0, fromSpec: false };
      } else {
        const slot = surfaceSlot++;
        const hintE = placement.offset_east_m;
        const hintN = placement.offset_north_m;
        const autoE = -14 + 14 * (slot % 3);
        const autoN = 16 + 14 * Math.floor(slot / 3);
        const e = hintE ?? autoE;
        const n = hintN ?? autoN;
        position = [e, 0, -n];
        summary.offset = { east: e, north: n, fromSpec: hintE !== null && hintE !== undefined && hintN !== null && hintN !== undefined };
        if (c.kind === "flowline") {
          const start: Vec3 = [1.2, 0.6, 0];
          const hinted = (hintE !== null && hintE !== undefined) || (hintN !== null && hintN !== undefined);
          const end: Vec3 = hinted ? [e, 0.6, -n] : [start[0] + length * 0.4, 0.6, -length * 0.6];
          route = [start, [end[0], 0.6, 0], end];
          if (hinted) {
            length = Math.abs(end[0] - start[0]) + Math.abs(end[2]);
            dims.length = "derived";
          }
        }
      }
      tangent = [0, 1, 0];
    } else {
      zone = "unlocated";
      toTray(placement.reason ?? "placement unknown in the sources");
    }
    const illustrative = c.representation === "generic_illustrative" || dims.od === "default";
    if (outerR <= 0) outerR = d.od / 2;
    elements.push({
      id: c.id,
      kind: c.kind,
      label: c.label,
      zone,
      representation: c.representation,
      placement: summary,
      mdTopM,
      mdBottomM,
      outerRadiusM: outerR,
      innerRadiusM: innerR,
      lengthM: length,
      dims,
      position,
      tangent,
      baseOffsetM: baseOffset,
      route,
      illustrative,
      scaleClass,
      source: c,
    });
  }

  // A perforation interval borrows the innermost casing/liner radius covering it (display only).
  for (const el of elements) {
    if (el.kind !== "perforation_interval" || el.zone !== "downhole" || el.dims.od === "spec") continue;
    const host = elements
      .filter((o) => isTubeKind(o.kind) && o.kind !== "tubing" && o.zone === "downhole" && (o.mdTopM ?? 0) <= (el.mdTopM ?? 0) + 1e-6 && (o.mdBottomM ?? 0) >= (el.mdBottomM ?? 0) - 1e-6)
      .sort((a, b) => a.outerRadiusM - b.outerRadiusM)[0];
    if (host) {
      el.outerRadiusM = host.outerRadiusM;
      el.dims.od = "derived";
    }
  }

  const unlocated = elements.filter((e) => e.zone === "unlocated");
  const tray =
    unlocated.length > 0
      ? {
          center: [-TRAY_WEST_M, 0, -trayCursor / 2] as Vec3,
          halfX: Math.max(6, ...unlocated.map((e) => e.outerRadiusM * options.surfaceScale + 3)),
          halfZ: trayCursor / 2 + 1,
        }
      : null;
  if (!path.available) notes.push(`Trajectory unavailable: components are drawn along a vertical placeholder line (MD treated as depth), not a surveyed path.`);
  if (spec.components?.length === 0) notes.push("The spec has no components.");
  return {
    path,
    elements,
    downhole: elements.filter((e) => e.zone === "downhole"),
    surface: elements.filter((e) => e.zone === "surface"),
    unlocated,
    tray,
    byId: new Map(elements.map((e) => [e.id, e])),
    notes,
  };
}

/** Largest MD interval end of any located component, in metres (placeholder-line length when no survey). */
export function locatedMdMax(spec: VisualAssetSpec): number {
  let max = 0;
  for (const c of spec.components ?? []) {
    if (c.placement.state === "located") max = Math.max(max, lengthToMetres(c.placement.md_bottom, c.placement.unit));
  }
  return max;
}

export const KIND_LABEL: Record<ComponentKind, string> = {
  casing: "Casing",
  liner: "Liner",
  tubing: "Tubing",
  packer: "Packer",
  pump_esp: "ESP pump",
  bearing: "Bearing",
  plug: "Plug",
  nipple: "Nipple",
  valve: "Valve",
  mandrel: "Mandrel",
  perforation_interval: "Perforation interval",
  wellhead: "Wellhead",
  christmas_tree: "Christmas tree",
  generic_block: "Generic block",
  separator: "Separator",
  choke: "Choke",
  manifold: "Manifold",
  tank: "Tank",
  flowline: "Flowline",
  pump_surface: "Surface pump",
};

export const REPRESENTATION_LABEL: Record<Representation, string> = {
  source_dimensioned: "Source dimensioned",
  catalog_reference: "Catalog reference",
  generic_illustrative: "Generic illustrative",
};

/** One-line placement text for the list and inspector. */
export function placementText(el: SceneElement): string {
  const p = el.placement;
  if (p.state === "located" && p.md && el.zone !== "unlocated") {
    return `MD ${p.md.top}-${p.md.bottom} ${p.md.unit} (${p.md.reference})`;
  }
  if (p.state === "surface") {
    return p.offset && p.offset.fromSpec ? `Surface, offset ${p.offset.east} m E / ${p.offset.north} m N of the wellhead` : "Surface, near the wellhead (layout chosen by the viewer)";
  }
  return `Unlocated${p.reason ? `: ${p.reason}` : ""}`;
}

/**
 * Default radius exaggeration for a hole of this length (labelled in the UI). Deep wells need
 * little exaggeration because the hole is long; short ones need more to be seen at all.
 */
export function defaultExaggeration(mdMaxM: number): number {
  if (mdMaxM >= 2500) return 5;
  if (mdMaxM >= 1500) return 10;
  return 20;
}
