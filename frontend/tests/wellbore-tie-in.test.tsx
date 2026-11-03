import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as THREE from "three";
import { ComponentList } from "../src/features/scene/ComponentList";
import { Inspector } from "../src/features/scene/Inspector";
import { buildAssets } from "../src/features/scene/Viewer3D";
import { buildSceneModel, DEFAULT_WELLHEAD_ID, locatedMdMax, type AssetComponent, type VisualAssetSpec } from "../src/features/scene/sceneModel";
import type { WellboreTrajectory } from "../src/features/scene/api";
import { toTrajectoryState } from "../src/features/scene/trajectorySource";
import { tieInInput, WellPath, type TrajectoryInput } from "../src/features/scene/trajectory";

const dir = join(import.meta.dirname, "fixtures", "asset-specs");
const load = (f: string) => JSON.parse(readFileSync(join(dir, f), "utf8")) as VisualAssetSpec;
const OPTIONS = { exaggeration: 10, surfaceScale: 1, cutaway: false, labels: "all" as const, depthMarks: false };

const FIRST_MD = 145.9;
const stations = [
  { md_m: FIRST_MD, tvd_m: FIRST_MD, east_m: 0, north_m: 0 },
  { md_m: 300, tvd_m: 299, east_m: 4, north_m: 0 },
  { md_m: 500, tvd_m: 490, east_m: 20, north_m: 0 },
];
const verticalTie = { kind: "vertical" as const, points: [{ md_m: 0, tvd_m: 0, east_m: 0, north_m: 0 }, { md_m: 70, tvd_m: 70, east_m: 0, north_m: 0 }, { md_m: FIRST_MD, tvd_m: FIRST_MD, east_m: 0, north_m: 0 }] };
// S-shaped arc: ends on the first station (east 3 m) with MD (curve length) > TVD.
const arcTie = {
  kind: "arc" as const,
  points: [
    { md_m: 0, tvd_m: 0, east_m: 0, north_m: 0 },
    { md_m: 50, tvd_m: 49.9, east_m: 0.5, north_m: 0 },
    { md_m: 100, tvd_m: 99.2, east_m: 2, north_m: 0 },
    { md_m: FIRST_MD, tvd_m: 145, east_m: 3, north_m: 0 },
  ],
};
const input = (tieIn: TrajectoryInput["tieIn"], first = stations[0]!): TrajectoryInput => ({ source: "t", stations: [first, ...stations.slice(1)], tieIn });

const comp = (id: string, kind: AssetComponent["kind"], placement: AssetComponent["placement"], extra: Partial<AssetComponent> = {}): AssetComponent =>
  ({ id, kind, label: id, representation: "generic_illustrative", placement, ...extra }) as AssetComponent;
const located = (top: number, bottom: number) => ({ state: "located", md_top: top, md_bottom: bottom, unit: "m", depth_reference: "MD" }) as AssetComponent["placement"];
const surface = { state: "surface", offset_east_m: null, offset_north_m: null } as AssetComponent["placement"];
const unlocated = { state: "unlocated", reason: "unknown" } as AssetComponent["placement"];
const specOf = (components: AssetComponent[]): VisualAssetSpec => ({ components }) as unknown as VisualAssetSpec;

describe("E-1: unlocated components are not drawn", () => {
  it("has no tray and no mesh/group for unlocated components, while the model keeps them", () => {
    const spec = load("f12-unlocated.json");
    const m = buildSceneModel(spec, WellPath.unavailable(Math.max(locatedMdMax(spec), 100), "t"));
    expect(m.unlocated.length).toBeGreaterThan(0);
    const built = buildAssets(m, OPTIONS);
    try {
      const ids = new Set(built.root.children.map((c) => c.userData["elementId"] as string | undefined));
      for (const el of m.unlocated) expect(ids.has(el.id)).toBe(false);
      expect(built.root.children.some((c) => c.name === "tray")).toBe(false);
      expect(built.anchors.some((a) => a.id === "tray")).toBe(false);
      // Nothing is parked west of the well where the tray used to be.
      expect(built.bounds.min.x).toBeGreaterThan(-30);
    } finally {
      built.lib.dispose();
    }
  });

  it("list and inspector still show and select unlocated components", () => {
    const spec = load("f12-unlocated.json");
    const m = buildSceneModel(spec, WellPath.unavailable(400, "t"));
    const onSelect = vi.fn();
    const { rerender } = render(<ComponentList model={m} selectedId={null} onSelect={onSelect} />);
    const el = m.unlocated[0]!;
    fireEvent.click(document.querySelector(`button[data-element-id="${el.id}"]`)!);
    expect(onSelect).toHaveBeenCalledWith(el.id);
    rerender(<Inspector element={el} />);
    expect(screen.getByTestId("inspector-label").textContent).toBe(el.label);
    expect(screen.getByTestId("inspector-placement").textContent).toMatch(/Unlocated/);
  });
});

describe("E-2: a wellhead is always drawn at the well hole", () => {
  const path = WellPath.unavailable(500, "t");

  it("draws a labelled default wellhead at the origin when the spec has none", () => {
    const m = buildSceneModel(specOf([comp("c1", "casing", located(0, 100))]), path);
    expect(m.defaultWellhead).not.toBeNull();
    expect(m.defaultWellhead!.label).toMatch(/default/i);
    for (const c of m.defaultWellhead!.position) expect(Math.abs(c)).toBe(0);
    expect(m.elements.map((e) => e.id)).not.toContain(DEFAULT_WELLHEAD_ID);
    const built = buildAssets(m, OPTIONS);
    try {
      expect(built.root.children.some((c) => c.userData["elementId"] === DEFAULT_WELLHEAD_ID)).toBe(true);
      expect(built.anchors.find((a) => a.id === DEFAULT_WELLHEAD_ID)?.text).toMatch(/default/i);
    } finally {
      built.lib.dispose();
    }
  });

  it("uses the spec wellhead when present and draws no default", () => {
    const m = buildSceneModel(specOf([comp("wh", "wellhead", surface)]), path);
    expect(m.defaultWellhead).toBeNull();
    const built = buildAssets(m, OPTIONS);
    try {
      expect(built.root.children.some((c) => c.userData["elementId"] === DEFAULT_WELLHEAD_ID)).toBe(false);
      expect(built.root.children.some((c) => c.userData["elementId"] === "wh")).toBe(true);
    } finally {
      built.lib.dispose();
    }
  });

  it("an unlocated spec wellhead is listed only, so the default is drawn", () => {
    const m = buildSceneModel(specOf([comp("wh", "wellhead", unlocated)]), path);
    expect(m.defaultWellhead).not.toBeNull();
    expect(m.unlocated.map((e) => e.id)).toEqual(["wh"]);
  });

  it("a tree stands on the default wellhead", () => {
    const m = buildSceneModel(specOf([comp("t", "christmas_tree", surface)]), path);
    expect(m.defaultWellhead).not.toBeNull();
    expect(m.byId.get("t")!.baseOffsetM).toBeGreaterThan(0);
  });
});

describe("E-3/E-4: tie-in", () => {
  it("vertical tie-in: the trace starts at the origin and stations are not changed", () => {
    const p = WellPath.fromTrajectory(input(verticalTie), 500);
    expect(p.tieInKind).toBe("vertical");
    expect(p.mdMin).toBe(0);
    expect(p.stationCount).toBe(3);
    const v = p.vertices();
    for (const c of v[0]!.position) expect(Math.abs(c)).toBe(0);
    expect(v[0]!.md).toBe(0);
    // Absolute depth of the first station is unchanged.
    expect(p.at(FIRST_MD).position[1]).toBeCloseTo(-FIRST_MD, 9);
    expect(p.at(300).position[1]).toBeCloseTo(-299, 9);
    // Drawn polyline: tie-in points (without the duplicate end) plus every station.
    expect(v).toHaveLength(2 + 3);
    expect(p.onTieIn(100)).toBe(true);
    expect(p.onTieIn(200)).toBe(false);
  });

  it("arc tie-in: starts at the origin, interpolates MD linearly on md_m and meets the first station", () => {
    const p = WellPath.fromTrajectory(input(arcTie, { md_m: FIRST_MD, tvd_m: 145, east_m: 3, north_m: 0 }), 500);
    expect(p.tieInKind).toBe("arc");
    for (const c of p.at(0).position) expect(Math.abs(c)).toBe(0);
    const mid = p.at(75).position; // halfway between MD 50 and 100
    expect(mid[0]).toBeCloseTo(1.25, 9);
    expect(mid[1]).toBeCloseTo(-(49.9 + 99.2) / 2, 9);
    expect(p.at(FIRST_MD).position[0]).toBeCloseTo(3, 9);
  });

  it("places components above the first station on the tie-in; absolute depth is untouched", () => {
    const spec = specOf([comp("wh", "wellhead", located(0, 2)), comp("c", "casing", located(0, 120)), comp("pk", "packer", located(60, 62)), comp("deep", "tubing", located(150, 400))]);
    const m = buildSceneModel(spec, WellPath.fromTrajectory(input(verticalTie), 500));
    expect(m.unlocated).toHaveLength(0);
    expect(m.byId.get("c")!.zone).toBe("downhole");
    expect(m.byId.get("pk")!.position[1]).toBeCloseTo(-61, 9);
    for (const c of m.byId.get("wh")!.position) expect(Math.abs(c)).toBe(0);
    expect(m.defaultWellhead).toBeNull();
    expect(m.notes.join(" ")).toMatch(/tie-in/);
    const built = buildAssets(m, OPTIONS);
    try {
      const traj = built.root.children.find((c) => c.name === "trajectory") as THREE.Mesh;
      traj.geometry.computeBoundingBox();
      // The tube reaches the well hole (origin) within its display radius.
      expect(traj.geometry.boundingBox!.max.y).toBeLessThan(1);
      expect(traj.geometry.boundingBox!.max.y).toBeGreaterThan(-1);
      expect(built.anchors.some((a) => a.id === "tie-in" && /display only/.test(a.text))).toBe(true);
    } finally {
      built.lib.dispose();
    }
  });

  it("without a tie-in the behaviour is unchanged: no invention, components above stay unplaced, note explains", () => {
    const spec = specOf([comp("pk", "packer", located(60, 62)), comp("deep", "tubing", located(150, 400))]);
    const p = WellPath.fromTrajectory(input(null), 500);
    expect(p.tieInKind).toBeNull();
    expect(p.mdMin).toBe(FIRST_MD);
    expect(p.vertices()).toHaveLength(3);
    const m = buildSceneModel(spec, p);
    expect(m.byId.get("pk")!.zone).toBe("unlocated");
    expect(m.byId.get("deep")!.zone).toBe("downhole");
    expect(m.notes.join(" ")).toMatch(/no tie-in was derived/);
  });

  it("ignores a tie-in that does not match the first station or when the survey starts at MD 0", () => {
    const bad = { ...verticalTie, points: verticalTie.points.map((q, i, a) => (i === a.length - 1 ? { ...q, tvd_m: q.tvd_m + 5 } : q)) };
    const p = WellPath.fromTrajectory(input(bad), 500);
    expect(p.tieInKind).toBeNull();
    expect(p.tieInIgnored).toMatch(/first surveyed station/);
    const atZero = WellPath.fromTrajectory({ source: "t", stations: [{ md_m: 0, tvd_m: 0 }, { md_m: 100, tvd_m: 100 }], tieIn: verticalTie }, 100);
    expect(atZero.tieInKind).toBeNull();
    expect(atZero.vertices()).toHaveLength(2);
  });

  it("tie-in points are never survey stations: counts and API mapping", () => {
    const p = WellPath.fromTrajectory(input(verticalTie), 500);
    expect(p.stationCount).toBe(stations.length);
    expect(tieInInput(null)).toBeNull();
    expect(tieInInput({ kind: "vertical", points: verticalTie.points })!.points).toHaveLength(3);
  });
});

describe("API trajectory -> WellPath", () => {
  const dto = (tie_in: unknown): WellboreTrajectory =>
    ({
      survey_set: { filename: "SSR.pdf" },
      survey_status: "as_built",
      md_reference: null,
      tvd_reference: null,
      azimuth_reference: null,
      north_reference: "grid",
      surface_location: null,
      points: stations.map((p) => ({ ...p })),
      displayed_count: 3,
      source_count: 3,
      md_min_m: FIRST_MD,
      md_max_m: 500,
      other_sets: [],
      warnings: [],
      tie_in,
    }) as unknown as WellboreTrajectory;

  it("tie_in from the API reaches the built WellPath through toTrajectoryState", () => {
    const state = toTrajectoryState(dto({ derived: true, label: "tie_in", reason_code: "TIE_IN_DERIVED", kind: "vertical", max_dls_deg_per_30m: 0, points: verticalTie.points }));
    if (state.kind !== "ready") throw new Error("expected ready");
    expect(state.input.tieIn?.kind).toBe("vertical");
    expect(state.info.counts).toContain("3 of 3 stations");
    const p = WellPath.fromTrajectory(state.input, 500);
    expect(p.tieInKind).toBe("vertical");
    expect(p.mdMin).toBe(0);
    expect(p.stationCount).toBe(3);
  });

  it("a null tie_in leaves the path starting at the first station", () => {
    const state = toTrajectoryState(dto(null));
    if (state.kind !== "ready") throw new Error("expected ready");
    const p = WellPath.fromTrajectory(state.input, 500);
    expect(p.tieInKind).toBeNull();
    expect(p.mdMin).toBe(FIRST_MD);
  });
});
