import { readFileSync } from "node:fs";
import { join } from "node:path";
import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import type { WellboreTrajectory } from "../src/features/scene/api";
import { FieldScene } from "../src/features/scene/FieldScene";
import { Inspector } from "../src/features/scene/Inspector";
import { loadTrajectory, placeholderReason, surfaceText, toTrajectoryState, inputOf } from "../src/features/scene/trajectorySource";
import { WellPath } from "../src/features/scene/trajectory";
import { render } from "./render";

const mockGet = vi.fn();
let specImpl: (id: string) => Promise<unknown> = () => Promise.reject(new ApiError(404, "NOT_FOUND", "none", null));
vi.mock("../src/features/scene/api", () => ({
  getAssetSpec: (_p: string, id: string) => specImpl(id),
  generateAssetSpec: vi.fn(),
  getTrajectory: (...a: unknown[]) => mockGet(...a),
}));

const dto = (over: Partial<WellboreTrajectory> = {}): WellboreTrajectory =>
  ({
    project_id: "p",
    wellbore_id: "w",
    method: "minimum_curvature",
    survey_set: { document_id: "d", run_id: "r", filename: "SSR.pdf", survey_status: "as_built", station_count: 3, validated: true, used: true, reasons: [] },
    survey_status: "as_built",
    md_unit: "m",
    depth_unit: "m",
    md_reference: "RKB",
    tvd_reference: null,
    azimuth_reference: "grid north",
    north_reference: "grid",
    crs: "ED50 UTM 31N",
    geodetic_datum: "ED50",
    surface_location: { easting: 456000, northing: 6780000, unit: "m", latitude: null, longitude: null, crs: "ED50 UTM 31N", geodetic_datum: "ED50", evidence: {} },
    points: [
      { md_m: 0, tvd_m: 0, east_m: 0, north_m: 0 },
      { md_m: 500, tvd_m: 480, east_m: 60, north_m: 10 },
      { md_m: 1000, tvd_m: 900, east_m: 200, north_m: 40 },
    ],
    displayed_count: 3,
    source_count: 195,
    md_min_m: 0,
    md_max_m: 1000,
    max_tvd_m: 900,
    source_tvd_max_abs_diff_m: 0.1,
    evidence: [],
    other_sets: [{ document_id: "d2", run_id: "r2", filename: "plan.pdf", survey_status: "planned", station_count: 2, validated: false, used: false, reasons: [{ code: "TRAJECTORY_PLANNED_ONLY", message: "m" }] }],
    warnings: [],
    ...over,
  }) as unknown as WellboreTrajectory;

describe("trajectory source", () => {
  it("labels the trace and the surface location with its CRS, and feeds a real WellPath", () => {
    const state = toTrajectoryState(dto());
    if (state.kind !== "ready") throw new Error("expected ready");
    expect(state.info.label).toBe("Survey: SSR.pdf, as-built, MD 0-1000 m");
    expect(state.info.surfaceText).toBe("Surface location: E 456000 m, N 6780000 m (CRS: ED50 UTM 31N, datum: ED50)");
    expect(state.info.counts).toContain("3 of 195 stations");
    expect(state.info.others[0]).toContain("only a planned survey exists");
    const path = WellPath.fromTrajectory(state.input, 1000);
    expect(path.available).toBe(true);
    expect(path.sourceLabel).toBe(state.info.label);
    expect(path.at(1000).position).toEqual([200, -900, -40]);
  });

  it("never invents a CRS or a location", () => {
    const noCrs = dto({ surface_location: { ...dto().surface_location!, crs: null, geodetic_datum: null } });
    expect(surfaceText(noCrs)).toBe("Surface location: E 456000 m, N 6780000 m (CRS not stated)");
    expect(surfaceText(dto({ surface_location: null }))).toBeNull();
  });

  it("maps 404 no_trajectory to a placeholder reason and other failures to an error", async () => {
    mockGet.mockRejectedValueOnce(new ApiError(404, "NOT_FOUND", "x", null, { code: "no_trajectory", sets: [{ reasons: ["TRAJECTORY_PLANNED_ONLY"] }] }));
    const none = await loadTrajectory("p", "w", new AbortController().signal);
    expect(none).toEqual({ kind: "none", reason: "no valid survey: only a planned survey exists" });
    expect(inputOf(none)).toBeNull();
    mockGet.mockRejectedValueOnce(new ApiError(500, "INTERNAL_ERROR", "boom", null));
    const err = await loadTrajectory("p", "w", new AbortController().signal);
    expect(err.kind).toBe("error");
    expect(placeholderReason(err)).toContain("could not be loaded");
    expect(placeholderReason(undefined)).toBe("survey is loading");
  });

  it("the single-wellbore info panel shows the survey, or the placeholder reason", () => {
    const ready = toTrajectoryState(dto());
    const { unmount } = render(<Inspector element={null} survey={ready} />);
    expect(screen.getByTestId("survey-label")).toHaveTextContent("Survey: SSR.pdf, as-built, MD 0-1000 m");
    expect(screen.getByTestId("survey-surface")).toHaveTextContent("CRS: ED50 UTM 31N");
    unmount();
    render(<Inspector element={null} survey={{ kind: "none", reason: "no valid survey: only a planned survey exists" }} />);
    expect(screen.getByTestId("survey-unavailable")).toHaveTextContent("vertical placeholder, not a survey");
  });
});

describe("field view survey fetch", () => {
  it("fetches surveys only for reconstructed wellbores, with bounded concurrency; a wellbore without a survey keeps the placeholder with the reason", async () => {
    const f14 = JSON.parse(readFileSync(join(import.meta.dirname, "fixtures", "asset-specs", "f14-dimensioned.json"), "utf8")) as unknown;
    // w8, w9 have no spec (404): no survey request may be made for them.
    specImpl = async (id: string) => {
      if (id === "w8" || id === "w9") throw new ApiError(404, "NOT_FOUND", "none", null);
      return { spec: f14, revision: 1, state: "current" };
    };
    let inflight = 0;
    let peak = 0;
    mockGet.mockImplementation(async (_p: string, id: string) => {
      inflight += 1;
      peak = Math.max(peak, inflight);
      await new Promise((r) => setTimeout(r, 5));
      inflight -= 1;
      if (id === "w6") throw new ApiError(404, "NOT_FOUND", "x", null, { code: "no_trajectory", sets: [] });
      return dto();
    });
    const wells = Array.from({ length: 10 }, (_, i) => ({ id: `w${i}`, name: `F / W-${i}` }));
    render(<FieldScene projectId="p" wellbores={wells} selectedId={null} onSelect={vi.fn()} onOpen={vi.fn()} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(8));
    await new Promise((r) => setTimeout(r, 50));
    expect(mockGet).toHaveBeenCalledTimes(8);
    expect(peak).toBeLessThanOrEqual(4);
    expect(mockGet.mock.calls.map((c) => c[1]).sort()).toEqual(["w0", "w1", "w2", "w3", "w4", "w5", "w6", "w7"]);
    expect(new Set(mockGet.mock.calls.map((c) => c[0]))).toEqual(new Set(["p"]));
  });
});
