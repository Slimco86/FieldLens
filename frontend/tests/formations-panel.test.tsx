import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { FormationPanel } from "../src/features/context/formations/FormationPanel";
import { createFormationStore } from "../src/features/context/formations/formationStore";
import { formationsPath, useFormationLayers, type FormationLayersState } from "../src/features/context/formations/useFormationLayers";
import { ExploreCommandsProvider } from "../src/features/scene/ExploreCommandsContext";
import { createExploreCommandBus, type ExploreCommandBus } from "../src/features/scene/exploreCommands";
import { emptySet, PROJECT, richSet, WB } from "./formationFixtures";

// A plain function (not vi.fn) so a rejected promise is only ever observed by the code under test.
const api = vi.hoisted(() => ({ impl: (() => Promise.resolve(undefined)) as (path: string, signal: AbortSignal) => Promise<unknown>, calls: [] as [string, AbortSignal][] }));
vi.mock("../src/api/client", async (orig) => ({
  ...(await orig<typeof import("../src/api/client")>()),
  getJson: (path: string, signal: AbortSignal) => {
    api.calls.push([path, signal]);
    return api.impl(path, signal);
  },
}));
const resolveWith = (v: unknown) => {
  api.impl = () => Promise.resolve(v);
};
const rejectWith = (e: unknown) => {
  api.impl = () => Promise.reject(e);
};

const B1 = "00000000-0000-4000-8000-0000000000b1";

describe("formationsPath", () => {
  it("scopes by project and wellbore", () => {
    expect(formationsPath("p 1", { kind: "field" })).toBe("/api/v1/projects/p%201/formations");
    expect(formationsPath("p", { kind: "wellbore", wellboreId: "w" })).toBe("/api/v1/projects/p/wellbores/w/formations");
  });
});

describe("useFormationLayers", () => {
  beforeEach(() => {
    api.calls.length = 0;
    resolveWith(undefined);
  });
  afterEach(() => vi.restoreAllMocks());
  const wb = { kind: "wellbore", wellboreId: WB } as const;

  it("moves loading -> ready with the revision, normalized", async () => {
    resolveWith(richSet());
    const { result } = renderHook(() => useFormationLayers(PROJECT, wb));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.revision).toBe("rev-1");
    expect(api.calls[0]?.[0]).toBe(`/api/v1/projects/${PROJECT}/wellbores/${WB}/formations`);
  });

  it("reports empty when nothing at all is stored, and idle without a project", async () => {
    resolveWith(emptySet());
    const { result } = renderHook(() => useFormationLayers(PROJECT, { kind: "field" }));
    await waitFor(() => expect(result.current.status).toBe("empty"));
    expect(result.current.data?.empty_reason).toBe("no formation picks in this project");
    const idle = renderHook(() => useFormationLayers(null, wb));
    expect(idle.result.current.status).toBe("idle");
  });

  it("reports errors with a readable message and never partial data", async () => {
    rejectWith(new ApiError(404, "not_found", "nope", null));
    const { result } = renderHook(() => useFormationLayers(PROJECT, wb));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toMatch(/not found/);
  });

  it("describes a network failure", async () => {
    rejectWith(new Error("boom"));
    const { result } = renderHook(() => useFormationLayers(PROJECT, { kind: "field" }));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toMatch(/boom/);
  });

  it("never shows another project's or revision's data while the new request is pending", async () => {
    resolveWith(richSet());
    const { result, rerender } = renderHook(({ p, r }: { p: string; r: number }) => useFormationLayers(p, wb, r), { initialProps: { p: PROJECT, r: 1 } });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    let release: (v: unknown) => void = () => undefined;
    api.impl = () => new Promise((r) => (release = r));
    rerender({ p: "other", r: 1 });
    expect(result.current.status).toBe("loading");
    expect(result.current.data).toBeNull();
    rerender({ p: PROJECT, r: 2 });
    expect(api.calls).toHaveLength(3);
    expect(result.current.status).toBe("loading");
    await act(async () => release(richSet()));
  });

  it("aborts the superseded request and ignores its late answer", async () => {
    let resolveFirst: (v: unknown) => void = () => undefined;
    const signals: AbortSignal[] = [];
    api.impl = (_p, s) => {
      signals.push(s);
      return new Promise((r) => (resolveFirst = r));
    };
    const { result, rerender } = renderHook(({ r }: { r: number }) => useFormationLayers(PROJECT, wb, r), { initialProps: { r: 1 } });
    resolveWith({ ...emptySet(), generated_from_revision: "new", surfaces: richSet().surfaces });
    rerender({ r: 2 });
    expect(signals[0]!.aborted).toBe(true);
    await waitFor(() => expect(result.current.revision).toBe("new"));
    await act(async () => resolveFirst(richSet()));
    expect(result.current.revision).toBe("new");
  });
});

const readyState = (data = richSet()): FormationLayersState => ({ status: "ready", data, error: null, revision: data.generated_from_revision });

function setup(state: FormationLayersState, bus: ExploreCommandBus = createExploreCommandBus(), wellboreId: string | null = WB) {
  const store = createFormationStore();
  const ui = render(
    <ExploreCommandsProvider bus={bus}>
      <FormationPanel state={state} store={store} wellboreId={wellboreId} />
    </ExploreCommandsProvider>,
  );
  return { store, bus, ...ui };
}

describe("FormationPanel", () => {
  it("shows loading, error and empty states without touching other content", () => {
    const a = setup({ status: "loading", data: null, error: null, revision: null });
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Loading formations");
    a.unmount();
    const b = setup({ status: "error", data: null, error: "Formation data could not be loaded (x).", revision: null });
    expect(screen.getByRole("alert")).toHaveTextContent(/unavailable.*other layers are unaffected/);
    b.unmount();
    setup({ status: "empty", data: emptySet(), error: null, revision: "rev-0" });
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("no formation picks in this project");
    expect(screen.queryByLabelText("Formation legend")).toBeNull();
  });

  it("lists legend items with tier/status and reasons, and everything not drawn", () => {
    setup(readyState());
    const items = screen.getAllByTestId("formation-legend-item");
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveTextContent("T2 level plane - illustrative");
    expect(items[0]).toHaveTextContent("illustrative");
    expect(items[1]).toHaveTextContent(/Plane not drawn: unknown_datum/);
    expect(items[3]).toHaveTextContent(/tier_not_rendered/);
    const nd = screen.getAllByTestId("formation-not-drawn").map((n) => n.textContent ?? "");
    expect(nd.some((t) => t.includes("tvd_conflict"))).toBe(true);
    expect(nd.some((t) => t.includes("qualifier FP"))).toBe(true);
    expect(nd.some((t) => t.includes("datum_mismatch"))).toBe(true);
    expect(screen.getByText(/true scale \(not exaggerated\), not an interpreted horizon/)).toBeInTheDocument();
  });

  it("toggles the layer, a surface, opacity and label mode through the store", async () => {
    const u = userEvent.setup();
    const { store } = setup(readyState());
    await u.click(screen.getByLabelText("Show formations"));
    expect(store.getState().visible).toBe(false);
    await u.click(screen.getByLabelText("Show Alpha"));
    expect(store.getState().hidden.has("alpha")).toBe(true);
    await u.selectOptions(screen.getByLabelText("Labels"), "off");
    expect(store.getState().labelMode).toBe("off");
    const range = screen.getByLabelText("Plane opacity");
    expect(range).toHaveAttribute("aria-valuetext", "22 percent");
  });

  it("shows the inspector for a selection, with depths, datum and source links", async () => {
    const { store } = setup(readyState());
    expect(screen.queryByTestId("formation-inspector")).toBeNull();
    await act(async () => store.select(B1));
    const ins = screen.getByTestId("formation-inspector");
    expect(ins).toHaveTextContent("MD 1500 m (along bore)");
    expect(ins).toHaveTextContent("TVD 1450 m (datum KB)");
    expect(ins).toHaveTextContent("TVDSS 1400 m (datum MSL)");
    expect(ins).toHaveTextContent("T1 pick marker");
    await act(async () => store.hover("00000000-0000-4000-8000-0000000000b3"));
    expect(screen.getByTestId("formation-inspector")).toHaveTextContent("(hover)");
    expect(screen.getByTestId("formation-inspector")).toHaveTextContent("datum unknown, not assumed");
  });

  it("opens the source through the bus and announces each non-handled outcome", async () => {
    const u = userEvent.setup();
    const bus = createExploreCommandBus();
    const { store } = setup(readyState(), bus);
    await act(async () => store.select(B1));
    await u.click(screen.getByRole("button", { name: /Open source \(page 7\)/ }));
    expect(screen.getByTestId("formation-message")).toHaveTextContent(/source viewer is not available/);
    const open = vi.fn(() => false);
    bus.subscribe({ openSource: open });
    await u.click(screen.getByRole("button", { name: /Open source/ }));
    expect(open).toHaveBeenCalledWith(expect.objectContaining({ source: expect.objectContaining({ page: 7 }) }));
    expect(screen.getByTestId("formation-message")).toHaveTextContent(/could not be opened/);
    bus.subscribe({ openSource: () => true });
    await u.click(screen.getByRole("button", { name: /Open source/ }));
    expect(screen.getByTestId("formation-message")).toBeEmptyDOMElement();
  });

  it("selects and focuses from the legend; missing camera is announced, a camera subscriber is honoured", async () => {
    const u = userEvent.setup();
    const bus = createExploreCommandBus();
    const { store } = setup(readyState(), bus);
    await u.click(screen.getByRole("button", { name: "Alpha" }));
    expect(store.getState().selectedId).toBe("plane:alpha");
    // Its own focusFormation handler must not make the bus report "handled".
    expect(screen.getByTestId("formation-message")).toHaveTextContent(/camera did not move/);
    const cam = vi.fn(() => true);
    bus.subscribe({ focusFormation: cam });
    await u.click(screen.getByRole("button", { name: "Focus camera" }));
    expect(cam).toHaveBeenCalledWith({ type: "focusFormation", wellboreId: WB, formationId: "plane:alpha" });
    expect(screen.getByTestId("formation-message")).toBeEmptyDOMElement();
  });

  it("answers external focusFormation commands by selecting, and refuses unknown ids", () => {
    const { store, bus } = setup(readyState());
    expect(bus.dispatch({ type: "focusFormation", wellboreId: WB, formationId: B1 })).toBe("handled");
    expect(store.getState().selectedId).toBe(B1);
    expect(bus.dispatch({ type: "focusFormation", wellboreId: WB, formationId: "gone" })).toBe("unhandled");
    expect(bus.dispatch({ type: "focusFormation", wellboreId: "other", formationId: B1 })).toBe("unhandled");
  });
});
