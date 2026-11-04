import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AnswerView, AssistantChartRendererProvider } from "../src/features/assistant/blocks";
import { appLinkToCommand } from "../src/features/assistant/links";
import { Markdown } from "../src/features/assistant/Markdown";
import { ExploreCommandsProvider } from "../src/features/scene/ExploreCommandsContext";
import { createExploreCommandBus, type ExploreCommandHandlers } from "../src/features/scene/exploreCommands";
import type { AppLink, Citation } from "../src/features/assistant/api";
import { answer, chartSpec } from "./fixtures/assistant";

const DOC = "00000000-0000-4000-8000-0000000000d1";
const link = (target: Record<string, unknown>, label = "Go"): AppLink => ({ label, target: target as unknown as AppLink["target"], tool_call_id: null });
const pdf = { kind: "pdf", document_id: DOC, page: 4, cell_id: null, rect: null } as never;

function setup(blocks: Parameters<typeof answer>[0], handlers: ExploreCommandHandlers = {}, extra: Parameters<typeof answer>[1] = {}) {
  const bus = createExploreCommandBus();
  bus.subscribe(handlers);
  return render(
    <ExploreCommandsProvider bus={bus}>
      <AnswerView answer={answer(blocks, extra)} />
    </ExploreCommandsProvider>,
  );
}

describe("assistant link dispatch (AV-4)", () => {
  it("maps each target kind to its command", () => {
    expect(appLinkToCommand(link({ kind: "source", document_id: DOC, page: 4, locator: pdf }))).toEqual({
      type: "openSource",
      source: { documentId: DOC, page: 4, locator: "pdf" },
    });
    expect(appLinkToCommand(link({ kind: "wellbore", wellbore_id: "w" }))).toEqual({ type: "focusWellbore", wellboreId: "w" });
    expect(appLinkToCommand(link({ kind: "element", element_id: "e", wellbore_id: "w" }))).toEqual({ type: "focusElement", wellboreId: "w", elementId: "e" });
    expect(appLinkToCommand(link({ kind: "formation", surface_key: "s", pick_id: null, wellbore_id: "w" }))).toEqual({ type: "focusFormation", wellboreId: "w", formationId: "s" });
    expect(appLinkToCommand(link({ kind: "chart", chart_key: "production_rates", wellbore_id: null }))).toEqual({ type: "openChart", kind: "production_rates", wellboreId: null });
    expect(appLinkToCommand(link({ kind: "element", element_id: "e", wellbore_id: null }))).toBeNull();
  });

  it("dispatches the matching command and reports handled silently", async () => {
    const focusWellbore = vi.fn(() => true);
    setup([{ kind: "link", link: link({ kind: "wellbore", wellbore_id: "w9" }, "Wellbore W9") }], { focusWellbore });
    await userEvent.click(screen.getByRole("button", { name: "Wellbore W9" }));
    expect(focusWellbore).toHaveBeenCalledWith(expect.objectContaining({ wellboreId: "w9" }));
    expect(screen.getByRole("status")).toHaveTextContent("Opened.");
  });

  it("says so when nobody listens, when the target is stale, and when the link lacks a target", async () => {
    setup([
      { kind: "link", link: link({ kind: "wellbore", wellbore_id: "w9" }, "A") },
      { kind: "link", link: link({ kind: "chart", chart_key: "log_tracks", wellbore_id: "w1" }, "B") },
      { kind: "link", link: link({ kind: "element", element_id: "e", wellbore_id: null }, "C") },
    ], { openChart: () => false });
    await userEvent.click(screen.getByRole("button", { name: "A" }));
    expect(screen.getByRole("status")).toHaveTextContent(/nothing is listening/i);
    await userEvent.click(screen.getByRole("button", { name: "B" }));
    expect(screen.getByRole("status")).toHaveTextContent(/stale|not be found/i);
    await userEvent.click(screen.getByRole("button", { name: "C" }));
    expect(screen.getByRole("status")).toHaveTextContent(/missing or no longer available/i);
  });

  it("citation chips open the source; draft chips are labeled; evidence-less chips are disabled", async () => {
    const openSource = vi.fn(() => true);
    const citations: Citation[] = [
      { marker: "[1]", label: "Report", draft: true, claim_id: null, evidence: { document_id: DOC, locator: pdf, record_id: null, source_revision_id: null } } as unknown as Citation,
      { marker: "[2]", label: null, draft: false, claim_id: null, evidence: null } as unknown as Citation,
    ];
    setup([{ kind: "text", text: "x [1]" }], { openSource }, { citations });
    const chip = screen.getByRole("button", { name: /\[1\] Report/ });
    expect(chip).toHaveTextContent(/Draft, unpublished/);
    expect(screen.getByText(/Includes draft, unpublished context/)).toBeInTheDocument();
    await userEvent.click(chip);
    expect(openSource).toHaveBeenCalledWith(expect.objectContaining({ source: { documentId: DOC, page: 4, locator: "pdf" } }));
    expect(screen.getByRole("button", { name: /\[2\]/ })).toBeDisabled();
  });
});

describe("answer blocks", () => {
  it("renders value, unknown value and gap blocks explicitly", () => {
    setup([
      { kind: "value", label: "Oil rate", value: 12.5, unit: "sm3/d", reference: "MD", tool_call_id: DOC, result_path: "/a", unknown_reason: null, citation_markers: ["[1]"] },
      { kind: "value", label: "GOR", value: null, unit: null, reference: null, tool_call_id: DOC, result_path: "/b", unknown_reason: "unit missing" },
      { kind: "gap", reason: "no_data", text: "No pressure records." },
    ]);
    expect(screen.getByText("12.5")).toBeInTheDocument();
    expect(screen.getByText(/Unknown: unit missing/)).toBeInTheDocument();
    expect(screen.getByText(/Data not available \(No data\)/)).toBeInTheDocument();
    expect(screen.getByText(/No pressure records/)).toBeInTheDocument();
  });

  it("flags unverified answers, unverified numbers and dropped blocks", () => {
    setup([{ kind: "text", text: "t", unverified_numbers: ["42"] }], {}, { verification: "unverified", dropped_blocks: [{ index: 1, kind: "chart", detail: null } as never] });
    expect(screen.getByText(/Not verified against sources/)).toBeInTheDocument();
    expect(screen.getByText(/Unverified numbers: 42/)).toBeInTheDocument();
    expect(screen.getByText(/1 block failed validation/)).toBeInTheDocument();
  });
});

describe("assistant chart block (AV-5)", () => {
  const chartBlock = (spec: ReturnType<typeof chartSpec> | null) =>
    [{ kind: "chart", request: {} as never, spec, open_in_charts: link({ kind: "chart", chart_key: "production_rates", wellbore_id: "w1" }) }] as Parameters<typeof answer>[0];

  it("uses the injected renderer, and opens the Charts tab via openChart", async () => {
    const openChart = vi.fn(() => true);
    const bus = createExploreCommandBus();
    bus.subscribe({ openChart });
    const spec = chartSpec();
    const renderChart = vi.fn(() => <div data-testid="real-chart" />);
    render(
      <ExploreCommandsProvider bus={bus}>
        <AssistantChartRendererProvider value={renderChart}>
          <AnswerView answer={answer(chartBlock(spec))} />
        </AssistantChartRendererProvider>
      </ExploreCommandsProvider>,
    );
    expect(screen.getByTestId("real-chart")).toBeInTheDocument();
    expect(renderChart).toHaveBeenCalledWith(spec);
    await userEvent.click(screen.getByRole("button", { name: "Open in Charts tab" }));
    expect(openChart).toHaveBeenCalledWith(expect.objectContaining({ kind: "production_rates", wellboreId: "w1" }));
  });

  it("falls back to a summary table with units and gaps; null spec shows unavailable, not a chart", () => {
    const { unmount } = setup(chartBlock(chartSpec()));
    expect(screen.getByRole("table", { name: /Oil rate: series summary/ })).toBeInTheDocument();
    expect(screen.getByText("sm3/d")).toBeInTheDocument();
    unmount();
    setup(chartBlock(null));
    expect(screen.getByText(/Chart not available/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("markdown-lite safety (XSS negative control)", () => {
  it("renders lists/bold/code but never raw HTML", () => {
    const { container } = render(
      <Markdown text={'Hello <img src=x onerror="window.__pwned=1"> **bold** `c`\n\n- one\n- <script>alert(1)</script>\n\n[x](javascript:alert(1))'} />,
    );
    expect(container.querySelector("img, script, a")).toBeNull();
    expect(container.querySelector("strong")).toHaveTextContent("bold");
    expect(container.querySelector("code")).toHaveTextContent("c");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.textContent).toContain("<script>alert(1)</script>");
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });
});
