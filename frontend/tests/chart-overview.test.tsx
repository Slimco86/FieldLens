import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChartCard } from "../src/features/charts/ChartCard";
import { ChartBlock } from "../src/features/charts/ChartBlock";
import { chart, series } from "./fixtures/charts";
import { render } from "./render";

const h = vi.hoisted(() => ({ disposed: 0, created: 0 }));
vi.mock("../src/features/charts/echartsRuntime", () => ({
  init: vi.fn(() => {
    h.created += 1;
    return { setOption: vi.fn(), on: vi.fn(), off: vi.fn(), dispatchAction: vi.fn(), resize: vi.fn(), dispose: vi.fn(() => (h.disposed += 1)) };
  }),
}));

beforeEach(() => {
  h.disposed = 0;
  h.created = 0;
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
});

const noted = () => chart({ notes: ["Rates are allocated"], excluded_series: [{ name: "Gas", reason: "unit mismatch", source_series_id: null }] });

describe("chart overview card and full view (UX-5)", () => {
  it("overview hides toolbar, data table and sources but flags notes and exclusions", async () => {
    render(<ChartBlock spec={noted()} variant="overview" />);
    expect(await screen.findByRole("heading", { name: "Production rates" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zoom in" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show data table" })).not.toBeInTheDocument();
    expect(screen.queryByText(/^Sources/)).not.toBeInTheDocument();
    expect(screen.queryByText("Rates are allocated")).not.toBeInTheDocument();
    expect(screen.getByTestId("status-production_rates")).toHaveTextContent(/1 series · .* gaps · 1 excluded/);
    expect(screen.getByLabelText(/2 notes, exclusions or caveats/)).toBeInTheDocument();
  });

  it("expand opens a labelled dialog with the full detail, Escape closes and focus returns", async () => {
    const user = userEvent.setup();
    render(<ChartCard spec={noted()} />);
    const expand = screen.getByRole("button", { name: "Expand chart: Production rates" });
    expect(expand).toHaveAttribute("aria-haspopup", "dialog");
    await user.click(expand);
    const dlg = await screen.findByRole("dialog", { name: "Production rates" });
    expect(within(dlg).getByRole("button", { name: "Zoom in" })).toBeInTheDocument();
    expect(within(dlg).getByRole("button", { name: "Show data table" })).toBeInTheDocument();
    expect(within(dlg).getByText("Rates are allocated")).toBeInTheDocument();
    await waitFor(() => expect(h.created).toBe(2));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(expand).toHaveFocus();
    expect(h.disposed).toBe(1);
  });

  it("close button closes the dialog", async () => {
    const user = userEvent.setup();
    render(<ChartCard spec={chart({ series: [series({ points: [{ x: "2024-01-01", y: 1 }] })] })} />);
    await user.click(screen.getByRole("button", { name: /Expand chart/ }));
    await user.click(await screen.findByRole("button", { name: /Close chart/ }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
