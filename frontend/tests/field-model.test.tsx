import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  activate,
  buildFieldPlan,
  gridDimensions,
  gridLayout,
  instanceCounts,
  lodFor,
  summarize,
  tubeRadiusFor,
  type FieldSpecState,
  type FieldWellInput,
  type Lod,
  type SurfaceLocation,
} from "../src/features/scene/fieldModel";
import { defaultExaggeration, type VisualAssetSpec } from "../src/features/scene/sceneModel";

const dir = join(import.meta.dirname, "fixtures", "asset-specs");
const load = (f: string) => JSON.parse(readFileSync(join(dir, f), "utf8")) as VisualAssetSpec;
const FILES = ["f14-dimensioned.json", "f12-unlocated.json", "f5-generic.json"];

const ready = (file: string): FieldSpecState => ({ kind: "ready", spec: load(file), revision: 1 });
const wells = (n: number, state: (i: number) => FieldSpecState = (i) => ready(FILES[i % 3]!)): FieldWellInput[] =>
  Array.from({ length: n }, (_, i) => ({ id: `w${i}`, name: `Well ${i}`, spec: state(i) }));

describe("schematic layout", () => {
  it("never invents positions: a centred grid in listing order", () => {
    const cells = gridLayout(6, 400);
    expect(cells).toHaveLength(6);
    const { cols, rows } = gridDimensions(6);
    expect(cols * rows).toBeGreaterThanOrEqual(6);
    const xs = cells.map((c) => c.position[0]);
    const zs = cells.map((c) => c.position[2]);
    expect(Math.min(...xs)).toBeCloseTo(-Math.max(...xs), 6);
    expect(Math.min(...zs)).toBeCloseTo(-Math.max(...zs), 6);
    expect(new Set(cells.map((c) => `${c.position[0]},${c.position[2]}`)).size).toBe(6);
    expect(cells.every((c) => c.position[1] === 0)).toBe(true);
    // Row-major in listing order.
    expect(cells[0]!.row).toBe(0);
    expect(cells[0]!.col).toBe(0);
    expect(cells[1]!.col).toBe(1);
  });

  it("handles zero and one wellbore", () => {
    expect(gridDimensions(0)).toEqual({ cols: 0, rows: 0 });
    expect(gridLayout(0, 400)).toEqual([]);
    expect(gridLayout(1, 400)[0]!.position).toEqual([0, 0, 0]);
  });

  it("the plan labels the layout as schematic and spaces wells beyond the pad size", () => {
    const plan = buildFieldPlan(wells(5));
    expect(plan.layoutLabel).toMatch(/schematic layout, not map positions/i);
    for (const w of plan.wells) {
      expect(plan.byId.get(w.id)).toBe(w);
    }
    const a = plan.wells[0]!.position;
    const b = plan.wells[1]!.position;
    expect(Math.hypot(a[0] - b[0], a[2] - b[2])).toBeGreaterThanOrEqual(plan.spacingM - 1e-6);
    expect(plan.display.padHalfM * 2).toBeLessThan(plan.spacingM);
  });
});

describe("states of wellbores", () => {
  it("0 specs: nothing is listed or drawn, the summary keeps the counts", () => {
    const plan = buildFieldPlan(wells(3, () => ({ kind: "missing" })));
    const s = summarize(plan);
    expect(s).toMatchObject({ total: 3, withSpec: 0, missing: 3, empty: true });
    expect(plan.wells).toEqual([]);
    expect(instanceCounts(plan, null)).toMatchObject({ glyphs: 0, placeholders: 0, markers: 0, tubeMeshes: 0, pads: 0 });
  });

  it("no wellbores at all is empty too", () => {
    const plan = buildFieldPlan([]);
    expect(plan.wells).toEqual([]);
    expect(summarize(plan).empty).toBe(true);
    expect(instanceCounts(plan, null).drawCalls).toBe(0);
  });

  it("loading wellbores are not 'empty'", () => {
    const s = summarize(buildFieldPlan(wells(2, () => ({ kind: "loading" }))));
    expect(s.loading).toBe(2);
    expect(s.empty).toBe(false);
  });

  it("mixed: only reconstructed wells are drawn (missing/loading are counted only); failed ones stay listed with the message", () => {
    const plan = buildFieldPlan(
      wells(5, (i) => (i === 0 ? ready("f14-dimensioned.json") : i === 1 ? { kind: "missing" } : i === 2 ? { kind: "error", message: "boom" } : i === 3 ? { kind: "loading" } : ready("f5-generic.json"))),
    );
    expect(plan.wells.map((w) => w.status)).toEqual(["spec", "error", "spec"]);
    expect(plan.wells[1]!.message).toBe("boom");
    expect(plan.byId.has("w1")).toBe(false);
    expect(summarize(plan)).toMatchObject({ total: 5, withSpec: 2, missing: 1, failed: 1, loading: 1, empty: false });
  });

  it("counts components and keeps illustrative ones out of the 'documented' tally", () => {
    const plan = buildFieldPlan(wells(3));
    const [f14, f12, f5] = plan.wells;
    expect(f14!.counts.components).toBe(load("f14-dimensioned.json").components!.length);
    expect(f12!.counts.unlocated).toBeGreaterThan(0);
    expect(f5!.counts.illustrative).toBe(f5!.counts.components);
    // Unlocated components never get a marker position (no invented depth).
    expect(f12!.markers.length).toBe(f12!.counts.downhole);
    expect(f12!.trajectoryAvailable).toBe(false);
  });

  it("uses an injected validated survey for the path and depth", () => {
    const plan = buildFieldPlan(wells(1), () => ({
      source: "test",
      stations: [
        { md_m: 0, tvd_m: 0 },
        { md_m: 2000, tvd_m: 1800, east_m: 500, north_m: 0 },
        { md_m: 4000, tvd_m: 3000, east_m: 900, north_m: 0 },
      ],
    }));
    expect(plan.wells[0]!.trajectoryAvailable).toBe(true);
    expect(plan.wells[0]!.depthM).toBeCloseTo(3000, 6);
  });
});

describe("level of detail", () => {
  it("full primitives only for the focused wellbore; others by distance", () => {
    expect(lodFor(true, 1e6, 3000)).toBe("full");
    expect(lodFor(false, 100, 3000)).toBe("markers");
    expect(lodFor(false, 20000, 3000)).toBe("glyph");
    expect(lodFor(false, 100, 0)).toBe("markers");
  });
});

describe("instancing", () => {
  it("draw calls of the far set do not grow with the number of wellbores", () => {
    const all = (n: number): Map<string, Lod> => new Map(Array.from({ length: n }, (_, i) => [`w${i}`, "markers" as Lod]));
    const small = buildFieldPlan(wells(3));
    const big = buildFieldPlan(wells(12));
    const a = instanceCounts(small, null, all(3));
    const b = instanceCounts(big, null, all(12));
    expect(a.drawCalls).toBe(b.drawCalls);
    expect(b.drawCalls).toBeLessThanOrEqual(5);
    expect(b.tubeMeshes).toBe(1);
    expect(b.glyphs).toBe(12);
    expect(b.pads).toBe(12);
    expect(b.markers).toBe(big.wells.reduce((s, w) => s + w.markers.length, 0));
  });

  it("markers appear only for wells in range and never for the focused one", () => {
    const plan = buildFieldPlan(wells(3));
    expect(instanceCounts(plan, null).markers).toBe(0);
    const lods = new Map<string, Lod>([["w0", "markers"], ["w1", "markers"]]);
    const c = instanceCounts(plan, "w0", lods);
    expect(c.glyphs).toBe(2);
    expect(c.markers).toBe(plan.wells[1]!.markers.length);
  });

  it("placeholders are only failed loads; unreconstructed wellbores are not instanced at all", () => {
    const plan = buildFieldPlan(wells(4, (i) => (i === 2 ? { kind: "missing" } : i === 3 ? { kind: "error", message: "x" } : ready("f14-dimensioned.json"))));
    const c = instanceCounts(plan, "w3");
    expect(c).toMatchObject({ glyphs: 2, placeholders: 1, tubeMeshes: 1, pads: 3 });
  });
});

const loc = (e: number, n: number, over: Partial<SurfaceLocation> = {}): SurfaceLocation => ({
  easting: e,
  northing: n,
  crs: "ED50 / UTM zone 31N",
  datum: "ED50",
  unit: "m",
  ...over,
});
const surfaces = (m: Record<string, SurfaceLocation | null>) => (id: string) => m[id] ?? null;
const noTraj = () => null;
const noReason = () => "no survey";

describe("surface-location layout", () => {
  const UTM = { w0: loc(435_000.4, 6_478_000.25), w1: loc(435_010.4, 6_478_000.25), w2: loc(435_000.4, 6_478_020.25) };

  it("same CRS/datum/unit: planar E/N offsets from the placed centroid, labelled with the CRS", () => {
    const plan = buildFieldPlan(wells(3), noTraj, noReason, surfaces(UTM));
    expect(plan.layoutKind).toBe("surface");
    expect(plan.layoutLabel).toBe("Surface-location layout (E/N offsets from the field centroid, ED50 / UTM zone 31N)");
    expect(plan.layoutNote).toBeNull();
    const [a, b, c] = plan.wells.map((w) => w.position);
    // East is +x, north is -z (render axes), relative differences are exact to metre-level at UTM magnitudes.
    expect(b![0] - a![0]).toBeCloseTo(10, 9);
    expect(a![2] - c![2]).toBeCloseTo(20, 9);
    // Centroid subtraction: positions are small numbers, the mean offset is zero.
    expect(Math.max(...plan.wells.map((w) => Math.abs(w.position[0])))).toBeLessThan(20);
    expect((a![0] + b![0] + c![0]) / 3).toBeCloseTo(0, 9);
    expect((a![2] + b![2] + c![2]) / 3).toBeCloseTo(0, 9);
    expect(plan.wells.every((w) => w.placement === "surface")).toBe(true);
    expect(plan.layoutFrame).toEqual({ crs: "ED50 / UTM zone 31N", datum: "ED50", unit: "m" });
  });

  it("CRS/datum comparison ignores case and whitespace", () => {
    const plan = buildFieldPlan(wells(2), noTraj, noReason, surfaces({ w0: loc(1, 1), w1: loc(5, 1, { crs: " ed50 /  utm zone 31n", datum: "ed50" }) }));
    expect(plan.layoutKind).toBe("surface");
  });

  it.each([
    ["different CRS", { w1: loc(5, 1, { crs: "WGS 84 / UTM zone 31N" }) }, /different CRSs/],
    ["different datum", { w1: loc(5, 1, { datum: "WGS84" }) }, /different datums/],
    ["unstated datum vs stated", { w1: loc(5, 1, { datum: null }) }, /different datums/],
    ["unstated CRS", { w1: loc(5, 1, { crs: null }) }, /does not state its CRS/],
    ["unstated unit", { w1: loc(5, 1, { unit: null }) }, /does not state its unit/],
    ["feet (no conversion)", { w0: loc(1, 1, { unit: "ft" }), w1: loc(5, 1, { unit: "ft" }) }, /not metres/],
  ])("%s: schematic grid with the schematic label and the reason", (_n, over, reason) => {
    const plan = buildFieldPlan(wells(2), noTraj, noReason, surfaces({ w0: loc(1, 1), ...over }));
    expect(plan.layoutKind).toBe("schematic");
    expect(plan.layoutLabel).toBe("Schematic layout, not map positions");
    expect(plan.layoutNote).toMatch(reason);
    expect(plan.wells.every((w) => w.placement === "schematic")).toBe(true);
  });

  it("no locations at all: schematic", () => {
    const plan = buildFieldPlan(wells(3));
    expect(plan.layoutKind).toBe("schematic");
    expect(plan.layoutNote).toMatch(/no wellbore states a surface location/);
  });

  it("a well without a location in an otherwise located set waits in a separated unlocated row (never a guessed position)", () => {
    const plan = buildFieldPlan(wells(4), noTraj, noReason, surfaces({ w0: loc(1000, 1000), w1: loc(1100, 1000), w3: loc(1000, 1100) }));
    expect(plan.layoutKind).toBe("surface");
    const lost = plan.byId.get("w2")!;
    expect(lost.placement).toBe("unlocated");
    // South of every located well (larger z), separated by at least the gap rule.
    const located = plan.wells.filter((w) => w.placement === "surface");
    expect(located).toHaveLength(3);
    expect(lost.position[2]).toBeGreaterThan(Math.max(...located.map((w) => w.position[2])) + 99);
    // Centroid is over the located wells only.
    expect(located.reduce((s, w) => s + w.position[0], 0) / 3).toBeCloseTo(0, 9);
  });

  it("failed spec loads are held in the unlocated row too", () => {
    const plan = buildFieldPlan(wells(3, (i) => (i === 2 ? { kind: "error", message: "x" } : ready("f14-dimensioned.json"))), noTraj, noReason, surfaces({ w0: loc(0, 0), w1: loc(50, 0) }));
    expect(plan.byId.get("w2")!.placement).toBe("unlocated");
  });

  it("platform-scale wells (metres apart) get pads/glyphs limited by the nearest neighbour, isolated wells keep the large size", () => {
    const m = { w0: loc(500_000, 6_000_000), w1: loc(500_003, 6_000_000), w2: loc(500_000, 6_000_004), w3: loc(504_000, 6_003_000) };
    const plan = buildFieldPlan(wells(4), noTraj, noReason, surfaces(m));
    const [a, b, c, far] = plan.wells;
    expect(plan.nearestM).toBeCloseTo(3, 9);
    // Neighbouring pads do not overlap: half-widths sum below the distance (0.4 each).
    expect(a!.padHalfM + b!.padHalfM).toBeLessThanOrEqual(3 + 1e-9);
    expect(a!.padHalfM + c!.padHalfM).toBeLessThanOrEqual(4 + 1e-9);
    expect(a!.glyphHeightM).toBeLessThan(far!.glyphHeightM);
    expect(far!.padHalfM).toBeCloseTo(plan.display.padHalfM, 9);
    // A minimum remains only for coincident wellheads.
    expect(a!.padHalfM).toBeGreaterThanOrEqual(0.5);
  });

  it("frames the horizontal spread and the deepest trace", () => {
    const plan = buildFieldPlan(
      wells(2),
      (id) => ({ source: "t", stations: [{ md_m: 0, tvd_m: 0 }, { md_m: 3000, tvd_m: 2500, east_m: id === "w0" ? 1500 : 0, north_m: 0 }] }),
      noReason,
      surfaces({ w0: loc(0, 0), w1: loc(100, 0) }),
    );
    expect(plan.bounds.depthM).toBeGreaterThanOrEqual(2500);
    expect(plan.bounds.maxX - plan.bounds.minX).toBeGreaterThanOrEqual(1500);
    expect(plan.framing.radiusM).toBeGreaterThan(plan.bounds.depthM * 0.5);
    expect(plan.framing.center[1]).toBeLessThan(0);
  });
});

describe("default trajectory thickness", () => {
  it("every well's tube radius is the selected-state rule, max(0.05, exaggeration*0.035), not extent-derived", () => {
    expect(tubeRadiusFor(3000)).toBeCloseTo(5 * 0.035, 9);
    expect(tubeRadiusFor(2000)).toBeCloseTo(10 * 0.035, 9);
    expect(tubeRadiusFor(500)).toBeCloseTo(20 * 0.035, 9);
    const plan = buildFieldPlan(wells(3), (id) => ({ source: "t", stations: [{ md_m: 0, tvd_m: 0 }, { md_m: id === "w0" ? 3000 : 800, tvd_m: id === "w0" ? 3000 : 800 }] }));
    for (const w of plan.wells) expect(w.tubeRadiusM).toBeCloseTo(Math.max(0.05, defaultExaggeration(w.depthM) * 0.035), 9);
    expect(plan.display.tubeRadiusM).toBeCloseTo(tubeRadiusFor(plan.bounds.depthM), 9);
  });
});

describe("linked selection", () => {
  it("first activation selects and flies, activating the selected wellbore opens it", () => {
    expect(activate(null, "w1")).toEqual({ selectedId: "w1", open: false });
    expect(activate("w0", "w1")).toEqual({ selectedId: "w1", open: false });
    expect(activate("w1", "w1")).toEqual({ selectedId: "w1", open: true });
  });
});
