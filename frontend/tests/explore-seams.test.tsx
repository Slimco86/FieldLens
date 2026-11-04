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
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "w1" })).toBe("no-subscriber");
    const off = bus.subscribe({ focusWellbore: (p) => p.wellboreId === "w1" });
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "w1" })).toBe("handled");
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "zz" })).toBe("unhandled");
    expect(bus.dispatch({ type: "focusFormation", wellboreId: "w1", formationId: "f" })).toBe("no-subscriber");
    off();
    off();
    expect(bus.size).toBe(0);
    expect(bus.dispatch({ type: "focusWellbore", wellboreId: "w1" })).toBe("no-subscriber");
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

  it("keeps flyOver/stopFlyOver as documented stubs", () => {
    const bus = createExploreCommandBus();
    const h = vi.fn(() => true);
    bus.subscribe({ focusWellbore: h });
    expect(FLY_OVER_STATE).toBe("not-implemented");
    expect(bus.dispatch({ type: "flyOver", wellboreId: "w" })).toBe("not-implemented");
    expect(bus.dispatch({ type: "stopFlyOver" })).toBe("not-implemented");
    expect(h).not.toHaveBeenCalled();
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
