import * as THREE from "three";
import { scenePalette, type MaterialRole } from "../../design/scenePalette";

interface MatSpec {
  color: string;
  metalness: number;
  roughness: number;
}

const SPEC: Record<MaterialRole, MatSpec> = {
  steel: { color: scenePalette.steel, metalness: 0.85, roughness: 0.35 },
  steelDark: { color: scenePalette.steelDark, metalness: 0.8, roughness: 0.45 },
  steelBright: { color: scenePalette.steelBright, metalness: 0.9, roughness: 0.25 },
  casing: { color: scenePalette.casing, metalness: 0.75, roughness: 0.42 },
  rubber: { color: scenePalette.rubber, metalness: 0.05, roughness: 0.92 },
  brass: { color: scenePalette.brass, metalness: 0.9, roughness: 0.3 },
  paintBlue: { color: scenePalette.paintBlue, metalness: 0.25, roughness: 0.45 },
  paintRed: { color: scenePalette.paintRed, metalness: 0.25, roughness: 0.45 },
  paintYellow: { color: scenePalette.paintYellow, metalness: 0.2, roughness: 0.5 },
  paintGreen: { color: scenePalette.paintGreen, metalness: 0.25, roughness: 0.45 },
  paintCream: { color: scenePalette.paintCream, metalness: 0.15, roughness: 0.55 },
  paintOrange: { color: scenePalette.paintOrange, metalness: 0.25, roughness: 0.45 },
  paintGrey: { color: scenePalette.paintGrey, metalness: 0.3, roughness: 0.5 },
  perforation: { color: scenePalette.perforation, metalness: 0.1, roughness: 0.5 },
  concrete: { color: scenePalette.concrete, metalness: 0, roughness: 0.95 },
  genericGrey: { color: scenePalette.genericGrey, metalness: 0.1, roughness: 0.7 },
};

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

  /** Material for a role; `generic` desaturates it toward neutral grey so illustrative shapes read as generic. */
  mat(role: MaterialRole, generic = false, highlighted = false): THREE.MeshStandardMaterial {
    const key = `${role}|${generic ? 1 : 0}|${highlighted ? 1 : 0}`;
    let m = this.materials.get(key) as THREE.MeshStandardMaterial | undefined;
    if (m === undefined) {
      const s = SPEC[role];
      const color = new THREE.Color(s.color);
      if (generic && role !== "perforation") color.lerp(new THREE.Color(scenePalette.genericMix), 0.62);
      m = new THREE.MeshStandardMaterial({
        color,
        metalness: generic ? s.metalness * 0.5 : s.metalness,
        roughness: generic ? Math.max(s.roughness, 0.6) : s.roughness,
        side: THREE.DoubleSide,
        emissive: highlighted ? new THREE.Color(scenePalette.highlight) : new THREE.Color(0x000000),
        emissiveIntensity: highlighted ? 0.55 : 0,
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

/** Swap a group's role-tagged materials between normal and highlighted variants. */
export function setHighlighted(group: THREE.Object3D, lib: SceneResources, on: boolean): void {
  group.traverse((o) => {
    const key = o.userData["matKey"] as string | undefined;
    if (key === undefined) return;
    const mesh = o as THREE.Mesh;
    const [role, generic] = key.split("|") as [MaterialRole, string];
    mesh.material = lib.mat(role, generic === "1", on);
  });
}
