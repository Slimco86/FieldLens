// Behavior tests for the source-inspection evidence panel with a stubbed fetch: detected profile,
// parse status, coverage, locators, findings, and loading/error/empty states. Parser correctness
// is proven by the backend tests, not here.
import { cleanup, screen, within } from "@testing-library/react";
import { render } from "./render";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EvidencePanel, describeLocator } from "../src/features/uploads/EvidencePanel";
import type { SourceDocumentItem } from "../src/features/uploads/api";

const P = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const R = "11111111-1111-4111-8111-111111111111";
const D = "d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1";
const doc = { document_id: D, original_filename: "prod.xlsx" } as unknown as SourceDocumentItem;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function report(over: Record<string, unknown> = {}) {
  return {
    project_id: P,
    document_id: D,
    source_revision_id: R,
    run_id: "r1",
    status: "partial",
    profile_name: "production_workbook_volve",
    profile_version: "1.0.0",
    method: "native xlsx",
    content_sha256: "a".repeat(64),
    stale: false,
    attempt_no: 1,
    coverage: { status: "partial", unit: "record", inspected: 9, total: 10, missing_ranges: ["row 10"], reasons: [] },
    record_counts: { production_day: 9 },
    wellbores: ["F-12"],
    issues: [
      {
        issue_id: "i1",
        code: "MISSING_UNIT",
        severity: "warning",
        message: "Daily sheet states no unit.",
        blocked_operations: ["calculation"],
        evidence_links: [],
      },
    ],
    error: null,
    detail: {},
    ...over,
  };
}
const records = (items: unknown[], total = items.length) => ({ items, page: { limit: 25, next_cursor: null }, total });
const record = {
  record_id: "rec1",
  ordinal: 0,
  kind: "production_day",
  subject: { wellbore_label: "NO 15/9-F-12 H" },
  effective_time: { literal: "2009-07-06", precision: "day" },
  validation_state: "unreviewed",
  attributes: [
    {
      key: "production_day.bore_oil_vol",
      original_text: "100.5",
      number: 100.5,
      text: null,
      unit: null,
      unit_status: "missing",
      reference: null,
      unknown_reason: null,
      validation_state: "unreviewed",
      evidence: { locator: { kind: "xlsx", sheet: "Daily Production Data", cell_range: "F2" } },
    },
    {
      key: "production_day.bore_gas_vol",
      original_text: "NULL",
      number: null,
      text: null,
      unit: null,
      unit_status: "missing",
      reference: null,
      unknown_reason: "NULL in source",
      validation_state: "unreviewed",
      evidence: { locator: { kind: "xlsx", sheet: "Daily Production Data", cell_range: "G2" } },
    },
  ],
};

function install(handler: (url: string, init?: RequestInit) => Response | undefined) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/session") return Promise.resolve(json({ csrf_token: "t".repeat(43) }));
      const out = handler(url, init);
      if (out === undefined) throw new Error(`unexpected request ${url}`);
      return Promise.resolve(out);
    }),
  );
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function open() {
  render(<EvidencePanel projectId={P} doc={doc} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /Inspect extraction for prod\.xlsx/ }));
  return user;
}

describe("records catching up with the report", () => {
  it("re-reads the list while it is shorter than the report says, and says so meanwhile", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let reads = 0;
      install((u) =>
        u.endsWith("/extraction")
          ? json(report({ record_counts: { production_day: 1 } }))
          : u.includes("/extraction/records")
            ? (reads++, json(reads === 1 ? records([]) : records([record])))
            : undefined,
      );
      render(<EvidencePanel projectId={P} doc={doc} />);
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      await user.click(screen.getByRole("button", { name: /Inspect extraction for prod\.xlsx/ }));
      expect(await screen.findByText(/The report lists 1 records but none are readable yet/)).toBeInTheDocument();
      await vi.advanceTimersByTimeAsync(2500);
      expect(await screen.findByRole("list", { name: /Extracted records for prod\.xlsx/ })).toBeInTheDocument();
      expect(screen.queryByText(/none are readable yet/)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("evidence panel", () => {
  it("lists wellbore labels separately from the well and shows coverage gaps", async () => {
    install((u) =>
      u.endsWith("/extraction")
        ? json(
            report({
              wellbore_identities: [
                { wellbore_label: "NO 15/9-F-12 H", well_key: "15/9-F-12", record_kinds: ["production_day"] },
                { wellbore_label: "F-12 A", well_key: "15/9-F-12", record_kinds: ["trajectory_station"] },
              ],
              coverage_notes: ["F-12: completion string, packers and tubing are not extracted (deferred completion PDFs)."],
            }),
          )
        : json(records([])),
    );
    await open();
    const ids = await screen.findByRole("list", { name: "Wellbores in this source" });
    expect(within(ids).getByText(/Wellbore NO 15\/9-F-12 H \(well 15\/9-F-12\)/)).toBeInTheDocument();
    expect(within(ids).getByText(/Wellbore F-12 A \(well 15\/9-F-12\)/)).toBeInTheDocument();
    const notes = screen.getByRole("list", { name: "Coverage notes" });
    expect(within(notes).getByText(/not extracted \(deferred completion PDFs\)/)).toBeInTheDocument();
  });

  it("shows profile, honest partial status, coverage, findings, records and locators", async () => {
    install((u) =>
      u.endsWith("/extraction") ? json(report()) : u.includes("/extraction/records") ? json(records([record])) : undefined,
    );
    await open();
    expect(await screen.findByText(/Partial \(not all content was extracted\)/)).toBeInTheDocument();
    expect(screen.getByText(/production_workbook_volve v1\.0\.0 \(native xlsx\)/)).toBeInTheDocument();
    expect(screen.getByText(/9 of 10 record inspected \(partial\); missing row 10/)).toBeInTheDocument();
    const findings = screen.getByRole("list", { name: "Data-quality findings" });
    expect(within(findings).getByText(/MISSING_UNIT/)).toBeInTheDocument();
    expect(within(findings).getByText(/blocks: calculation/)).toBeInTheDocument();
    const recs = await screen.findByRole("list", { name: /Extracted records for prod\.xlsx/ });
    expect(within(recs).getByText(/xlsx Daily Production Data!F2/)).toBeInTheDocument();
    expect(within(recs).getByText(/100\.5 unit not stated/)).toBeInTheDocument();
    // NULL is shown as unknown with its reason, never as zero.
    expect(within(recs).getByText(/unknown \(NULL in source\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Inspect|Hide extraction/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("states loading, then an error with retry", async () => {
    let calls = 0;
    install((u) =>
      u.endsWith("/extraction")
        ? (calls++, calls === 1 ? json({ error: { code: "SERVICE_UNAVAILABLE", message: "storage is unavailable", request_id: "req-9" } }, 503) : json(report({ status: "succeeded", issues: [] })))
        : u.includes("/extraction/records")
          ? json(records([]))
          : undefined,
    );
    const user = await open();
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded: storage is unavailable/);
    expect(screen.getByText(/Request ID: req-9/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry loading extraction report" }));
    expect(await screen.findByText(/^Succeeded$/)).toBeInTheDocument();
    expect(screen.getByText(/No data-quality findings were recorded/)).toBeInTheDocument();
    expect(await screen.findByText(/No records were extracted from this file/)).toBeInTheDocument();
  });

  it("shows a loading status while the report is pending", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        String(input) === "/api/v1/session"
          ? Promise.resolve(json({ csrf_token: "t".repeat(43) }))
          : new Promise<Response>(() => undefined),
      ),
    );
    await open();
    expect(screen.getByRole("status")).toHaveTextContent(/Loading extraction report/);
  });

  it("explains a file with no run yet and an unsupported file without claiming success", async () => {
    install((u) => (u.endsWith("/extraction") ? json(report({ status: null, run_id: null, issues: [], coverage: null })) : undefined));
    await open();
    expect(await screen.findByText(/no extraction run is recorded|Storage verification has not finished/)).toBeInTheDocument();
    cleanup();
    install((u) =>
      u.endsWith("/extraction")
        ? json(report({ status: "unsupported", profile_name: null, profile_version: null, method: null, coverage: null, record_counts: {} }))
        : u.includes("/extraction/records")
          ? json(records([]))
          : undefined,
    );
    await open();
    expect(await screen.findByText(/Unsupported \(no profile matches the content\)/)).toBeInTheDocument();
    expect(screen.getByText(/none matched the file content/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-run extraction" })).toBeInTheDocument();
  });

  it("flags a stale profile and offers a re-run", async () => {
    install((u) =>
      u.endsWith("/extraction") ? json(report({ status: "succeeded", stale: true, coverage: null })) : json(records([])),
    );
    await open();
    expect(await screen.findByText(/results are stale/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-run extraction" })).toBeInTheDocument();
  });
});

describe("describeLocator", () => {
  it("renders each locator kind", () => {
    const mk = (locator: object) => ({ locator }) as never;
    expect(describeLocator(mk({ kind: "xml", element_path: "/a/b[1]" }))).toBe("xml /a/b[1]");
    expect(describeLocator(mk({ kind: "pdf", page: 3, cell_id: "r2c4" }))).toBe("pdf page 3 cell r2c4");
    expect(describeLocator(mk({ kind: "text", las_section: "curve", line_start: 12, line_end: 12, column_name: "GR" }))).toBe(
      "text section curve, line 12, column GR",
    );
  });
});

describe("run-less documents (AC-8)", () => {
  const stored = { ...doc, storage_state: "stored" } as unknown as SourceDocumentItem;
  const runless = report({ status: null, run_id: null });

  it("offers Start extraction for a Stored document with no run and reports the outcome", async () => {
    let posts = 0;
    install((u, init) => {
      if (u.includes("/extraction?retry=true") && init?.method === "POST") {
        posts++;
        return json({ outcome: "queued", report: runless });
      }
      if (u.endsWith("/extraction")) return json(runless);
    });
    render(<EvidencePanel projectId={P} doc={stored} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Inspect extraction for prod\.xlsx/ }));
    expect(await screen.findByText(/no extraction run is recorded/)).toBeInTheDocument();
    expect(screen.queryByText(/waiting for the extraction worker/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start extraction" }));
    expect(await screen.findByText("Extraction was queued.")).toBeInTheDocument();
    expect(posts).toBe(1);
  });

  it("gives a precise reason, not a start action, for a Failed document", async () => {
    install((u) => (u.endsWith("/extraction") ? json(runless) : undefined));
    render(<EvidencePanel projectId={P} doc={{ ...doc, storage_state: "failed" } as unknown as SourceDocumentItem} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Inspect extraction for prod\.xlsx/ }));
    expect(await screen.findByText(/Storage failed for this file/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start extraction" })).not.toBeInTheDocument();
  });

  it("shows the writing process of an extraction error", async () => {
    install((u) =>
      u.endsWith("/extraction")
        ? json(report({ status: "failed", error: { code: "source_missing", message: "source file missing", process: "host=a pid=1 lane=x root=y" } }))
        : u.includes("/extraction/records")
          ? json(records([]))
          : undefined,
    );
    render(<EvidencePanel projectId={P} doc={stored} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Inspect extraction for prod\.xlsx/ }));
    expect(await screen.findByText(/Written by process: host=a pid=1 lane=x root=y/)).toBeInTheDocument();
  });
});
