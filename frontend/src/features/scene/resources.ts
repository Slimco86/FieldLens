import * as THREE from "three";
import { scenePalette, type MaterialRole } from "../../design/scenePalette";

interface MatSpec {
  color: string;
  metalness: number;
  roughness: number;
}

/**
 * Material roles with physically distinct finishes (TASK-092): bare metals are metallic but never mirror-like,
 * paints are satin dielectrics, rubber and cement are matte. Colours come from `scenePalette` only.
 */
const SPEC: Record<MaterialRole, MatSpec> = {
  steel: { color: scenePalette.steel, metalness: 0.8, roughness: 0.45 },
  steelDark: { color: scenePalette.steelDark, metalness: 0.75, roughness: 0.55 },
  steelBright: { color: scenePalette.steelBright, metalness: 0.9, roughness: 0.34 },
  casing: { color: scenePalette.casing, metalness: 0.8, roughness: 0.5 },
  rubber: { color: scenePalette.rubber, metalness: 0, roughness: 0.95 },
  brass: { color: scenePalette.brass, metalness: 0.85, roughness: 0.38 },
  paintBlue: { color: scenePalette.paintBlue, metalness: 0, roughness: 0.55 },
  paintRed: { color: scenePalette.paintRed, metalness: 0, roughness: 0.55 },
  paintYellow: { color: scenePalette.paintYellow, metalness: 0, roughness: 0.58 },
  paintGreen: { color: scenePalette.paintGreen, metalness: 0, roughness: 0.55 },
  paintCream: { color: scenePalette.paintCream, metalness: 0, roughness: 0.6 },
  paintOrange: { color: scenePalette.paintOrange, metalness: 0, roughness: 0.55 },
  paintGrey: { color: scenePalette.paintGrey, metalness: 0.05, roughness: 0.6 },
  perforation: { color: scenePalette.perforation, metalness: 0.05, roughness: 0.4 },
  concrete: { color: scenePalette.concrete, metalness: 0, roughness: 0.95 },
  cement: { color: scenePalette.cement, metalness: 0, roughness: 0.92 },
  openHole: { color: scenePalette.openHole, metalness: 0, roughness: 0.9 },
  genericGrey: { color: scenePalette.genericGrey, metalness: 0.1, roughness: 0.7 },
};

/** Every role, for tests and legends. */
export const MATERIAL_ROLES = Object.keys(SPEC) as MaterialRole[];

/** Base finish of a role (before the generic/illustrative adjustment). */
export const materialSpec = (role: MaterialRole): Readonly<MatSpec> => SPEC[role];

/** Share of the highlight colour mixed into the object's own colour when selected. */
export const HIGHLIGHT_BLEND = 0.35;
/** Emissive uses the object's own hue at this low intensity, so the selected object is lifted but stays readable. */
export const HIGHLIGHT_EMISSIVE = 0.28;
/** Share of the dim colour mixed into non-selected context when dimming is on. */
export const DIM_BLEND = 0.35;

/** Cool-tint blend used for roles whose own hue is close to the amber accent (an amber tint would barely change them). */
export const HIGHLIGHT_BLEND_COOL = 0.5;

const _hsl = { h: 0, s: 0, l: 0 };

/** True when the base is a saturated warm colour near the highlight hue, where an amber tint is nearly invisible. */
export function nearHighlightHue(base: THREE.Color): boolean {
  const hl = new THREE.Color(scenePalette.highlight).getHSL({ h: 0, s: 0, l: 0 });
  base.getHSL(_hsl);
  const d = Math.abs(_hsl.h - hl.h);
  return Math.min(d, 1 - d) < 0.1 && _hsl.s > 0.3;
}

/**
 * Selected colour: the base lerped toward the highlight accent (or toward the cool tint when the base is
 * already close to amber). Pure; the input is not modified.
 */
export function blendedHighlightColor(base: THREE.Color, amount?: number): THREE.Color {
  const warm = nearHighlightHue(base);
  const target = new THREE.Color(warm ? scenePalette.highlightCool : scenePalette.highlight);
  return base.clone().lerp(target, amount ?? (warm ? HIGHLIGHT_BLEND_COOL : HIGHLIGHT_BLEND));
}

export type GeoKey = "cyl" | "cylLow" | "box" | "sphere" | "cone" | "dome" | "disc";

/**
 * Owner of every shared GPU resource of one viewer: a handful of unit geometries (scaled per mesh)
 * and a material per role/variant. Per-element geometries (tubes) are tracked and disposed with it.
 * Dispose only frees GPU memory; three re-uploads on the next render, so a StrictMode remount is safe.
 */
export class SceneResources {
  private readonly materials = new Map<string, THREE.Material>();
  private readonly geometries = new Map<string, THREE.BufferGeometry>();
  private readonly owned = new Set<THREE.BufferGeometry>();
  private readonly extra = new Set<{ dispose(): void }>();
  private readonly torusCache = new Map<number, THREE.BufferGeometry>();

  geo(key: GeoKey): THREE.BufferGeometry {
    let g = this.geometries.get(key);
    if (g === undefined) {
      switch (key) {
        case "cyl":
          g = new THREE.CylinderGeometry(1, 1, 1, 40, 1);
          break;
        case "cylLow":
          g = new THREE.CylinderGeometry(1, 1, 1, 14, 1);
          break;
        case "box":
          g = new THREE.BoxGeometry(1, 1, 1);
          break;
        case "sphere":
          g = new THREE.SphereGeometry(1, 28, 18);
          break;
        case "cone":
          g = new THREE.CylinderGeometry(0, 1, 1, 24, 1);
          break;
        case "dome":
          g = new THREE.SphereGeometry(1, 32, 12, 0, Math.PI * 2, 0, Math.PI / 2);
          break;
        case "disc":
          g = new THREE.CircleGeometry(1, 64);
          break;
      }
      this.geometries.set(key, g);
    }
    return g;
  }

  /** Torus with unit major radius; `tube` is the tube radius relative to it. */
  torus(tube: number): THREE.BufferGeometry {
    const k = Math.round(tube * 1000);
    let g = this.torusCache.get(k);
    if (g === undefined) {
      g = new THREE.TorusGeometry(1, tube, 10, 40);
      this.torusCache.set(k, g);
    }
    return g;
  }

  /**
   * Material for a role; `generic` desaturates it toward neutral grey so illustrative shapes read as generic.
   * `highlighted` blends the colour toward the highlight accent (plus a faint emissive in the object's own hue);
   * `dimmed` darkens it toward the fog tint for unselected context. All variants are cached and disposed with the library.
   */
  mat(role: MaterialRole, generic = false, highlighted = false, dimmed = false): THREE.MeshStandardMaterial {
    const key = `${role}|${generic ? 1 : 0}|${highlighted ? 1 : 0}|${dimmed && !highlighted ? 1 : 0}`;
    let m = this.materials.get(key) as THREE.MeshStandardMaterial | undefined;
    if (m === undefined) {
      const s = SPEC[role];
      const color = new THREE.Color(s.color);
      if (generic && role !== "perforation") color.lerp(new THREE.Color(scenePalette.genericMix), 0.62);
      const own = color.clone();
      if (highlighted) color.copy(blendedHighlightColor(own));
      else if (dimmed) color.lerp(new THREE.Color(scenePalette.fog), DIM_BLEND);
      m = new THREE.MeshStandardMaterial({
        color,
        metalness: generic ? s.metalness * 0.5 : s.metalness,
        roughness: generic ? Math.max(s.roughness, 0.6) : s.roughness,
        side: THREE.DoubleSide,
        emissive: highlighted ? own : new THREE.Color(0x000000),
        emissiveIntensity: highlighted ? HIGHLIGHT_EMISSIVE : 0,
      });
      this.materials.set(key, m);
    }
    return m;
  }

  /** Line material used for outlines of generic shapes. */
  lineMat(): THREE.LineBasicMaterial {
    let m = this.materials.get("line") as THREE.LineBasicMaterial | undefined;
    if (m === undefined) {
      m = new THREE.LineBasicMaterial({ color: new THREE.Color(scenePalette.steelBright), transparent: true, opacity: 0.8 });
      this.materials.set("line", m);
    }
    return m;
  }

  /** Take ownership of any disposable (a material or texture made outside the library). */
  own<T extends { dispose(): void }>(d: T): T {
    this.extra.add(d);
    return d;
  }

  track<T extends THREE.BufferGeometry>(g: T): T {
    this.owned.add(g);
    return g;
  }

  /** Dispose the per-element geometries (tubes); shared unit geometries and materials stay. */
  releaseOwned(): void {
    for (const g of this.owned) g.dispose();
    this.owned.clear();
  }

  /** Number of GPU resources currently owned (for leak checks in tests/profiling). */
  counts(): { geometries: number; materials: number } {
    return { geometries: this.geometries.size + this.torusCache.size + this.owned.size, materials: this.materials.size };
  }

  dispose(): void {
    for (const m of this.materials.values()) m.dispose();
    for (const g of this.geometries.values()) g.dispose();
    for (const g of this.torusCache.values()) g.dispose();
    for (const g of this.owned) g.dispose();
    for (const d of this.extra) d.dispose();
    this.extra.clear();
    this.materials.clear();
    this.geometries.clear();
    this.torusCache.clear();
    this.owned.clear();
  }
}

/** Swap a group's role-tagged materials between normal and highlighted variants (cached; no allocation after first use). */
export function setHighlighted(group: THREE.Object3D, lib: SceneResources, on: boolean): void {
  group.traverse((o) => {
    const key = o.userData["matKey"] as string | undefined;
    if (key === undefined) return;
    const mesh = o as THREE.Mesh;
    const [role, generic] = key.split("|") as [MaterialRole, string];
    mesh.material = lib.mat(role, generic === "1", on);
  });
}

/**
 * Optionally dim unselected context (darkened colour, no transparency, so no sorting cost). Call once per
 * selection change, never per frame; apply `setHighlighted` to the selected group afterwards.
 */
export function setDimmed(group: THREE.Object3D, lib: SceneResources, on: boolean): void {
  group.traverse((o) => {
    const key = o.userData["matKey"] as string | undefined;
    if (key === undefined) return;
    const mesh = o as THREE.Mesh;
    const [role, generic] = key.split("|") as [MaterialRole, string];
    mesh.material = lib.mat(role, generic === "1", false, on);
  });
}
