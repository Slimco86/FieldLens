import { act, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExploreWorkspace } from "../src/app/shell/ExploreWorkspace";
import { readStageMode, STAGE_MODE_STORAGE_KEY, useExploreStage } from "../src/app/shell/exploreStage";
import { ExploreCommandsProvider, useExploreCommandBus, useExploreCommandHandlers } from "../src/features/scene/ExploreCommandsContext";
import { createExploreCommandBus, FLY_OVER_STATE } from "../src/features/scene/exploreCommands";
import { renderLayers } from "../src/features/scene/sceneLayers";
import { render } from "./render";

describe("ExploreCommands bus", () => {
  it("reports no-subscriber, handled and unhandled", () => {
    const bus = createExploreCommandBus();
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "w1" })).toBe("queued");
    const off = bus.subscribe({ focusWellbore: (p) => p.wellboreId === "w1" });
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "w1" })).toBe("handled");
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "zz" })).toBe("unhandled");
    expect(bus.dispatch({ type: "openChart", kind: "k", wellboreId: null })).toBe("no-subscriber");
    off();
    off();
    expect(bus.size).toBe(0);
    expect(bus.dispatch({ type: "openChart", kind: "k", wellboreId: null })).toBe("no-subscriber");
  });

  it("fans out to every subscriber and any acting one wins", () => {
    const bus = createExploreCommandBus();
    const a = vi.fn(() => false);
    const b = vi.fn(() => true);
    bus.subscribe({ openSource: a });
    bus.subscribe({ openSource: b });
    expect(bus.dispatch({ type: "openSource", source: { documentId: "d", page: 3 } })).toBe("handled");
    expect(a).toHaveBeenCalledOnce();
    expect(b).toHaveBeenCalledOnce();
  });

  it("queues focus/fly-over commands until a subscriber can act, bounded and expiring (S-1)", () => {
    let t = 0;
    const bus = createExploreCommandBus({ now: () => t, ttlMs: 1000, maxPending: 2 });
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "w1" })).toBe("queued");
    expect(bus.pending).toBe(1);
    // Focus commands supersede each other (last value wins).
    expect(bus.dispatch({ type: "focusElement", wellboreId: "w1", elementId: "e1" })).toBe("queued");
    expect(bus.pending).toBe(1);
    expect(bus.dispatch({ type: "flyOver", wellboreId: "w1" })).toBe("queued");
    expect(bus.pending).toBe(2);
    // Non-navigation commands are never queued: explicit no-subscriber.
    expect(bus.dispatch({ type: "openSource", source: { documentId: "d" } })).toBe("no-subscriber");
    expect(bus.dispatch({ type: "stopFlyOver" })).toBe("no-subscriber");
    const focus = vi.fn(() => true);
    const fly = vi.fn(() => true);
    bus.subscribe({ focusElement: focus, flyOver: fly });
    expect(focus).toHaveBeenCalledWith({ type: "focusElement", wellboreId: "w1", elementId: "e1" });
    expect(fly).toHaveBeenCalledOnce();
    expect(bus.pending).toBe(0);

    expect(bus.dispatch({ type: "focusFormation", wellboreId: "w", formationId: "f" })).toBe("queued");
    t = 2000;
    expect(bus.pending).toBe(0);
  });

  it("holds commands for a mounted-but-not-ready subscriber and replays them", () => {
    const bus = createExploreCommandBus();
    let ready = false;
    const h = vi.fn(() => (ready ? true : ("defer" as const)));
    bus.subscribe({ focusWellbore: h });
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "w" })).toBe("queued");
    bus.replay();
    expect(bus.pending).toBe(1);
    ready = true;
    bus.replay();
    expect(bus.pending).toBe(0);
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "w" })).toBe("handled");
  });

  it("reports a refusing ready subscriber as unhandled, not queued (AV-4)", () => {
    const bus = createExploreCommandBus();
    bus.subscribe({ focusWellbore: () => false });
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "w" })).toBe("unhandled");
    expect(bus.pending).toBe(0);
  });

  it("isolates throwing subscribers (S-3)", () => {
    const errors: unknown[] = [];
    const bus = createExploreCommandBus({ onError: (e) => errors.push(e) });
    const ok = vi.fn(() => true);
    bus.subscribe({ openSource: () => { throw new Error("boom"); } });
    bus.subscribe({ openSource: ok });
    expect(bus.dispatch({ type: "openSource", source: { documentId: "d" } })).toBe("handled");
    expect(ok).toHaveBeenCalledOnce();
    expect(errors).toHaveLength(1);
    const bus2 = createExploreCommandBus({ onError: () => { throw new Error("reporter"); } });
    bus2.subscribe({ openSource: () => { throw new Error("boom"); } });
    expect(bus2.dispatch({ type: "openSource", source: { documentId: "d" } })).toBe("unhandled");
  });

  it("implements flyOver/stopFlyOver on the bus", () => {
    const bus = createExploreCommandBus();
    const fly = vi.fn(() => true);
    const stop = vi.fn(() => true);
    bus.subscribe({ flyOver: fly, stopFlyOver: stop });
    expect(FLY_OVER_STATE).toBe("implemented");
    expect(bus.dispatch({ type: "flyOver", wellboreId: "w" })).toBe("handled");
    expect(bus.dispatch({ type: "stopFlyOver" })).toBe("handled");
    expect(fly).toHaveBeenCalledOnce();
    expect(stop).toHaveBeenCalledOnce();
  });

  it("registers through the hook with the latest closure and unregisters on unmount", () => {
    const bus = createExploreCommandBus();
    const wrapper = ({ children }: { children: ReactNode }) => <ExploreCommandsProvider bus={bus}>{children}</ExploreCommandsProvider>;
    const calls: string[] = [];
    const { rerender, unmount } = renderHook(({ tag }) => useExploreCommandHandlers({ focusElement: () => (calls.push(tag), true) }), {
      wrapper,
      initialProps: { tag: "one" },
    });
    expect(bus.size).toBe(1);
    rerender({ tag: "two" });
    expect(bus.size).toBe(1);
    bus.dispatch({ type: "focusElement", wellboreId: "w", elementId: "e" });
    expect(calls).toEqual(["two"]);
    unmount();
    expect(bus.size).toBe(0);
  });

  it("is inert without a provider", () => {
    const { result } = renderHook(() => {
      useExploreCommandHandlers({ focusWellbore: () => true });
      return useExploreCommandBus();
    });
    expect(result.current).toBeNull();
  });
});

describe("scene layers slot", () => {
  it("is empty by default and passes the frame to a render prop", () => {
    const ctx = { scope: "wellbore", origin: [0, 0, 0], exaggeration: 5, cutaway: true } as const;
    expect(renderLayers(undefined, ctx)).toBeNull();
    const fn = vi.fn(() => "x");
    expect(renderLayers(fn, ctx)).toBe("x");
    expect(fn).toHaveBeenCalledWith(ctx);
  });
});

function Probe() {
  const s = useExploreStage();
  return <output data-testid="probe">{s === null ? "none" : `${s.mode}:${s.context.kind === "wellbore" ? s.context.wellboreId : "field"}`}</output>;
}

describe("Explore stage regions", () => {
  beforeEach(() => window.localStorage.clear());

  it("renders the plain stage (no switch) when no charts slot is given", () => {
    render(<ExploreWorkspace stage={<p>scene</p>} />);
    expect(screen.queryByRole("group", { name: "Stage mode" })).toBeNull();
    expect(screen.getByText("scene")).toBeVisible();
  });

  it("switches 3D / Charts / Split by keyboard, keeping panes mounted, and persists", async () => {
    const user = userEvent.setup();
    render(<ExploreWorkspace stage={<p>scene</p>} charts={<p>charts-slot</p>} context={{ kind: "wellbore", wellboreId: "wb-1" }} assistant={<p>assist</p>} />);
    expect(screen.getByRole("group", { name: "Stage mode" })).toBeInTheDocument();
    const [b3d, bCharts, bSplit] = ["3D", "Charts", "Split"].map((n) => screen.getByRole("button", { name: n })) as [HTMLElement, HTMLElement, HTMLElement];
    expect(b3d).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("scene")).toBeVisible();
    expect(screen.getByText("charts-slot")).not.toBeVisible();

    await act(async () => b3d.focus());
    await user.tab();
    expect(bCharts).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(bCharts).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("scene")).not.toBeVisible();
    expect(screen.getByText("charts-slot")).toBeVisible();
    expect(window.localStorage.getItem(STAGE_MODE_STORAGE_KEY)).toBe("charts");

    await user.click(bSplit);
    expect(screen.getByText("scene")).toBeVisible();
    expect(screen.getByText("charts-slot")).toBeVisible();
    expect(screen.getByRole("region", { name: "Assistant" })).toBeInTheDocument();
  });

  it("restores the persisted mode and ignores junk", () => {
    window.localStorage.setItem(STAGE_MODE_STORAGE_KEY, "split");
    expect(readStageMode()).toBe("split");
    window.localStorage.setItem(STAGE_MODE_STORAGE_KEY, "nonsense");
    expect(readStageMode()).toBe("3d");
  });

  it("exposes mode and wellbore/field context to slots", async () => {
    const { unmount } = render(<ExploreWorkspace stage={<Probe />} charts={<p>c</p>} context={{ kind: "wellbore", wellboreId: "wb-9" }} />);
    expect(screen.getByTestId("probe")).toHaveTextContent("3d:wb-9");
    expect(screen.getByRole("region", { name: "Stage" })).toHaveAttribute("data-wellbore-id", "wb-9");
    unmount();
    render(<ExploreWorkspace stage={<Probe />} />);
    expect(screen.getByTestId("probe")).toHaveTextContent("3d:field");
  });
});
