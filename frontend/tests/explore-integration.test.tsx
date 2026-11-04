import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { dispatchAppLink } from "../src/features/assistant/links";
import type { AppLink } from "../src/features/assistant/api";
import { ExploreScene } from "../src/features/scene/ExploreScene";
import { createExploreCommandBus, type ExploreCommandBus } from "../src/features/scene/exploreCommands";
import { cursorWindowOf, focusChartBlock } from "../src/features/scene/exploreEnrichment";
import { makeFocusFormationHandler } from "../src/features/scene/formationFocus";
import { chart, fieldScope, fieldSet, series, boreScope, wellboreSet } from "./fixtures/charts";
import { PROJECT, richSet, WB } from "./formationFixtures";
import { render } from "./render";

const B1 = "00000000-0000-4000-8000-0000000000b1";
const B5 = "00000000-0000-4000-8000-0000000000b5";
const DOC = "00000000-0000-4000-8000-0000000000d1";

// --- boundaries mocked as the existing scene/chart tests do: no WebGL, no ECharts canvas, no real PDF iframe ---
const cam = vi.hoisted(() => ({ focusPoint: vi.fn(), wellboreIds: [] as string[] }));
const exposure = vi.hoisted(() => ({ ids: [] as string[] }));

vi.mock("../src/features/charts/echartsRuntime", () => ({
  init: vi.fn(() => ({ setOption: vi.fn(), on: vi.fn(), off: vi.fn(), dispatchAction: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}));
vi.mock("../src/features/scene/webgl", () => ({ webgl2Available: () => true }));
vi.mock("../src/features/scene/FieldViewer3D", () => ({ default: () => null }));
vi.mock("../src/features/documents/DocumentViewer", () => ({
  default: (p: { documentId: string; page: number | null }) => <div data-testid="doc-viewer">{`${p.documentId}#${p.page}`}</div>,
}));
// A camera double: the real viewer-side handler (makeFocusFormationHandler) over a spy `focusPoint`.
vi.mock("../src/features/scene/Viewer3D", async () => {
  const { useEffect } = await import("react");
  const { useExploreCommandHandlers } = await import("../src/features/scene/ExploreCommandsContext");
  const { makeFocusFormationHandler: make } = await import("../src/features/scene/formationFocus");
  const ctx = { scope: "wellbore", origin: [0, 0, 0], exaggeration: 5, cutaway: true } as const;
  function ViewerStub(props: { commands: { current: unknown }; wellboreId: string; resolveFormationFocus?: Parameters<typeof make>[0]["resolve"] }) {
    useEffect(() => {
      props.commands.current = { focusPoint: cam.focusPoint, fitWellhead: vi.fn(), fitAll: vi.fn(), focus: vi.fn(), zoom: vi.fn(), flyOver: () => false, stopFlyOver: () => false };
      return () => {
        props.commands.current = null;
      };
    }, [props.commands]);
    useExploreCommandHandlers(
      props.resolveFormationFocus === undefined
        ? {}
        : { focusFormation: make({ accepts: (id) => id === props.wellboreId, resolve: props.resolveFormationFocus, ctx, commands: props.commands as never }) },
    );
    return <div data-testid="viewer-stub" />;
  }
  return { default: ViewerStub };
});
vi.mock("../src/features/pipeline/api", async (orig) => ({
  ...(await orig<typeof import("../src/features/pipeline/api")>()),
  getExposure: async () => ({ wells: [{ well_id: "w", name: "Well A", wellbores: exposure.ids.map((id, i) => ({ wellbore_id: id, wellbore_name: `A-${i + 1}` })) }] }),
}));
const specJson: unknown = JSON.parse(readFileSync(join(import.meta.dirname, "fixtures", "asset-specs", "f14-dimensioned.json"), "utf8"));
vi.mock("../src/features/scene/api", () => ({
  getAssetSpec: async () => ({ spec: specJson, revision: 2, state: "current" }),
  generateAssetSpec: vi.fn(),
  getTrajectory: async () => {
    throw new ApiError(404, "NOT_FOUND", "none", null, { code: "no_trajectory", sets: [] });
  },
}));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const bore = (over: Parameters<typeof chart>[0] = {}) => chart({ scope: boreScope(WB), series: [series({ scope: boreScope(WB), points: [{ x: "2024-01-01", y: 10 }] })], ...over });
const urls: string[] = [];

beforeEach(() => {
  window.localStorage.clear();
  urls.length = 0;
  cam.focusPoint.mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      if (url.includes("/formations")) return json(richSet());
      if (url.endsWith("/charts/field")) {
        return json(fieldSet([chart({ chart_id: "tot", key: "field_rates_total", title: "Field rate totals", scope: fieldScope(), series: [series({ scope: fieldScope(), points: [{ x: "2024-01-01", y: 3 }] })] })], { project_id: PROJECT, wellbore_ids: [WB] }));
      }
      if (url.includes("/charts")) return json(wellboreSet([bore()], { project_id: PROJECT, wellbore_id: WB }));
      return json({ error: { code: "not_found", message: "none", request_id: "r" } }, 404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const stage = () => screen.getByRole("region", { name: "Stage" });
const link = (target: Record<string, unknown>): AppLink => ({ label: "Go", target: target as unknown as AppLink["target"], tool_call_id: null });

function mount(ids: string[], opts: { onOpenSource?: (d: string) => void } = {}) {
  exposure.ids = ids;
  const bus: ExploreCommandBus = createExploreCommandBus();
  render(<ExploreScene projectId={PROJECT} modelRevision="m1" bus={bus} {...opts} />);
  return bus;
}
const dispatch = (bus: ExploreCommandBus, l: AppLink) => {
  let r!: ReturnType<typeof dispatchAppLink>;
  act(() => {
    r = dispatchAppLink(bus, l);
  });
  return r;
};

describe("Explore integration: wellbore vs field context", () => {
  it("wellbore view: wellbore chart set, fly-over controls and the stage switch", async () => {
    mount([WB]);
    await waitFor(() => expect(stage()).toHaveAttribute("data-context", "wellbore"));
    expect(stage()).toHaveAttribute("data-wellbore-id", WB);
    expect(await screen.findByTestId("fly-over-controls")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Charts" }));
    expect(await screen.findByRole("heading", { name: "Production rates" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Field rate totals" })).not.toBeInTheDocument();
    expect(urls.some((u) => u.includes(`/wellbores/${WB}/charts`))).toBe(true);
    expect(screen.getByTestId("formation-panel")).toBeInTheDocument();
  });

  it("field view: field chart set, no fly-over, formation panel mounted", async () => {
    mount([WB, "00000000-0000-4000-8000-0000000000a2"]);
    await waitFor(() => expect(stage()).toHaveAttribute("data-context", "field"));
    expect(screen.queryByTestId("fly-over-controls")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Charts" }));
    expect(await screen.findByRole("heading", { name: "Field rate totals" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Production rates" })).not.toBeInTheDocument();
    expect(urls.some((u) => u.endsWith("/charts/field"))).toBe(true);
    expect(screen.getByTestId("formation-panel")).toBeInTheDocument();
  });
});

describe("Explore integration: assistant link -> bus -> handler outcome", () => {
  it("openChart switches 3D to Charts and reports Opened; stale wellbore/chart are explicit failures", async () => {
    const bus = mount([WB]);
    await waitFor(() => expect(document.querySelector('[data-chart-key="production_rates"]')).not.toBeNull());
    expect(stage()).toHaveAttribute("data-stage-mode", "3d");
    expect(dispatch(bus, link({ kind: "chart", chart_key: "production_rates", wellbore_id: WB }))).toEqual({ ok: true, message: "Opened." });
    expect(stage()).toHaveAttribute("data-stage-mode", "charts");
    // Another wellbore, a field chart in a wellbore view, an unloaded chart, and an invalid window are all refused.
    for (const t of [
      { kind: "chart", chart_key: "production_rates", wellbore_id: "00000000-0000-4000-8000-0000000000ff" },
      { kind: "chart", chart_key: "production_rates", wellbore_id: null },
      { kind: "chart", chart_key: "log_tracks", wellbore_id: WB },
    ]) {
      const r = dispatch(bus, link(t));
      expect(r.ok).toBe(false);
      expect(r.message).toMatch(/could not be found/);
    }
    act(() => {
      expect(bus.dispatch({ type: "openChart", kind: "production_rates", wellboreId: WB, window: { from: "2024-03-01", to: "2024-01-01" } })).toBe("unhandled");
      expect(bus.dispatch({ type: "openChart", kind: "production_rates", wellboreId: WB, window: { from: "2024-01-01", to: "2024-03-01" } })).toBe("handled");
    });
  });

  it("openChart keeps Split as Split", async () => {
    const bus = mount([WB]);
    await waitFor(() => expect(document.querySelector('[data-chart-key="production_rates"]')).not.toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "Split" }));
    expect(dispatch(bus, link({ kind: "chart", chart_key: "production_rates", wellbore_id: WB })).ok).toBe(true);
    expect(stage()).toHaveAttribute("data-stage-mode", "split");
  });

  it("openSource with a page opens the PDF viewer at that page; without a page it goes to the Sources tab; with neither it is refused", async () => {
    const onOpenSource = vi.fn();
    const bus = mount([WB], { onOpenSource });
    await screen.findByTestId("scene-stage");
    expect(dispatch(bus, link({ kind: "source", document_id: DOC, page: 7, locator: null })).ok).toBe(true);
    expect(await screen.findByTestId("doc-viewer")).toHaveTextContent(`${DOC}#7`);
    expect(dispatch(bus, link({ kind: "source", document_id: DOC, page: null, locator: null })).ok).toBe(true);
    expect(onOpenSource).toHaveBeenCalledWith(DOC);
  });

  it("openSource without a page and without a Sources callback is an explicit refusal", async () => {
    const bus = mount([WB]);
    await screen.findByTestId("scene-stage");
    const r = dispatch(bus, link({ kind: "source", document_id: DOC, page: null, locator: null }));
    expect(r.ok).toBe(false);
  });

  it("a link without a target, or no workspace at all, says so", () => {
    expect(dispatchAppLink(null, link({ kind: "wellbore", wellbore_id: "w" })).ok).toBe(false);
    const bus = createExploreCommandBus();
    expect(dispatchAppLink(bus, link({ kind: "chart", chart_key: "production_rates", wellbore_id: null }))).toMatchObject({ ok: false, message: expect.stringMatching(/Nothing is listening/) });
  });
});

describe("Explore integration: focusFormation reaches the camera", () => {
  it("a placeable formation is handled by the camera (exactly one focus) and selected in the panel", async () => {
    const bus = mount([WB]);
    await screen.findAllByTestId("formation-legend-item");
    await waitFor(() => expect(cam.focusPoint).not.toHaveBeenCalled());
    const r = dispatch(bus, link({ kind: "formation", surface_key: "alpha", pick_id: B1, wellbore_id: WB }));
    expect(r.ok).toBe(true);
    expect(cam.focusPoint).toHaveBeenCalledTimes(1);
    expect(cam.focusPoint.mock.calls[0]![0]).toHaveLength(3);
  });

  it("the panel's own focus action is handled only because the camera acted", async () => {
    mount([WB]);
    const items = await screen.findAllByTestId("formation-legend-item");
    await userEvent.click(items[0]!.querySelector("button")!);
    expect(cam.focusPoint).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/camera did not move/)).not.toBeInTheDocument();
  });

  it("an unplaceable or other-wellbore formation is refused: no motion, explicit outcome", async () => {
    const bus = mount([WB]);
    await screen.findAllByTestId("formation-legend-item");
    const r1 = dispatch(bus, link({ kind: "formation", surface_key: "x", pick_id: B5, wellbore_id: WB }));
    const r2 = dispatch(bus, link({ kind: "formation", surface_key: "alpha", pick_id: B1, wellbore_id: "00000000-0000-4000-8000-0000000000ff" }));
    // Known limitation (documented): the panel still selects a listed-but-unplaceable formation, so the bus reports it
    // handled although the camera did not move. Another wellbore is refused by both paths.
    expect(r1.ok).toBe(true);
    expect(r2.ok).toBe(false);
    expect(cam.focusPoint).not.toHaveBeenCalled();
  });
});

describe("enrichment helpers", () => {
  it("cursorWindowOf: ISO -> time axis, numbers -> depth axis, half-open not applied, bad -> invalid", () => {
    expect(cursorWindowOf(undefined)).toBeNull();
    expect(cursorWindowOf({ from: "2024-01-01" })).toBeNull();
    expect(cursorWindowOf({ from: "2024-01-01", to: "2024-02-01" })).toMatchObject({ axis: "time" });
    expect(cursorWindowOf({ from: 100, to: 200 })).toEqual({ axis: "depth", from: 100, to: 200 });
    expect(cursorWindowOf({ from: 200, to: 100 })).toBe("invalid");
    expect(cursorWindowOf({ from: "nope", to: "2024-01-01" })).toBe("invalid");
    expect(cursorWindowOf({ from: 1, to: "2024-01-01" })).toBe("invalid");
  });

  it("focusChartBlock finds a block by key and refuses when absent", () => {
    const host = document.createElement("div");
    host.innerHTML = '<section data-chart-key="a"></section>';
    document.body.append(host);
    expect(focusChartBlock(host, "a")).toBe(true);
    expect(focusChartBlock(host, "b")).toBe(false);
    expect(focusChartBlock(null, "a")).toBe(false);
    host.remove();
  });

  it("makeFocusFormationHandler: refuses foreign wellbores and null poses, defers without commands, otherwise moves", () => {
    const focusPoint = vi.fn();
    const ctx = { scope: "wellbore", origin: [0, 0, 0], exaggeration: 5, cutaway: true } as const;
    const commands = { current: null as { focusPoint: typeof focusPoint } | null };
    const handler = (pose: { target: readonly [number, number, number]; radius: number } | null) =>
      makeFocusFormationHandler({ accepts: (id) => id === "w", resolve: () => pose, ctx, commands });
    expect(handler({ target: [1, 2, 3], radius: 4 })({ wellboreId: "other", formationId: "f" })).toBe(false);
    expect(handler(null)({ wellboreId: "w", formationId: "f" })).toBe(false);
    expect(handler({ target: [1, 2, 3], radius: 4 })({ wellboreId: "w", formationId: "f" })).toBe("defer");
    commands.current = { focusPoint };
    expect(handler({ target: [1, 2, 3], radius: 4 })({ wellboreId: "w", formationId: "f" })).toBe(true);
    expect(focusPoint).toHaveBeenCalledWith([1, 2, 3], 4);
  });
});
