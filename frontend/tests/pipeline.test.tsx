// Interaction tests for the Reconstruction tab (UI-16, TASK-063; processing flow from UI-15, TASK-053) with a stubbed fetch. They prove how the UI
// renders and calls the contract, not the live backend (that is a separate lane/QA step).
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "./render";
import { ReconstructionPanel } from "../src/features/pipeline/ReconstructionPanel";

const P = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const Q = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const R = "11111111-1111-4111-8111-111111111111";
const RUN = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const RUN2 = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const D1 = "d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1";
const D2 = "d2d2d2d2-d2d2-4d2d-8d2d-d2d2d2d2d2d2";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const err = (status: number, code: string, message: string) =>
  json({ error: { code, message, request_id: "req-123", details: null } }, status);

const GATE = (over: Record<string, unknown> = {}) => ({
  project_id: P,
  can_start: false,
  gate_version: "1",
  conditions: [
    { code: "WELLBORE_IDENTIFIED", met: true, message: "At least one well and wellbore is identified." },
    { code: "VALIDATED_TRAJECTORY", met: false, message: "No wellbore has a validated trajectory." },
  ],
  qualifying_wellbore_ids: [],
  unmet: [{ code: "NO_VALIDATED_TRAJECTORY", message: "No wellbore has a validated trajectory; see the per-wellbore reasons.", wellbore_id: null }],
  warnings: [],
  wellbores: [
    {
      well_id: "w1",
      wellbore_id: "b1",
      wellbore_name: "F-11 B",
      trajectory_validated: false,
      trajectory_sets: [],
      location_state: "unlocated",
      unlocated: true,
      unmet: [{ code: "TRAJECTORY_PLANNED_ONLY", message: "Only a planned survey exists.", wellbore_id: "b1" }],
      warnings: [{ code: "SURFACE_LOCATION_MISSING", message: "No surface location in sources.", wellbore_id: "b1" }],
    },
  ],
  ...over,
});

const category = (name: string, over: Record<string, unknown> = {}) => ({
  category: name,
  present: false,
  record_count: 0,
  conflicting_record_count: 0,
  accepted_proposal_count: 0,
  proposal_total: 0,
  proposals_truncated: false,
  proposals: [],
  findings_total: 0,
  findings_truncated: false,
  conflicts: [],
  gaps: [],
  findings: [],
  gap_reasons: [],
  groups: [],
  ...over,
});
const EXPOSURE = (over: Record<string, unknown> = {}) => ({
  project_id: P,
  resolved_current: true,
  resolver_version: "1",
  unresolved_record_count: 0,
  gate: GATE(),
  wells: [
    {
      well_id: "w1",
      name: "F-11",
      wellbores: [
        {
          project_id: P,
          well_id: "w1",
          wellbore_id: "b1",
          wellbore_name: "F-11 B",
          gate: GATE().wellbores[0],
          categories: [
            category("trajectory", {
              present: true,
              record_count: 120,
              findings_total: 250,
              findings_truncated: true,
              findings: [
                { issue_id: "i1", kind: "finding", code: "STATION_ODD", message: "Odd station", severity: "warning", scope: "record", locators: [{ line: 7 }], attribute_keys: [], blocked_operations: [], document_id: D1, run_id: R },
              ],
              groups: [
                {
                  document_id: D1, run_id: R, filename: "traj.csv", kind: "trajectory_station", record_count: 120, evidence_class: "source_record",
                  sample_truncated: true, validation_counts: { unreviewed: 120 }, survey_status: "unstated", profile_name: null,
                  sample: [{ record_id: "r1", kind: "trajectory_station", ordinal: 1, validation_state: "unreviewed", locator: { kind: "text", line: 2 }, attributes: [] }],
                },
              ],
            }),
            category("logs", { gap_reasons: ["NO_RECORDS"] }),
          ],
        },
      ],
    },
  ],
  ...over,
});

const docState = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  document_id: id,
  original_filename: name,
  native_state: "unsupported",
  no_native_parser: true,
  processable: true,
  processing_status: "not_started",
  page_count: 3,
  over_page_cap: false,
  retryable: false,
  state_text: "no native parser; model processing available, not started",
  user_labels: [],
  last_run_id: null,
  not_processable_reason: null,
  ...over,
});
const DOCS = () => ({
  project_id: P,
  source_revision_id: R,
  items: [
    docState(D1, "scan.pdf"),
    docState(D2, "native.pdf", { no_native_parser: false, native_state: "extracted", state_text: "native parsing: extracted; model processing available, not started" }),
  ],
});

const runDoc = (over: Record<string, unknown> = {}) => ({
  document_id: D1, source_revision_id: R, original_filename: "scan.pdf", ordinal: 1, page_count: 3,
  pages: { page_start: 1, page_end: 3 }, pages_done: 0, state: "estimated", estimated_usd: "0.0300", actual_usd: "0",
  retryable: false, label_hints: [], failure_code: null, failure_message: null, finished_at: null, ...over,
});
const runBody = (over: Record<string, unknown> = {}, estOver: Record<string, unknown> = {}) => ({
  run_id: RUN, project_id: P, status: "estimated", step: "stub", attempt_no: 1, cancel_requested: false,
  created_at: "2026-11-01T10:00:00Z", actual_usd: "0", confirmed_usd: null, retry_of_run_id: null,
  error_code: null, error_message: null,
  estimate: {
    confirmable: true, estimated_input_tokens: 1500, estimated_output_tokens: 300, estimated_usd: "0.0300", fits_budget: true,
    pages: 3, pricing_source: "stub_illustrative", provider: "stub", remaining_budget_usd: "4.9700", route: "model",
    total_cap_usd: "5.0000", ...estOver,
  },
  documents: [runDoc()],
  ...over,
});
const summary = (r: ReturnType<typeof runBody>) => ({
  run_id: r.run_id, status: r.status, provider: "stub", created_at: r.created_at, document_count: r.documents.length,
  processed_count: r.documents.filter((d) => d.state === "processed").length, estimated_usd: r.estimate.estimated_usd, actual_usd: r.actual_usd, finished_at: null,
});

interface Mock {
  calls: { method: string; url: string; body: unknown }[];
  runs: Record<string, ReturnType<typeof runBody>>;
  routes: Record<string, (body: unknown) => Response | Promise<Response>>;
}

function install(init: Partial<Mock["runs"]> = {}, routes: Mock["routes"] = {}, project = P): Mock {
  const m: Mock = { calls: [], runs: { ...(init as Mock["runs"]) }, routes };
  const fn = vi.fn((input: RequestInfo | URL, opts?: RequestInit) => {
    const url = String(input);
    const method = opts?.method ?? "GET";
    const body = typeof opts?.body === "string" ? JSON.parse(opts.body) : undefined;
    m.calls.push({ method, url, body });
    if (url === "/api/v1/session") return Promise.resolve(json({ csrf_token: "tok" }));
    const path = url.replace(`/api/v1/projects/${project}`, "");
    const key = `${method} ${path}`;
    const override = m.routes[key];
    if (override !== undefined) return Promise.resolve(override(body));
    if (key === "GET /identity/start-gate") return Promise.resolve(json(GATE()));
    if (key === "GET /identity/exposure") return Promise.resolve(json(EXPOSURE()));
    if (key === "GET /processing/documents") return Promise.resolve(json(DOCS()));
    if (key === "GET /processing/runs") return Promise.resolve(json({ items: Object.values(m.runs).map(summary) }));
    if (key === "POST /processing/runs/estimates") {
      m.runs[RUN] = runBody();
      return Promise.resolve(json(m.runs[RUN], 201));
    }
    const mm = /^(GET|POST) \/processing\/runs\/([^/]+)(\/\w+)?$/.exec(key);
    if (mm !== null) {
      const run = m.runs[mm[2] as string];
      if (run === undefined) return Promise.resolve(err(404, "NOT_FOUND", "no run"));
      if (mm[3] === "/confirm") {
        m.runs[run.run_id] = { ...run, status: "queued", confirmed_usd: run.estimate.estimated_usd } as unknown as typeof run;
        return Promise.resolve(json(m.runs[run.run_id]));
      }
      if (mm[3] === "/cancel") {
        m.runs[run.run_id] = { ...run, status: "cancelled" };
        return Promise.resolve(json(m.runs[run.run_id]));
      }
      if (mm[3] === "/retry") {
        m.runs[RUN2] = runBody({ run_id: RUN2, retry_of_run_id: run.run_id, created_at: "2026-11-01T11:00:00Z" });
        return Promise.resolve(json(m.runs[RUN2], 201));
      }
      return Promise.resolve(json(run));
    }
    throw new Error(`unexpected request ${key}`);
  });
  vi.stubGlobal("fetch", fn);
  return m;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const panel = (project = P, onOpenSource: (id: string) => void = () => undefined) => (
  <ReconstructionPanel projectId={project} revisionId={R} onOpenSource={onOpenSource} />
);

const gw = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  well_id: "w", wellbore_id: id, wellbore_name: name, trajectory_validated: false, trajectory_sets: [],
  location_state: "unlocated", unlocated: true, unmet: [], warnings: [], ...over,
});
const grp = (doc: string, filename: string, kind: string, over: Record<string, unknown> = {}) => ({
  document_id: doc, run_id: R, filename, kind, record_count: 12, evidence_class: "source_record", sample_truncated: false,
  validation_counts: { unreviewed: 12 }, survey_status: null, profile_name: null,
  sample: [{ record_id: "r", kind, ordinal: 1, validation_state: "unreviewed", locator: { kind: "text", line: 2 }, attributes: [] }], ...over,
});
const wb = (g: ReturnType<typeof gw>, categories: ReturnType<typeof category>[]) => ({
  project_id: P, well_id: g.well_id, wellbore_id: g.wellbore_id, wellbore_name: g.wellbore_name, gate: g, categories,
});
/** The owner's F-12 case: a ready wellbore listed last by the API, a not-ready PILOT and a block-less F-12. */
function f12(extra: Record<string, unknown> = {}) {
  const ready = gw("b3", "15/9-F-12", { trajectory_validated: true });
  const pilot = gw("b2", "15/9-F-12 PILOT", { unmet: [{ code: "TRAJECTORY_PLANNED_ONLY", message: "Only a planned survey exists.", wellbore_id: "b2" }] });
  const blockless = gw("b4", "F-12", {
    unmet: [{ code: "NO_VALIDATED_TRAJECTORY", message: "No validated trajectory.", wellbore_id: "b4" }],
    warnings: [{ code: "BLOCK_NOT_STATED", message: "No block stated.", wellbore_id: "b4" }],
  });
  const gate = GATE({ can_start: true, unmet: [], qualifying_wellbore_ids: ["b3"], wellbores: [pilot, ready, blockless] });
  const exposure = EXPOSURE({
    gate,
    wells: [
      { well_id: "w", name: "15/9-F-12", wellbores: [
        wb(pilot, [category("logs", { present: true, record_count: 5, groups: [grp(D2, "logs.las", "log_curve")], conflicts: [
          { issue_id: "c1", kind: "conflict", code: "DEPTH_UNIT_CONFLICT", message: "Units disagree", severity: "error", scope: "record", locators: [{ line: 9 }], attribute_keys: [], blocked_operations: [], document_id: D2, run_id: R } ] })]),
        wb(ready, [
          category("trajectory", { present: true, record_count: 120, groups: [grp(D1, "traj.csv", "trajectory_station")] }),
          category("logs", { gap_reasons: ["NO_RECORDS"] }),
        ]),
      ] },
      { well_id: "w", name: "F-12", wellbores: [wb(blockless, [category("trajectory")])] },
    ],
    ...extra,
  });
  return { gate, exposure, routes: { "GET /identity/start-gate": () => json(gate), "GET /identity/exposure": () => json(exposure) } };
}
const rowOf = async (name: RegExp) => (await screen.findAllByRole("row")).find((r) => name.test(r.textContent ?? ""))!;

describe("Reconstruction list (AC-2, AC-3, AC-4)", () => {
  it("lists ready wellbores first with a text badge, then the rest with the server reason and a block badge", async () => {
    install({}, f12().routes);
    render(panel());
    await screen.findByRole("region", { name: "Identified wellbores table" });
    const body = screen.getAllByRole("row").slice(1);
    expect(body[0]).toHaveTextContent("Well 15/9-F-12");
    expect(body[0]).toHaveTextContent("Wellbore 15/9-F-12");
    expect(body[0]).not.toHaveTextContent("PILOT");
    expect(body[0]).toHaveTextContent("Ready");
    expect(body[0]!.className).toMatch(/readyRow/);
    const pilot = await rowOf(/PILOT/);
    expect(pilot).toHaveTextContent("Not ready");
    expect(pilot).toHaveTextContent("TRAJECTORY_PLANNED_ONLY");
    expect(pilot.className).not.toMatch(/readyRow/);
    const blockless = await rowOf(/Well F-12/);
    expect(blockless).toHaveTextContent("Block not stated");
    expect(blockless).toHaveTextContent("NO_VALIDATED_TRAJECTORY");
    expect(screen.getAllByText("Block not stated")).toHaveLength(1);
  });

  it("has Sources and no Present, Validation or Records column; one heading per category with its count (RR-7)", async () => {
    install({}, f12().routes);
    render(panel());
    await screen.findByRole("region", { name: "Identified wellbores table" });
    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Wellbore", "Readiness", "Sources", "Action"]);
    const ready = (await screen.findAllByRole("row"))[1]!;
    const cats = within(ready).getByRole("list", { name: "Source files of 15/9-F-12" });
    expect(cats).toHaveTextContent("Trajectory - 120 records");
    expect(cats.textContent!.match(/Trajectory/g)).toHaveLength(1);
    expect(ready).not.toHaveTextContent("Logs");
  });

  it("lists the files under their category with own count and first locator, linking to Sources", async () => {
    install({}, f12().routes);
    const open = vi.fn();
    render(panel(P, open));
    const row = (await screen.findAllByRole("row"))[1]!;
    const files = within(row).getByRole("list", { name: "Trajectory files of 15/9-F-12" });
    expect(files).toHaveTextContent("traj.csv (12 trajectory_station; first at line 2)");
    await userEvent.click(within(files).getByRole("link", { name: "Open traj.csv in Sources" }));
    expect(open).toHaveBeenCalledWith(D1);
    expect(await rowOf(/Well F-12/)).toHaveTextContent("No source file carries data");
  });

  it("keeps gaps, conflicts and findings in an expandable detail row only", async () => {
    install({}, f12().routes);
    render(panel());
    const pilot = await rowOf(/PILOT/);
    expect(screen.queryByText("DEPTH_UNIT_CONFLICT")).not.toBeInTheDocument();
    const toggle = within(pilot).getByRole("button", { name: "Show details of 15/9-F-12 PILOT" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    const list = screen.getByRole("list", { name: "Gaps, conflicts and findings of 15/9-F-12 PILOT" });
    expect(list).toHaveTextContent("DEPTH_UNIT_CONFLICT");
    expect(within(pilot).getByRole("button", { name: "Hide details of 15/9-F-12 PILOT" })).toHaveAttribute("aria-expanded", "true");
  });

  it("groups gate warnings by code with the wellbores they name", async () => {
    const f = f12();
    const warn = (id: string) => ({ code: "BLOCK_NOT_STATED", message: "No block stated.", wellbore_id: id });
    const gate = { ...f.gate, warnings: [warn("b4"), warn("b2"), warn("b4")] };
    install({}, { ...f.routes, "GET /identity/start-gate": () => json(gate) });
    render(panel());
    const list = await screen.findByRole("list", { name: "Gate warnings" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(list).toHaveTextContent("Wellbores: F-12, 15/9-F-12 PILOT.");
  });

  it("shows only human source locators, never ids or kinds", async () => {
    const f = f12();
    const ex = f.exposure as unknown as { wells: { wellbores: { categories: { groups: { sample: { locator: unknown }[] }[] }[] }[] }[] };
    ex.wells[0]!.wellbores[1]!.categories[0]!.groups[0]!.sample[0]!.locator = { kind: "pdf", document_id: D1, page: 4, table: 2 };
    install({}, { ...f.routes, "GET /identity/exposure": () => json(f.exposure) });
    render(panel());
    const files = await screen.findByRole("list", { name: "Source files of 15/9-F-12" });
    expect(files).toHaveTextContent("first at page 4, table 2");
    expect(files.textContent).not.toContain(D1);
    expect(files.textContent).not.toContain("kind");
  });

  it("gives the panel a landmark name distinct from the tab section", async () => {
    install();
    render(panel());
    expect(await screen.findByRole("region", { name: "Identified wellbores" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Reconstruction" })).not.toBeInTheDocument();
  });

  it("shows truncation notices in the detail row", async () => {
    install();
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Show details of F-11 B" }));
    const list = screen.getByRole("list", { name: "Gaps, conflicts and findings of F-11 B" });
    expect(list).toHaveTextContent("Findings truncated: showing 1 of 250.");
    expect(list).toHaveTextContent("Some record samples are truncated");
    expect(list).toHaveTextContent("NO_RECORDS");
  });
});

describe("Reconstruct actions (RR-7, RR-8)", () => {
  it("shows a disabled Reconstruct button with its description on ready rows and none on others", async () => {
    const m = install({}, f12().routes);
    render(panel());
    const ready = (await screen.findAllByRole("row"))[1]!;
    const btn = within(ready).getByRole("button", { name: "Reconstruct" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAccessibleDescription("Reconstruction start arrives in the next update");
    const pilot = await rowOf(/PILOT/);
    expect(within(pilot).queryByRole("button", { name: "Reconstruct" })).not.toBeInTheDocument();
    expect(pilot).toHaveTextContent("Not available: not ready");
    expect(pilot).toHaveTextContent("TRAJECTORY_PLANNED_ONLY");
    expect(m.calls.filter((c) => c.method !== "GET")).toEqual([]);
  });

  it("shows a disabled bulk button with the ready count", async () => {
    install({}, f12().routes);
    render(panel());
    const all = await screen.findByRole("button", { name: "Reconstruct all ready wellbores (1)" });
    expect(all).toBeDisabled();
    expect(all).toHaveAccessibleDescription(/Reconstruction start arrives in the next update/);
  });

  it("has no Process action, no Document processing pane, no run list and never says Processed", async () => {
    const m = install({}, f12().routes);
    const { container } = render(panel());
    await screen.findByRole("region", { name: "Identified wellbores table" });
    expect(screen.queryByRole("button", { name: /Process/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Document processing")).not.toBeInTheDocument();
    expect(screen.queryByText(/Nothing to process/)).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/Processed|stub processing/);
    expect(m.calls.some((c) => c.url.includes("/processing/"))).toBe(false);
  });

  it("says start is not available yet, with no OCR and no merge review", async () => {
    install();
    render(panel());
    expect(await screen.findByText(/Starting a reconstruction is not\s+available yet/)).toBeInTheDocument();
    expect(screen.getAllByText(/no OCR/).length).toBeGreaterThan(0);
  });
});

describe("Reconstruction list states (AC-7)", () => {
  it("shows an empty state when no wellbore is identified", async () => {
    install({}, { "GET /identity/exposure": () => json(EXPOSURE({ wells: [] })) });
    render(panel());
    expect(await screen.findByText("No wellbore identified")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reconstruct all ready/ })).not.toBeInTheDocument();
  });

  it("shows a failing endpoint with request id and retries", async () => {
    let fail = true;
    install({}, { "GET /identity/exposure": () => (fail ? err(500, "INTERNAL", "boom") : json(EXPOSURE())) });
    render(panel());
    const alert = (await screen.findByText(/Identified wellbores could not be loaded: boom/)).closest("[role=alert]")!;
    expect(alert).toHaveTextContent("req-123");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry loading identified wellbores" }));
    expect(await screen.findByRole("region", { name: "Identified wellbores table" })).toBeInTheDocument();
  });

  it("never offers Reconstruct when readiness could not be read", async () => {
    install({}, { ...f12().routes, "GET /identity/start-gate": () => err(500, "INTERNAL", "gate down") });
    render(panel());
    const alert = (await screen.findByText(/Readiness could not be loaded.*gate down/)).closest("[role=alert]")!;
    expect(alert).toHaveTextContent("req-123");
    expect(screen.getAllByText("Readiness unknown").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Reconstruct" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconstruct all ready wellbores (0)" })).toBeDisabled();
  });

  it("states stale identities and unresolved records", async () => {
    install({}, { ...f12().routes, "GET /identity/exposure": () => json({ ...f12().exposure, resolved_current: false, unresolved_record_count: 4 }) });
    render(panel());
    expect(await screen.findByText(/Stored identities are out of date/)).toBeInTheDocument();
    expect(screen.getByText(/4 record\(s\) have no resolved wellbore/)).toBeInTheDocument();
  });
});

describe("stale project", () => {
  it("drops answers that arrive after the project changed", async () => {
    let release: (r: Response) => void = () => undefined;
    install({}, { "GET /identity/exposure": () => new Promise<Response>((res) => (release = res)) as unknown as Response });
    const view = render(panel(P));
    await waitFor(() => expect(screen.getByText("Loading identified wellbores…")).toBeInTheDocument());
    view.rerender(<ReconstructionPanel key={Q} projectId={Q} revisionId={R} onOpenSource={() => undefined} />);
    release(json(EXPOSURE({ project_id: P })));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("region", { name: "Identified wellbores table" })).not.toBeInTheDocument();
  });

  it("drops a payload stamped with another project", async () => {
    install({}, { "GET /identity/exposure": () => json(EXPOSURE({ project_id: Q })) });
    render(panel());
    expect(await screen.findByText(/belonged to another project and was dropped/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Identified wellbores table" })).not.toBeInTheDocument();
  });
});

describe("empty and honest wording", () => {
  it("explains no source revision", () => {
    install();
    render(<ReconstructionPanel projectId={P} revisionId={null} onOpenSource={() => undefined} />);
    expect(screen.getByText("Reconstruction is unavailable")).toBeInTheDocument();
  });

});

