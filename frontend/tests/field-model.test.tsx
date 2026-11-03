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
  type FieldSpecState,
  type FieldWellInput,
  type Lod,
} from "../src/features/scene/fieldModel";
import type { VisualAssetSpec } from "../src/features/scene/sceneModel";

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
  it("0 specs: empty summary, every wellbore is a placeholder entry", () => {
    const plan = buildFieldPlan(wells(3, () => ({ kind: "missing" })));
    const s = summarize(plan);
    expect(s).toMatchObject({ total: 3, withSpec: 0, missing: 3, empty: true });
    expect(plan.wells.every((w) => w.model === null && w.markers.length === 0)).toBe(true);
    expect(instanceCounts(plan, null)).toMatchObject({ glyphs: 0, placeholders: 3, markers: 0, tubeMeshes: 0, pads: 3 });
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

  it("mixed: wells without a spec stay listed as labelled placeholders and failed ones carry the message", () => {
    const plan = buildFieldPlan(
      wells(4, (i) => (i === 0 ? ready("f14-dimensioned.json") : i === 1 ? { kind: "missing" } : i === 2 ? { kind: "error", message: "boom" } : ready("f5-generic.json"))),
    );
    expect(plan.wells.map((w) => w.status)).toEqual(["spec", "missing", "error", "spec"]);
    expect(plan.wells[2]!.message).toBe("boom");
    expect(summarize(plan)).toMatchObject({ withSpec: 2, missing: 1, failed: 1, empty: false });
    expect(plan.wells[1]!.name).toBe("Well 1");
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

  it("placeholders are instanced separately and a focused placeholder stays a placeholder", () => {
    const plan = buildFieldPlan(wells(3, (i) => (i === 2 ? { kind: "missing" } : ready("f14-dimensioned.json"))));
    const c = instanceCounts(plan, "w2");
    expect(c).toMatchObject({ glyphs: 2, placeholders: 1, tubeMeshes: 1 });
  });
});

describe("linked selection", () => {
  it("first activation selects and flies, activating the selected wellbore opens it", () => {
    expect(activate(null, "w1")).toEqual({ selectedId: "w1", open: false });
    expect(activate("w0", "w1")).toEqual({ selectedId: "w1", open: false });
    expect(activate("w1", "w1")).toEqual({ selectedId: "w1", open: true });
  });
});
