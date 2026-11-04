import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExploreStageProvider } from "../src/app/shell/exploreStage";
import { ChartPanel } from "../src/features/charts/ChartPanel";
import { chart, emptyChart, fieldScope, fieldSet, OTHER_WB, PROJECT, series, WB, wellboreSet, wellScope, boreScope } from "./fixtures/charts";
import { render } from "./render";

vi.mock("../src/features/charts/echartsRuntime", () => ({
  init: vi.fn(() => ({ setOption: vi.fn(), on: vi.fn(), off: vi.fn(), dispatchAction: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}));

interface Pending {
  url: string;
  signal: AbortSignal;
  resolve: (body: unknown, status?: number) => void;
}
let pending: Pending[] = [];

beforeEach(() => {
  pending = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        const signal = init!.signal!;
        signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        pending.push({
          url,
          signal,
          resolve: (body, status = 200) => resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })),
        });
      }),
    ),
  );
});
afterEach(() => vi.unstubAllGlobals());

const wbCtx = (id: string) => ({ kind: "wellbore" as const, wellboreId: id });

describe("wellbore chart set (XC-1/2)", () => {
  it("requests only the selected wellbore and draws its wellbore- and well-level charts", async () => {
    render(<ChartPanel projectId={PROJECT} context={wbCtx(WB)} asOf="2024-03-31" />);
    expect(screen.getByText("Loading wellbore charts…")).toBeInTheDocument();
    expect(pending[0]!.url).toBe(`/api/v1/projects/${PROJECT}/wellbores/${WB}/charts?as_of=2024-03-31`);
    pending[0]!.resolve(
      wellboreSet(
        [
          chart(),
          chart({ chart_id: "whp", key: "on_stream_hours", title: "On-stream hours", scope: wellScope(), series: [series({ scope: wellScope(), points: [{ x: "2024-01-01", y: 1 }] })] }),
          emptyChart("pressure_tests"),
        ],
        { as_of: "2024-03-31", ambiguities: ["Series 'WHP' matches wellbores A-1 and A-1T2"] },
      ),
    );
    expect(await screen.findByRole("heading", { name: "Wellbore charts: A-1 · Well A" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Production rates" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "On-stream hours" })).toBeInTheDocument();
    expect(screen.getAllByText("Well-level").length).toBeGreaterThan(0);
    expect(screen.getByText("No records in project")).toBeInTheDocument();
    expect(screen.getByText(/matches wellbores A-1 and A-1T2/)).toBeInTheDocument();
  });

  it("never draws another wellbore's chart or a field chart in a wellbore view", async () => {
    render(<ChartPanel projectId={PROJECT} context={wbCtx(WB)} />);
    pending[0]!.resolve(
      wellboreSet([
        chart(),
        chart({ chart_id: "leak", title: "Leaked bore", scope: boreScope(OTHER_WB) }),
        chart({ chart_id: "fld", title: "Field totals", scope: fieldScope() }),
      ]),
    );
    expect(await screen.findByRole("heading", { name: "Production rates" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Leaked bore" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Field totals" })).not.toBeInTheDocument();
    expect(screen.getByText(/not drawn: Leaked bore, Field totals/)).toBeInTheDocument();
  });

  it("uses the Explore stage context when none is passed", async () => {
    render(
      <ExploreStageProvider value={{ mode: "charts", context: wbCtx(OTHER_WB) }}>
        <ChartPanel projectId={PROJECT} />
      </ExploreStageProvider>,
    );
    expect(pending[0]!.url).toContain(`/wellbores/${OTHER_WB}/charts`);
  });
});

describe("field chart set (XC-3)", () => {
  it("renders the global set with the reconciliation note and excluded series", async () => {
    render(<ChartPanel projectId={PROJECT} context={{ kind: "field" }} from="2020-01-01" to="2024-01-01" />);
    expect(pending[0]!.url).toBe(`/api/v1/projects/${PROJECT}/charts/field?from=2020-01-01&to=2024-01-01`);
    pending[0]!.resolve(
      fieldSet(
        [
          chart({ chart_id: "tot", key: "field_rates_total", title: "Field rate totals", scope: fieldScope(), series: [series({ scope: fieldScope(), points: [{ x: "2024-01-01", y: 3 }] })] }),
          chart({ chart_id: "wb", title: "Single wellbore chart", scope: boreScope() }),
        ],
        {
          reconciliation_note: "Unreconciled until a published model associates series",
          excluded_series: [{ name: "Water injection (Sm3/h)", source_series_id: null, reason: "different unit and meaning from producer volumes" }],
        },
      ),
    );
    expect(await screen.findByRole("heading", { name: "Field rate totals" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Field charts" })).toBeInTheDocument();
    expect(screen.getByText(/Unreconciled until a published model/)).toBeInTheDocument();
    expect(screen.getByText(/Water injection \(Sm3\/h\): different unit/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Single wellbore chart" })).not.toBeInTheDocument();
  });

  it("defaults to the field view outside an Explore stage", () => {
    render(<ChartPanel projectId={PROJECT} />);
    expect(pending[0]!.url).toContain("/charts/field");
  });
});

describe("context races and failures (XC-5)", () => {
  it("aborts the stale request and never paints an out-of-order answer under the new label", async () => {
    const { rerender } = render(<ChartPanel projectId={PROJECT} context={wbCtx(WB)} />);
    rerender(<ChartPanel projectId={PROJECT} context={wbCtx(OTHER_WB)} />);
    expect(pending).toHaveLength(2);
    expect(pending[0]!.signal.aborted).toBe(true);
    // B answers first, then the stale A answer arrives late.
    pending[1]!.resolve(wellboreSet([chart({ chart_id: "b", title: "Bore B chart", scope: boreScope(OTHER_WB) })], { wellbore_id: OTHER_WB, wellbore_label: "B-2" }));
    expect(await screen.findByRole("heading", { name: "Wellbore charts: B-2 · Well A" })).toBeInTheDocument();
    pending[0]!.resolve(wellboreSet([chart({ title: "Bore A chart" })]));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("heading", { name: "Bore A chart" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Bore B chart" })).toBeInTheDocument();
  });

  it("shows loading, not the previous wellbore's charts, while the next one loads", async () => {
    const { rerender } = render(<ChartPanel projectId={PROJECT} context={wbCtx(WB)} />);
    pending[0]!.resolve(wellboreSet([chart()]));
    await screen.findByRole("heading", { name: "Production rates" });
    rerender(<ChartPanel projectId={PROJECT} context={wbCtx(OTHER_WB)} />);
    expect(screen.queryByRole("heading", { name: "Production rates" })).not.toBeInTheDocument();
    expect(screen.getByText("Loading wellbore charts…")).toBeInTheDocument();
  });

  it("changing the as-of date aborts and refetches", () => {
    const { rerender } = render(<ChartPanel projectId={PROJECT} context={wbCtx(WB)} asOf="2024-01-01" />);
    rerender(<ChartPanel projectId={PROJECT} context={wbCtx(WB)} asOf="2024-02-01" />);
    expect(pending[0]!.signal.aborted).toBe(true);
    expect(pending[1]!.url).toContain("as_of=2024-02-01");
  });

  it("rejects a response for another wellbore or as-of date", async () => {
    render(<ChartPanel projectId={PROJECT} context={wbCtx(WB)} asOf="2024-03-31" />);
    pending[0]!.resolve(wellboreSet([chart()], { wellbore_id: OTHER_WB, as_of: "2024-03-31" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/different project or wellbore/);
    expect(screen.queryByRole("heading", { name: "Production rates" })).not.toBeInTheDocument();
  });

  it("rejects a response for another as-of date", async () => {
    render(<ChartPanel projectId={PROJECT} context={wbCtx(WB)} asOf="2024-03-31" />);
    pending[0]!.resolve(wellboreSet([chart()], { as_of: "2023-01-01" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not the selected as-of date 2024-03-31/);
  });

  it("shows the API error with its request id and retries", async () => {
    const user = userEvent.setup();
    render(<ChartPanel projectId={PROJECT} context={wbCtx(WB)} />);
    pending[0]!.resolve({ error: { code: "service_unavailable", message: "storage is unavailable; try again", request_id: "req-1" } }, 503);
    expect(await screen.findByText(/Charts could not be loaded: storage is unavailable/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(pending).toHaveLength(2));
    pending[1]!.resolve(wellboreSet([chart()]));
    expect(await screen.findByRole("heading", { name: "Production rates" })).toBeInTheDocument();
  });
});
