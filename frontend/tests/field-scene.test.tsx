import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { FieldScene } from "../src/features/scene/FieldScene";
import { dropdownWellbores } from "../src/features/scene/ExploreScene";
import type { FieldSpecState } from "../src/features/scene/fieldModel";
import { render } from "./render";

const dir = join(import.meta.dirname, "fixtures", "asset-specs");
const spec = (f: string): unknown => JSON.parse(readFileSync(join(dir, f), "utf8"));

// A plain function (not vi.fn): rejected 404 promises are the normal "no spec yet" answer here.
let specImpl: (id: string) => Promise<unknown> = async () => {
  throw new Error("not configured");
};
vi.mock("../src/features/scene/api", () => ({
  getAssetSpec: (_p: string, id: string) => specImpl(id),
  generateAssetSpec: vi.fn(),
  getTrajectory: (_p: string, id: string) => trajImpl(id),
}));

// Survey API double: a 404 `no_trajectory` unless a test supplies one.
let trajImpl: (id: string) => Promise<unknown> = async () => {
  throw new ApiError(404, "NOT_FOUND", "none", null, { code: "no_trajectory", sets: [] });
};

const WELLS = [
  { id: "a", name: "Field A / A-1" },
  { id: "b", name: "Field A / A-2" },
  { id: "c", name: "Field A / A-3" },
];

function mockSpecs(files: Record<string, string | null | "fail">) {
  specImpl = async (id: string) => {
    const f = files[id];
    if (f === null || f === undefined) throw new ApiError(404, null, "none", null);
    if (f === "fail") throw new ApiError(500, null, "down", null);
    return { spec: spec(f), revision: 2, state: "current" };
  };
}

function mount(selected: string | null = null) {
  const onSelect = vi.fn();
  const onOpen = vi.fn();
  render(<FieldScene projectId="p" wellbores={WELLS} selectedId={selected} onSelect={onSelect} onOpen={onOpen} />);
  return { onSelect, onOpen };
}

describe("field scene (no WebGL in jsdom: list and inspector paths)", () => {
  it("lists ONLY reconstructed wellbores (failed loads stay for retry), keeps the summary counts and the permanent badges", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: null, c: "fail" });
    mount();
    expect(screen.getByTestId("illustrative-badge")).toHaveTextContent("Illustrative visual — not an engineering model");
    expect(screen.getByTestId("field-layout-badge")).toHaveTextContent(/schematic layout, not map positions/i);
    await waitFor(() => expect(screen.getByTestId("field-summary")).toHaveTextContent("3 wellbores: 1 reconstructed (with asset spec), 1 not reconstructed (not listed or drawn), 1 failed"));
    const items = screen.getAllByRole("button").filter((b) => b.hasAttribute("data-wellbore-id"));
    expect(items.map((b) => b.getAttribute("data-wellbore-id"))).toEqual(["a", "c"]);
    expect(items.map((b) => b.getAttribute("data-status"))).toEqual(["spec", "error"]);
  });

  it("requests surveys only for reconstructed wellbores", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: null, c: null });
    const asked: string[] = [];
    trajImpl = async (id: string) => {
      asked.push(id);
      throw new ApiError(404, "NOT_FOUND", "none", null, { code: "no_trajectory", sets: [] });
    };
    mount();
    await waitFor(() => expect(asked).toEqual(["a"]));
    await waitFor(() => expect(screen.getByTestId("scene-fallback")).toBeInTheDocument());
    expect(asked).toEqual(["a"]);
  });

  it("same stated CRS/datum/unit on every drawn wellbore: surface-location layout label and placement in the inspector", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: null });
    trajImpl = async (id: string) => ({
      survey_set: { filename: "SSR.pdf" },
      survey_status: "as_built",
      md_min_m: 0,
      md_max_m: 1000,
      points: [
        { md_m: 0, tvd_m: 0, east_m: 0, north_m: 0 },
        { md_m: 1000, tvd_m: 900, east_m: 200, north_m: 40 },
      ],
      surface_location: { easting: id === "a" ? 435000 : 435010, northing: 6478000, unit: "m", latitude: null, longitude: null, crs: "ED50 / UTM zone 31N", geodetic_datum: "ED50" },
      md_reference: null,
      tvd_reference: null,
      azimuth_reference: "grid north",
      north_reference: "grid",
      displayed_count: 2,
      source_count: 2,
      other_sets: [],
      warnings: [],
    });
    mount("b");
    await waitFor(() =>
      expect(screen.getByTestId("field-layout-badge")).toHaveTextContent("Surface-location layout (E/N offsets from the field centroid, ED50 / UTM zone 31N)"),
    );
    await waitFor(() => expect(screen.getByTestId("field-inspector-placement")).toHaveTextContent("E 5 m, N 0 m from the field centroid"));
    expect(screen.getByTestId("field-inspector-surface")).toHaveTextContent("ED50 / UTM zone 31N");
    trajImpl = async () => {
      throw new ApiError(404, "NOT_FOUND", "none", null, { code: "no_trajectory", sets: [] });
    };
  });

  it("the single-view dropdown lists reconstructed wellbores plus the shown one", () => {
    const specs = new Map<string, FieldSpecState>([
      ["a", { kind: "ready", spec: spec("f14-dimensioned.json") as never, revision: 1 }],
      ["b", { kind: "missing" }],
      ["c", { kind: "error", message: "x" }],
    ]);
    expect(dropdownWellbores(WELLS, specs, "a").map((w) => w.id)).toEqual(["a"]);
    expect(dropdownWellbores(WELLS, specs, "b").map((w) => w.id)).toEqual(["a", "b"]);
  });

  it("the inspector shows the survey label and location, or the placeholder reason for a wellbore without a valid survey", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: null });
    trajImpl = async (id: string) => {
      if (id === "b") throw new ApiError(404, "NOT_FOUND", "none", null, { code: "no_trajectory", sets: [{ reasons: ["TRAJECTORY_PLANNED_ONLY"] }] });
      return {
        survey_set: { filename: "SSR.pdf" },
        survey_status: "as_built",
        md_min_m: 0,
        md_max_m: 1000,
        points: [
          { md_m: 0, tvd_m: 0, east_m: 0, north_m: 0 },
          { md_m: 1000, tvd_m: 900, east_m: 200, north_m: 40 },
        ],
        surface_location: { easting: 1, northing: 2, unit: "m", latitude: null, longitude: null, crs: null, geodetic_datum: null },
        md_reference: null,
        tvd_reference: null,
        azimuth_reference: "grid north",
        north_reference: "grid",
        displayed_count: 2,
        source_count: 2,
        other_sets: [],
        warnings: [],
      };
    };
    const { unmount } = render(<FieldScene projectId="p" wellbores={WELLS} selectedId="a" onSelect={vi.fn()} onOpen={vi.fn()} />);
    await waitFor(() => expect(screen.getByTestId("field-inspector-trajectory")).toHaveTextContent("Survey: SSR.pdf, as-built, MD 0-1000 m"));
    expect(screen.getByTestId("field-inspector-surface")).toHaveTextContent("Surface location: E 1 m, N 2 m (CRS not stated)");
    unmount();
    render(<FieldScene projectId="p" wellbores={WELLS} selectedId="b" onSelect={vi.fn()} onOpen={vi.fn()} />);
    await waitFor(() => expect(screen.getByTestId("field-inspector-trajectory")).toHaveTextContent("only a planned survey exists"));
    expect(screen.getByTestId("field-inspector-trajectory")).toHaveTextContent("vertical placeholder");
  });

  it("shows a clear empty state when no wellbore has a spec and lists nothing", async () => {
    mockSpecs({});
    mount();
    expect(await screen.findByText("No visual asset specs yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button").filter((b) => b.hasAttribute("data-wellbore-id"))).toHaveLength(0);
    expect(screen.getByTestId("field-summary")).toHaveTextContent("3 wellbores: 0 reconstructed (with asset spec), 3 not reconstructed");
    expect(screen.getByTestId("illustrative-badge")).toBeInTheDocument();
  });

  it("list selection selects first and opens the wellbore view on the second activation", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: "f12-unlocated.json" });
    const first = mount();
    await waitFor(() => expect(screen.getByTestId("field-summary")).toHaveTextContent("3 reconstructed"));
    fireEvent.click(document.querySelector('[data-wellbore-id="b"]')!);
    expect(first.onSelect).toHaveBeenCalledWith("b");
    expect(first.onOpen).not.toHaveBeenCalled();
  });

  it("an already selected wellbore opens; the inspector summarises it and Open is enabled", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: null });
    const { onOpen } = mount("b");
    await waitFor(() => expect(screen.getByTestId("field-inspector-name")).toHaveTextContent("Field A / A-2"));
    expect(screen.getByTestId("field-inspector")).toHaveTextContent("Revision");
    expect(screen.getByTestId("field-open")).toBeEnabled();
    fireEvent.click(document.querySelector('[data-wellbore-id="b"]')!);
    expect(onOpen).toHaveBeenCalledWith("b");
  });

  it("arrow keys move focus through the list", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: "f12-unlocated.json" });
    mount();
    await waitFor(() => expect(screen.getByTestId("field-summary")).toHaveTextContent("3 reconstructed"));
    const items = Array.from(document.querySelectorAll<HTMLButtonElement>("button[data-wellbore-id]"));
    items[0]!.focus();
    fireEvent.keyDown(items[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(items[1]!, { key: "End" });
    expect(document.activeElement).toBe(items[2]);
  });

  it("returning from the wellbore view focuses the selected list item", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: "f12-unlocated.json" });
    render(<FieldScene projectId="p" wellbores={WELLS} selectedId="b" onSelect={vi.fn()} onOpen={vi.fn()} restoreFocus />);
    await waitFor(() => expect(document.activeElement).toBe(document.querySelector('button[data-wellbore-id="b"]')));
  });

  it("does not steal focus on a first visit", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: "f12-unlocated.json" });
    mount("b");
    await waitFor(() => expect(screen.getByTestId("field-summary")).toHaveTextContent("3 reconstructed"));
    expect(document.activeElement).toBe(document.body);
  });

  it("a not-yet-reconstructed wellbore is neither listed nor selectable in the field view", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: null, c: null });
    mount("b");
    await waitFor(() => expect(screen.getByTestId("field-summary")).toHaveTextContent("2 not reconstructed"));
    expect(document.querySelector('[data-wellbore-id="b"]')).toBeNull();
    expect(screen.getByTestId("field-inspector")).toHaveTextContent("Select a wellbore");
  });
});
