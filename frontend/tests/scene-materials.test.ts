import { readFileSync } from "node:fs";
import { join } from "node:path";
import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { scenePalette, type MaterialRole } from "../src/design/scenePalette";
import { buildElement } from "../src/features/scene/primitives";
import { MATERIAL_ROLES, SceneResources, blendedHighlightColor, materialSpec, nearHighlightHue, setDimmed, setHighlighted } from "../src/features/scene/resources";
import { buildSceneModel, locatedMdMax, type VisualAssetSpec } from "../src/features/scene/sceneModel";
import { WellPath } from "../src/features/scene/trajectory";

const dir = join(import.meta.dirname, "fixtures", "asset-specs");
const load = (f: string) => JSON.parse(readFileSync(join(dir, f), "utf8")) as VisualAssetSpec;

/** Triangles and draw calls (one per mesh / instanced mesh / line object) below a root. */
function renderCost(root: THREE.Object3D): { triangles: number; drawCalls: number } {
  let triangles = 0;
  let drawCalls = 0;
  root.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      const g = o.geometry as THREE.BufferGeometry;
      const per = (g.index?.count ?? g.attributes["position"]!.count) / 3;
      triangles += per * (o instanceof THREE.InstancedMesh ? o.count : 1);
      drawCalls += 1;
    } else if (o instanceof THREE.LineSegments) drawCalls += 1;
  });
  return { triangles, drawCalls };
}

function sceneOf(file: string) {
  const spec = load(file);
  const path = WellPath.unavailable(Math.max(locatedMdMax(spec), 100), "test");
  const m = buildSceneModel(spec, path, { surfaceScale: 1 });
  const lib = new SceneResources();
  const ctx = { lib, path, exaggeration: 4, surfaceScale: 1, cutaway: false };
  const group = new THREE.Group();
  for (const el of m.elements) group.add(buildElement(el, ctx));
  return { m, lib, group, ctx };
}

/** Apparent albedo under the emissive term: colour plus emissive * intensity, clamped. */
const effective = (m: THREE.MeshStandardMaterial): THREE.Color => {
  const c = m.color.clone();
  c.r = Math.min(1, c.r + m.emissive.r * m.emissiveIntensity);
  c.g = Math.min(1, c.g + m.emissive.g * m.emissiveIntensity);
  c.b = Math.min(1, c.b + m.emissive.b * m.emissiveIntensity);
  return c;
};
/** Euclidean distance in linear RGB (the working space of THREE.Color). */
const linDist = (a: THREE.Color, b: THREE.Color): number => Math.hypot(a.r - b.r, a.g - b.g, a.b - b.b);
const lum = (c: THREE.Color): number => 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
const ratio = (a: THREE.Color, b: THREE.Color): number => {
  const [x, y] = [lum(a), lum(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};
/** CIE76 colour difference between two sRGB colours. */
function deltaE(a: THREE.Color, b: THREE.Color): number {
  const lab = (c: THREE.Color): [number, number, number] => {
    const l = c; // THREE.Color holds linear-sRGB working values
    const X = (0.4124 * l.r + 0.3576 * l.g + 0.1805 * l.b) / 0.95047;
    const Y = 0.2126 * l.r + 0.7152 * l.g + 0.0722 * l.b;
    const Z = (0.0193 * l.r + 0.1192 * l.g + 0.9505 * l.b) / 1.08883;
    const f = (t: number) => (t > 216 / 24389 ? Math.cbrt(t) : (24389 / 27 * t + 16) / 116);
    return [116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))];
  };
  const [p, q] = [lab(a), lab(b)];
  return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
}

describe("material roles (G-1)", () => {
  it("every role has a spec and nothing is uniformly glossy", () => {
    const glossy = MATERIAL_ROLES.filter((r) => materialSpec(r).metalness >= 0.7 && materialSpec(r).roughness <= 0.3);
    expect(glossy).toEqual([]);
    const roughnesses = new Set(MATERIAL_ROLES.map((r) => materialSpec(r).roughness));
    expect(roughnesses.size).toBeGreaterThanOrEqual(6);
  });

  it("cement is matte, casing brushed steel, tubing lighter metal, paint and rubber non-metal", () => {
    expect(materialSpec("cement").roughness).toBeGreaterThanOrEqual(0.85);
    expect(materialSpec("cement").metalness).toBeLessThanOrEqual(0.05);
    expect(materialSpec("casing").metalness).toBeGreaterThanOrEqual(0.75);
    expect(materialSpec("casing").roughness).toBeGreaterThanOrEqual(0.45);
    expect(materialSpec("casing").roughness).toBeLessThanOrEqual(0.55);
    expect(materialSpec("steelBright").metalness).toBeGreaterThanOrEqual(0.85);
    expect(lum(new THREE.Color(scenePalette.steelBright))).toBeGreaterThan(lum(new THREE.Color(scenePalette.casing)) + 0.2);
    for (const r of ["paintBlue", "paintRed", "paintYellow", "paintGreen", "paintCream", "paintOrange", "paintGrey"] as MaterialRole[]) {
      expect(materialSpec(r).metalness).toBeLessThanOrEqual(0.1);
      expect(materialSpec(r).roughness).toBeGreaterThanOrEqual(0.5);
    }
    expect(materialSpec("rubber").metalness).toBeLessThanOrEqual(0.05);
    expect(materialSpec("rubber").roughness).toBeGreaterThanOrEqual(0.9);
    expect(materialSpec("perforation").roughness).toBeLessThanOrEqual(0.5);
  });

  it("casing, tubing, cement, packer rubber, hole and perforation colours are separated", () => {
    const keys: MaterialRole[] = ["casing", "steelBright", "cement", "rubber", "openHole", "perforation", "steelDark"];
    for (let i = 0; i < keys.length; i += 1) {
      for (let j = i + 1; j < keys.length; j += 1) {
        const d = deltaE(new THREE.Color(scenePalette[keys[i]!]), new THREE.Color(scenePalette[keys[j]!]));
        expect(d, `${keys[i]} vs ${keys[j]}`).toBeGreaterThan(12);
      }
    }
  });

  it("every role stays visible against the darkest backdrop", () => {
    const bg = new THREE.Color(scenePalette.backdropTop);
    for (const r of MATERIAL_ROLES) {
      if (r === "rubber" || r === "openHole") continue; // dark by nature, outlined by lit neighbours
      expect(ratio(new THREE.Color(scenePalette[r]), bg), r).toBeGreaterThan(1.8);
    }
    expect(deltaE(new THREE.Color(scenePalette.rubber), bg)).toBeGreaterThan(8);
  });

  it("steelDark parts keep >= 3:1 contrast against the fog tint", () => {
    expect(ratio(new THREE.Color(scenePalette.steelDark), new THREE.Color(scenePalette.fog))).toBeGreaterThanOrEqual(3);
  });

  it("generic variants stay matte-ish and keep the labelled illustrative distinction", () => {
    const lib = new SceneResources();
    const real = lib.mat("steel", false);
    const gen = lib.mat("steel", true);
    expect(gen).not.toBe(real);
    expect(gen.roughness).toBeGreaterThanOrEqual(0.6);
    expect(gen.metalness).toBeLessThan(real.metalness);
    expect(deltaE(gen.color, real.color)).toBeGreaterThan(5);
    lib.dispose();
  });
});

describe("blended highlight (G-2)", () => {
  it("lerps the base colour toward the highlight by 30-40 %", () => {
    const base = new THREE.Color(scenePalette.paintBlue);
    const hl = new THREE.Color(scenePalette.highlight);
    const out = blendedHighlightColor(base);
    const expected = base.clone().lerp(hl, 0.35);
    expect(out.r).toBeCloseTo(expected.r, 6);
    expect(out.g).toBeCloseTo(expected.g, 6);
    expect(out.b).toBeCloseTo(expected.b, 6);
    expect(base.getHex()).toBe(new THREE.Color(scenePalette.paintBlue).getHex()); // input untouched
  });

  it("warm roles near the amber accent get the cool tint, others the amber one", () => {
    const warm = new THREE.Color(scenePalette.perforation);
    expect(nearHighlightHue(warm)).toBe(true);
    expect(nearHighlightHue(new THREE.Color(scenePalette.paintBlue))).toBe(false);
    const hl = new THREE.Color(scenePalette.highlightCool);
    expect(linDist(blendedHighlightColor(warm), hl)).toBeLessThan(linDist(warm, hl));
  });

  it("keeps the base readable (never beyond the accent) yet clearly different", () => {
    const lib = new SceneResources();
    for (const r of MATERIAL_ROLES) {
      for (const generic of [false, true]) {
        const base = lib.mat(r, generic, false);
        const sel = lib.mat(r, generic, true);
        const dSel = linDist(effective(base), effective(sel));
        expect(dSel, `${r}/${generic} visible`).toBeGreaterThanOrEqual(0.25);
        expect(dSel, `${r}/${generic} stays a tint, not a replacement`).toBeLessThan(1.2);
        expect(sel.emissiveIntensity).toBeLessThanOrEqual(0.3);
        expect(sel.emissive.getHex()).not.toBe(new THREE.Color(scenePalette.highlight).getHex());
        expect(base.emissiveIntensity).toBe(0);
      }
    }
    lib.dispose();
  });

  it("setHighlighted swaps and restores role materials; setDimmed likewise, without leaking", () => {
    const { group, lib } = sceneOf("f14-dimensioned.json");
    const before: THREE.Material[] = [];
    group.traverse((o) => {
      if (o.userData["matKey"] !== undefined) before.push((o as THREE.Mesh).material as THREE.Material);
    });
    expect(before.length).toBeGreaterThan(0);
    const target = group.children[0]!;
    setHighlighted(target, lib, true);
    const counts = lib.counts();
    setHighlighted(target, lib, false);
    setHighlighted(target, lib, true);
    setHighlighted(target, lib, false);
    expect(lib.counts()).toEqual(counts); // cache reused, no new allocations
    setDimmed(group, lib, true);
    setDimmed(group, lib, false);
    const after: THREE.Material[] = [];
    group.traverse((o) => {
      if (o.userData["matKey"] !== undefined) after.push((o as THREE.Mesh).material as THREE.Material);
    });
    expect(after).toEqual(before);
    lib.dispose();
  });

  it("dimmed context is darker than normal but not transparent", () => {
    const lib = new SceneResources();
    const n = lib.mat("steel", false);
    const d = lib.mat("steel", false, false, true);
    expect(lum(d.color)).toBeLessThan(lum(n.color));
    expect(d.transparent).toBe(false);
    lib.dispose();
  });
});

describe("resources (no leaks)", () => {
  it("dispose releases every owned material and geometry", () => {
    const { group, lib } = sceneOf("f14-dimensioned.json");
    const mats = new Set<THREE.Material>();
    const geos = new Set<THREE.BufferGeometry>();
    group.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        mats.add(o.material as THREE.Material);
        geos.add(o.geometry as THREE.BufferGeometry);
      }
    });
    let disposed = 0;
    for (const m of mats) m.addEventListener("dispose", () => (disposed += 1));
    for (const g of geos) g.addEventListener("dispose", () => (disposed += 1));
    lib.dispose();
    expect(disposed).toBe(mats.size + geos.size);
    expect(lib.counts()).toEqual({ geometries: 0, materials: 0 });
  });
});

describe("wellhead (G-3, G-4)", () => {
  const roles = (g: THREE.Object3D): Set<string> => {
    const s = new Set<string>();
    g.traverse((o) => {
      const k = o.userData["matKey"] as string | undefined;
      if (k !== undefined) s.add(k.split("|")[0]!);
    });
    return s;
  };

  it("uses several distinct colours, both red and blue valves, and instanced bolts", () => {
    const { m, group, lib } = sceneOf("f14-dimensioned.json");
    const wh = m.elements.find((e) => e.kind === "wellhead");
    if (wh === undefined) throw new Error("fixture has no wellhead");
    const g = group.children[m.elements.indexOf(wh)]!;
    const r = roles(g);
    for (const need of ["paintRed", "paintBlue", "steelDark", "steelBright", "paintCream"]) expect(r.has(need), need).toBe(true);
    const colours = new Set([...r].map((x) => new THREE.Color(scenePalette[x as MaterialRole]).getHex()));
    expect(colours.size).toBeGreaterThanOrEqual(6);
    let instanced = 0;
    g.traverse((o) => {
      if (o instanceof THREE.InstancedMesh) instanced += 1;
    });
    expect(instanced).toBeGreaterThanOrEqual(2);
    lib.dispose();
  });

  it("wellhead cost is bounded and the fixture scene grows <= 20 % over the recorded baseline", () => {
    // Baselines measured on base d0294a0 (master 0.47.0) with this same helper and fixtures.
    const baseline: Record<string, { triangles: number; drawCalls: number }> = {
      "f14-dimensioned.json": { triangles: BASE_F14.triangles, drawCalls: BASE_F14.drawCalls },
    };
    const { m, group, lib } = sceneOf("f14-dimensioned.json");
    const c = renderCost(group);
    const whIdx = m.elements.findIndex((e) => e.kind === "wellhead");
    const whCost = renderCost(group.children[whIdx]!);
    expect(whCost.triangles).toBeLessThanOrEqual(5320 * 1.6);
    process.stderr.write(`\nSCENECOST ${JSON.stringify(c)} wellhead ${JSON.stringify(whCost)}\n`);
    expect(c.triangles).toBeLessThanOrEqual(baseline["f14-dimensioned.json"]!.triangles * 1.2);
    expect(c.drawCalls).toBeLessThanOrEqual(baseline["f14-dimensioned.json"]!.drawCalls * 1.2);
    lib.dispose();
  });
});

// Measured on base d0294a0: sum over the f14 fixture elements (wellhead alone: 5320 triangles / 23 draw calls).
const BASE_F14 = { triangles: 97920, drawCalls: 201 };
