// Interaction tests for the project Overview (UI-13) with a stubbed fetch: every shown count is
// reproduced exactly from fixture API fields, failures stay local to their section, and answers
// for another project are never rendered. Real-lane evidence is a separate Playwright/QA step.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "./render";
import { ProjectOverview } from "../src/features/overview/ProjectOverview";

const P = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const Q = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const R = "11111111-1111-4111-8111-111111111111";
const D = (n: number) => `d${n}d${n}d${n}d${n}-d${n}d${n}-4d${n}d-8d${n}d-d${n}d${n}d${n}d${n}d${n}d${n}d${n}`;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function doc(n: number, over: Record<string, unknown>) {
  return {
    document_id: D(n),
    project_id: P,
    source_revision_id: R,
    original_filename: `file${n}`,
    format_family: "csv",
    storage_state: "stored",
    extraction_state: "extracted",
    ...over,
  };
}
const DOCS = [
  doc(1, { original_filename: "traj.csv", format_family: "csv" }),
  doc(2, { original_filename: "logs.las", format_family: "las", extraction_state: "extracted_with_issues" }),
  doc(3, { original_filename: "scan.pdf", format_family: "pdf", extraction_state: "pending_extraction" }),
  doc(4, { original_filename: "bad.xlsx", format_family: "xlsx", storage_state: "quarantined", extraction_state: "pending_extraction" }),
];

const report = (n: number, over: Record<string, unknown>) => ({
  project_id: P,
  source_revision_id: R,
  document_id: D(n),
  record_counts: {},
  issues: [],
  coverage: null,
  ...over,
});
const REPORTS: Record<string, unknown> = {
  [D(1)]: report(1, { record_counts: { trajectory_station: 120 }, coverage: { status: "complete", inspected: 120, total: 120, unit: "record" } }),
  [D(2)]: report(2, {
    record_counts: { well_log_curve: 7, trajectory_station: 5 },
    coverage: { status: "partial", inspected: 1, total: 2, unit: "page" },
    issues: [
      {
        issue_id: "i1",
        severity: "warning",
        code: "MISSING_UNIT",
        message: "Curve DEPT has no unit",
        evidence_links: [{ locator: { kind: "text", las_section: "~C", line_start: 12, line_end: 12 } }],
      },
      { issue_id: "i2", severity: "error", code: "EXTRACTION_PARTIAL", message: "Page 3 unreadable", evidence_links: [] },
    ],
  }),
};

const IDENTITY = {
  project_id: P,
  resolved_current: false,
  linked_record_count: 132,
  unresolved_record_count: 4,
  unresolved: [{ reason: "ambiguous", record_count: 4, document_count: 1, detail: "", labels: ["F-11"] }],
  wells: [
    {
      well_id: "w1",
      name: "15/9-F-11",
      document_count: 2,
      record_count: 132,
      wellbores: [
        {
          wellbore_id: "b1",
          well_id: "w1",
          name: "15/9-F-11 B",
          document_count: 2,
          record_count: 132,
          record_counts: [{ kind: "trajectory_station", records: 125 }],
        },
      ],
    },
  ],
};

const SERIES = {
  items: [
    {
      series_id: "s1",
      project_id: P,
      document_id: D(2),
      kind: "log",
      measure: "GR",
      unit: null,
      unit_status: "missing",
      wellbore_label: "15/9-F-11 B",
      well_name: null,
      min_value: 10.5,
      max_value: 99,
      valid_count: 1000,
      sample_count: 1200,
      index: { name: "DEPT", unit: "m", unit_status: "stated", first: 1500, last: 2600, first_date: null, last_date: null },
    },
  ],
  total: 1,
  limit: 500,
  offset: 0,
  next_offset: null,
};

type Routes = Record<string, () => Response | Promise<Response>>;
function install(routes: Partial<Routes> = {}, project = P) {
  const calls: string[] = [];
  const base: Routes = {
    documents: () => json({ items: DOCS, page: { limit: 50, next_cursor: null } }),
    identity: () => json(IDENTITY),
    series: () => json(SERIES),
    extraction: () => json({}),
  };
  const fn = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    const m = /\/documents\/(d\dd\dd\dd\d-[^/]+)\/extraction$/.exec(url);
    if (m !== null) {
      const r = REPORTS[m[1] as string];
      return Promise.resolve((routes.extraction ?? (() => (r === undefined ? json({}, 404) : json(r))))());
    }
    for (const key of ["documents", "identity", "series"] as const) {
      if (url.startsWith(`/api/v1/projects/${project}/${key}`)) return Promise.resolve((routes[key] ?? base[key]!)());
    }
    throw new Error(`unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const list = (name: string) => screen.findByRole("list", { name });

describe("project Overview", () => {
  it("reproduces API counts exactly and states unit gaps and what is not available", async () => {
    install();
    render(<ProjectOverview projectId={P} revisionId={R} />);

    const states = await list("Documents by processing state");
    const texts = (el: HTMLElement) => within(el).getAllByRole("listitem").map((li) => li.textContent?.trim());
    expect(texts(states)).toEqual(["2 Waiting for extraction", "1 Extracted", "1 Extracted with findings"]);
    expect(texts(await list("Documents by storage state"))).toEqual(["3 Stored", "1 Quarantined"]);
    expect(within(await list("Documents by detected format")).getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getByText("documents", { exact: false, selector: "p" })).toHaveTextContent("4 documents");

    const coverage = await screen.findByRole("region", { name: "Extraction coverage per record kind table" });
    const traj = within(coverage).getByRole("row", { name: /trajectory_station/ });
    expect(within(traj).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "trajectory_station",
      "125",
      "2",
      "1 complete, 1 partial, 0 unknown",
    ]);

    const counts = await screen.findByRole("group", { name: "Issue counts by severity" });
    expect(counts).toHaveTextContent("Error: 1");
    expect(counts).toHaveTextContent("Warning: 1");
    const issues = await list("First 10 issues, most severe first");
    const items = within(issues).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Page 3 unreadable");
    expect(items[0]).toHaveTextContent("no source location cited");
    expect(items[1]).toHaveTextContent("logs.las, text section ~C, line 12");

    const wells = await screen.findByRole("region", { name: "Resolved wells and wellbores table" });
    expect(within(wells).getByRole("row", { name: /Wellbore 15\/9-F-11 B/ })).toHaveTextContent("trajectory_station 125");
    expect(screen.getByText(/out of date/)).toBeInTheDocument();
    expect(screen.getByText(/4 record\(s\) have no resolved well/)).toBeInTheDocument();

    const series = await screen.findByRole("region", { name: "Series for 15/9-F-11 B table" });
    const row = within(series).getByRole("row", { name: /GR/ });
    expect(row).toHaveTextContent("not stated");
    expect(row).toHaveTextContent("DEPT (m)");
    expect(row).toHaveTextContent("1500 to 2600");
    expect(row).toHaveTextContent("10.5 to 99");
    expect(row).toHaveTextContent("1,000 / 1,200");

    const warn = await list("Unit warnings");
    expect(within(warn).getByText(/GR: value unit not stated/)).toBeInTheDocument();
    expect(within(warn).getByText(/1 extraction issue\(s\) with code MISSING_UNIT/)).toBeInTheDocument();

    const notYet = screen.getByRole("list", { name: "Not available yet" });
    expect(within(notYet).getAllByRole("listitem")).toHaveLength(4);
    expect(notYet).toHaveTextContent("TASK-056");
  });

  it("shows a designed empty state and makes no data requests without a source revision", () => {
    const calls = install();
    render(<ProjectOverview projectId={P} revisionId={null} />);
    expect(screen.getByText("No data yet")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Not available yet" })).toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it("keeps a failed section local, shows its request id and retries only on request", async () => {
    let fail = true;
    const calls = install({
      identity: () =>
        fail
          ? json({ error: { code: "INTERNAL", message: "identity down", request_id: "req-42" } }, 500)
          : json(IDENTITY),
    });
    const user = userEvent.setup();
    render(<ProjectOverview projectId={P} revisionId={R} />);
    const alert = await screen.findByText(/Well identity could not be loaded: identity down/);
    expect(alert.closest('[role="alert"]')).toHaveTextContent("req-42");
    expect(await screen.findByRole("region", { name: "Series for 15/9-F-11 B table" })).toBeInTheDocument(); // other sections unaffected
    const before = calls.filter((u) => u.includes("/identity")).length;
    fail = false;
    await user.click(screen.getByRole("button", { name: "Retry loading well identity" }));
    expect(await screen.findByRole("region", { name: "Resolved wells and wellbores table" })).toBeInTheDocument();
    expect(calls.filter((u) => u.includes("/identity")).length).toBe(before + 1);
  });

  it("says when extraction reports could not be read instead of counting them as zero", async () => {
    install({ extraction: () => json({ error: { code: "X", message: "boom", request_id: "r" } }, 500) });
    render(<ProjectOverview projectId={P} revisionId={R} />);
    expect(await screen.findByText(/2 extraction report\(s\) could not be read/)).toBeInTheDocument();
    expect(screen.getByText("No extracted records")).toBeInTheDocument();
  });

  it("never renders an answer that belongs to another project", async () => {
    let release: (r: Response) => void = () => undefined;
    const late = new Promise<Response>((resolve) => (release = resolve));
    install({ documents: () => late });
    const view = render(<ProjectOverview projectId={P} revisionId={R} />);
    install({ documents: () => json({ items: [], page: { limit: 50, next_cursor: null } }) }, Q);
    view.rerender(<ProjectOverview projectId={Q} revisionId={R} />);
    expect(await screen.findByText("No documents in the latest revision")).toBeInTheDocument();
    release(json({ items: DOCS, page: { limit: 50, next_cursor: null } }));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("traj.csv")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Documents by processing state" })).not.toBeInTheDocument();
  });

  it("refreshes on demand and exposes scrollable tables to the keyboard", async () => {
    const calls = install();
    const user = userEvent.setup();
    render(<ProjectOverview projectId={P} revisionId={R} />);
    const region = await screen.findByRole("region", { name: "Resolved wells and wellbores table" });
    expect(region).toHaveAttribute("tabindex", "0");
    const before = calls.filter((u) => u.includes("/series")).length;
    await user.click(screen.getByRole("button", { name: "Refresh project data overview" }));
    await waitFor(() => expect(calls.filter((u) => u.includes("/series")).length).toBe(before + 1));
  });
});
