import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChartBlock } from "../src/features/charts/ChartBlock";
import { ExploreCommandsProvider } from "../src/features/scene/ExploreCommandsContext";
import { createExploreCommandBus } from "../src/features/scene/exploreCommands";
import { useExploreEnrichment } from "../src/features/scene/exploreEnrichment";
import { chart, fieldScope, fieldSet, PROJECT, WB } from "./fixtures/charts";
import { render } from "./render";

vi.mock("../src/features/charts/echartsRuntime", () => ({
  init: vi.fn(() => ({ setOption: vi.fn(), on: vi.fn(), off: vi.fn(), dispatchAction: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}));
// The assistant is a boundary: expose the context it would send.
vi.mock("../src/features/assistant", () => ({
  AssistantPanel: (p: { context: unknown }) => <output data-testid="assistant-context">{JSON.stringify(p.context)}</output>,
}));
vi.mock("../src/features/context/formations/FormationPanel", () => ({ FormationPanel: () => null }));

let urls: string[] = [];
let chartStatus = 200;
beforeEach(() => {
  urls = [];
  chartStatus = 200;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      if (url.includes("/charts")) {
        const asOf = new URL(url, "http://x").searchParams.get("as_of");
        if (chartStatus === 422) return new Response(JSON.stringify({ detail: "as_of is outside the data" }), { status: 422, headers: { "content-type": "application/json" } });
        return new Response(JSON.stringify(fieldSet([chart({ scope: fieldScope() })], { as_of: asOf })), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response("{}", { status: 404, headers: { "content-type": "application/json" } });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function Host() {
  const e = useExploreEnrichment({ projectId: PROJECT, context: { kind: "field" }, revision: 1 });
  return (
    <>
      {e?.workspace.charts}
      {e?.workspace.assistant}
    </>
  );
}
const mount = () =>
  render(
    <ExploreCommandsProvider>
      <Host />
    </ExploreCommandsProvider>,
  );
const chartUrls = () => urls.filter((u) => u.includes("/charts"));

describe("as-of control (D3)", () => {
  it("is labelled, starts empty, and clearing is disabled until a date is set", async () => {
    mount();
    const input = await screen.findByLabelText("As of");
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("type", "date");
    expect(screen.getByRole("button", { name: "Clear as-of date (show latest)" })).toBeDisabled();
    await waitFor(() => expect(chartUrls()[0]).toBe(`/api/v1/projects/${PROJECT}/charts/field`));
  });

  it("sends the date as as_of to the charts request and the assistant context, and clears back to latest", async () => {
    const user = userEvent.setup();
    mount();
    const input = await screen.findByLabelText("As of");
    expect(JSON.parse(screen.getByTestId("assistant-context").textContent!)).toMatchObject({ as_of: null });
    fireEvent.change(input, { target: { value: "2024-03-31" } });
    await waitFor(() => expect(chartUrls().at(-1)).toBe(`/api/v1/projects/${PROJECT}/charts/field?as_of=2024-03-31`));
    expect(JSON.parse(screen.getByTestId("assistant-context").textContent!)).toMatchObject({ as_of: "2024-03-31" });
    expect(await screen.findByText("Showing the record as of 2024-03-31")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear as-of date (show latest)" }));
    await waitFor(() => expect(chartUrls().at(-1)).toBe(`/api/v1/projects/${PROJECT}/charts/field`));
    expect(JSON.parse(screen.getByTestId("assistant-context").textContent!)).toMatchObject({ as_of: null });
  });

  it("surfaces a server 422 as an alert", async () => {
    mount();
    const input = await screen.findByLabelText("As of");
    chartStatus = 422;
    fireEvent.change(input, { target: { value: "2099-01-01" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(/Charts could not be loaded/);
  });
});

describe("chart formation top -> Show in 3D (XC-7)", () => {
  const withTop = (pick: string | null = "pick-1", surface: string | null = "brent") =>
    chart({
      reference_lines: [{ axis_id: "y0", label: "Top Brent", value: 2100, unit: "m", pick_id: pick, surface_key: surface, evidence: [] }],
    });

  it("dispatches focusFormation for the wellbore with the pick id and announces handled", async () => {
    const bus = createExploreCommandBus();
    const spy = vi.spyOn(bus, "dispatch").mockReturnValue("handled");
    const user = userEvent.setup();
    render(<ChartBlock spec={withTop()} commandBus={bus} />);
    await user.click(screen.getByRole("button", { name: "Show Top Brent in 3D" }));
    expect(spy).toHaveBeenCalledWith({ type: "focusFormation", wellboreId: WB, formationId: "pick-1" });
    expect(screen.getAllByRole("status").some((s) => s.textContent === "Top Brent: Shown in 3D.")).toBe(true);
  });

  it("falls back to the surface key and says 'unhandled' explicitly when no viewer can act", async () => {
    const bus = createExploreCommandBus();
    const spy = vi.spyOn(bus, "dispatch").mockReturnValue("unhandled");
    const spec = withTop(null, "brent");
    const user = userEvent.setup();
    render(<ChartBlock spec={spec} commandBus={bus} />);
    await user.click(screen.getByRole("button", { name: "Show Top Brent in 3D" }));
    expect(spy).toHaveBeenCalledWith({ type: "focusFormation", wellboreId: WB, formationId: "brent" });
    expect(screen.getAllByText(/Could not show this formation in 3D/).length).toBeGreaterThan(0);
  });

  it("offers no action for reference lines without a formation reference, and no bus is reported", async () => {
    const spec = withTop(null, null);
    const { unmount } = render(<ChartBlock spec={spec} commandBus={null} />);
    expect(screen.queryByRole("button", { name: /Show .* in 3D/ })).toBeNull();
    unmount();
    const user = userEvent.setup();
    render(<ChartBlock spec={withTop()} commandBus={null} />);
    await user.click(screen.getByRole("button", { name: "Show Top Brent in 3D" }));
    expect(screen.getAllByText(/3D view is not available here/).length).toBeGreaterThan(0);
  });
});
