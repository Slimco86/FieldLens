import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChartBlock } from "../src/features/charts/ChartBlock";
import { ChartCursorProvider, createChartCursorStore } from "../src/features/charts/chartCursor";
import { ExploreCommandsProvider } from "../src/features/scene/ExploreCommandsContext";
import { createExploreCommandBus } from "../src/features/scene/exploreCommands";
import { chart, emptyChart, series, wellScope } from "./fixtures/charts";
import { render } from "./render";

interface Fake {
  setOption: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  off: ReturnType<typeof vi.fn>;
  dispatchAction: ReturnType<typeof vi.fn>;
  resize: ReturnType<typeof vi.fn>;
  dispose: ReturnType<typeof vi.fn>;
  handlers: Record<string, (e: unknown) => void>;
}
const h = vi.hoisted(() => ({ instances: [] as Fake[], failNext: false }));

vi.mock("../src/features/charts/echartsRuntime", () => ({
  init: vi.fn(() => {
    if (h.failNext) {
      h.failNext = false;
      throw new Error("no canvas");
    }
    const handlers: Record<string, (e: unknown) => void> = {};
    const inst: Fake = {
      setOption: vi.fn(),
      on: vi.fn((name: string, fn: (e: unknown) => void) => {
        handlers[name] = fn;
      }),
      off: vi.fn(),
      dispatchAction: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
      handlers,
    };
    h.instances.push(inst);
    return inst;
  }),
}));

const observers: { cb: () => void; disconnected: boolean }[] = [];
let width = 600;

beforeEach(() => {
  h.instances.length = 0;
  observers.length = 0;
  width = 600;
  vi.stubGlobal(
    "ResizeObserver",
    class {
      rec = { cb: () => undefined as void, disconnected: false };
      constructor(cb: () => void) {
        this.rec.cb = cb;
        observers.push(this.rec);
      }
      observe() {}
      unobserve() {}
      disconnect() {
        this.rec.disconnected = true;
      }
    },
  );
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => width });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 280 });
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientWidth;
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).clientHeight;
});

const ready = () => waitFor(() => expect(h.instances).toHaveLength(1));

describe("ChartBlock (XC-6 accessibility, lifecycle)", () => {
  it("shows scope badges, as-of/window, a text summary and mounts the lazy chart", async () => {
    render(<ChartBlock spec={chart({ window: { from: "2024-01-01", to: "2024-03-31" } })} />);
    expect(screen.getByRole("heading", { name: "Production rates" })).toBeInTheDocument();
    expect(screen.getByText("Wellbore-level A-1")).toBeInTheDocument();
    expect(screen.getByText(/As of 2024-03-31 · Window 2024-01-01 to 2024-03-31/)).toBeInTheDocument();
    const plot = screen.getByRole("img", { name: /Production rates\..*2 valid values, 1 gaps/ });
    await ready();
    expect(plot).toHaveAttribute("data-engine", "ready");
    const option = h.instances[0]!.setOption.mock.calls[0]![0] as { series: { data: unknown[] }[] };
    expect(option.series[0]!.data[1]).toEqual(["2024-02-01", null]);
  });

  it("labels well-level series as well-level, never as the wellbore", async () => {
    render(<ChartBlock spec={chart({ series: [series({ scope: wellScope(), points: [{ x: "2024-01-01", y: 1 }] })] })} />);
    expect(screen.getAllByText("Well-level").length).toBeGreaterThan(0);
    await ready();
  });

  it("disposes the instance, its listeners and the observer on unmount", async () => {
    const { unmount } = render(<ChartBlock spec={chart()} />);
    await ready();
    unmount();
    expect(h.instances[0]!.dispose).toHaveBeenCalledOnce();
    expect(h.instances[0]!.off).toHaveBeenCalledWith("datazoom");
    expect(observers.every((o) => o.disconnected)).toBe(true);
  });

  it("does not create an instance when unmounted before the chunk resolves", async () => {
    const { unmount } = render(<ChartBlock spec={chart()} />);
    unmount();
    await new Promise((r) => setTimeout(r, 20));
    expect(h.instances).toHaveLength(0);
  });

  it("resizes when revealed from a hidden pane, not while it has no size", async () => {
    render(<ChartBlock spec={chart()} />);
    await ready();
    width = 0;
    act(() => observers.forEach((o) => o.cb()));
    expect(h.instances[0]!.resize).not.toHaveBeenCalled();
    width = 640;
    act(() => observers.forEach((o) => o.cb()));
    expect(h.instances[0]!.resize).toHaveBeenCalledOnce();
  });

  it("offers a keyboard-reachable data table with gaps stated and a point pager", async () => {
    const user = userEvent.setup();
    const pts = Array.from({ length: 250 }, (_, i) => ({ x: `2024-01-01T00:${String(i % 60).padStart(2, "0")}:00`, y: i === 1 ? null : i }));
    render(<ChartBlock spec={chart({ series: [series({ points: pts })] })} />);
    await ready();
    const toggle = screen.getByRole("button", { name: "Show data table" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    toggle.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Hide data table" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("table", { name: /Series summary/ })).toBeInTheDocument();
    const points = screen.getByRole("table", { name: /Supplied points of Oil rate \(250\)/ });
    expect(points).toHaveTextContent("gap (no value)");
    expect(screen.getAllByRole("row")).toHaveLength(1 + 1 + 1 + 100); // summary header+row, points header + 100
    await user.click(screen.getByRole("button", { name: "Show 100 more points" }));
    expect(screen.getAllByRole("row")).toHaveLength(1 + 1 + 1 + 200);
  });

  it("explains an empty chart with its reason and draws nothing", () => {
    render(<ChartBlock spec={emptyChart("pressure_tests", "no_records")} />);
    expect(screen.getByText("No records in project")).toBeInTheDocument();
    expect(screen.getByText(/No pressure-test records exist/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(h.instances).toHaveLength(0);
  });

  it("surfaces an ambiguous association instead of picking a wellbore", async () => {
    const amb = { ...wellScope(), ambiguity: "Two wellbores share label A-1" };
    render(<ChartBlock spec={chart({ scope: amb, series: [series({ scope: amb, points: [{ x: "2024-01-01", y: 1 }] })] })} />);
    expect(screen.getByText("Two wellbores share label A-1")).toBeInTheDocument();
    await ready();
  });

  it("falls back to the table when the renderer cannot start", async () => {
    h.failNext = true;
    render(<ChartBlock spec={chart()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/renderer could not be loaded/);
    expect(screen.getByRole("button", { name: "Show data table" })).toBeInTheDocument();
  });
});

describe("evidence links (openSource)", () => {
  const link = () => screen.getByRole("button", { name: /Open source for Oil rate/ });

  it("dispatches openSource with document and page and reports 'opened'", async () => {
    const bus = createExploreCommandBus();
    const open = vi.fn(() => true);
    bus.subscribe({ openSource: open });
    const user = userEvent.setup();
    render(<ChartBlock spec={chart()} commandBus={bus} />);
    await ready();
    await user.click(link());
    expect(open).toHaveBeenCalledWith(expect.objectContaining({ source: { documentId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", page: 3, locator: undefined } }));
    expect(screen.getAllByText("Source opened.").length).toBeGreaterThan(0);
  });

  it("states no-subscriber explicitly", async () => {
    const user = userEvent.setup();
    render(
      <ExploreCommandsProvider bus={createExploreCommandBus()}>
        <ChartBlock spec={chart()} />
      </ExploreCommandsProvider>,
    );
    await ready();
    await user.click(link());
    expect(screen.getAllByText(/source viewer is not available/).length).toBeGreaterThan(0);
  });

  it("states unhandled (document/page not found) and a missing bus", async () => {
    const bus = createExploreCommandBus();
    bus.subscribe({ openSource: () => false });
    const user = userEvent.setup();
    const { unmount } = render(<ChartBlock spec={chart()} commandBus={bus} />);
    await ready();
    await user.click(link());
    expect(screen.getAllByText(/could not find that document or page/).length).toBeGreaterThan(0);
    unmount();
    render(<ChartBlock spec={chart()} commandBus={null} />);
    await waitFor(() => expect(h.instances).toHaveLength(2));
    await user.click(link());
    expect(screen.getAllByText(/source viewer is not available/).length).toBeGreaterThan(0);
  });
});

describe("linked time cursor", () => {
  const wrap = (store: ReturnType<typeof createChartCursorStore>, children: ReactNode) => <ChartCursorProvider store={store}>{children}</ChartCursorProvider>;

  it("publishes the zoomed window and the peer chart follows without echoing", async () => {
    const store = createChartCursorStore();
    const user = userEvent.setup();
    render(wrap(store, <><ChartBlock spec={chart({ chart_id: "a" })} /><ChartBlock spec={chart({ chart_id: "b", title: "Other" })} /></>));
    await waitFor(() => expect(h.instances).toHaveLength(2));
    const [a, b] = h.instances as [Fake, Fake];
    await user.click(screen.getAllByRole("button", { name: "Zoom in" })[0]!);
    expect(a.dispatchAction).toHaveBeenCalledWith({ type: "dataZoom", dataZoomIndex: 0, start: 25, end: 75 });
    // ECharts reports the zoom; the block turns percent into a window on the data extent.
    act(() => a.handlers.datazoom!({ batch: [{ start: 25, end: 75 }] }));
    const w = store.get()!;
    expect(w.axis).toBe("time");
    expect(w.from).toBeCloseTo(Date.parse("2024-01-01") + 0.25 * (Date.parse("2024-03-01") - Date.parse("2024-01-01")), 0);
    expect(b.dispatchAction).toHaveBeenCalledWith({ type: "dataZoom", dataZoomIndex: 0, start: 25, end: 75 }, { silent: true });
    expect(screen.getAllByText(/Selected 2024-01-1\d to 2024-02-\d\d/).length).toBe(2);
    // reset clears the window for everyone
    act(() => a.handlers.datazoom!({ start: 0, end: 100 }));
    expect(store.get()).toBeNull();
  });
});
