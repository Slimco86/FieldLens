// Interaction tests for the Reconstruction tab (UI-16, TASK-063; processing flow from UI-15, TASK-053) with a stubbed fetch. They prove how the UI
// renders and calls the contract, not the live backend (that is a separate lane/QA step).
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "./render";
import { ReconstructionPanel } from "../src/features/pipeline/ReconstructionPanel";
import { chooseDocuments } from "../src/features/pipeline/ReconstructionList";

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
const estimates = (m: Mock) => m.calls.filter((c) => c.method === "POST" && c.url.endsWith("/estimates"));
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

  it("has Sources and no Present or Validation column; counts per category", async () => {
    install({}, f12().routes);
    render(panel());
    await screen.findByRole("region", { name: "Identified wellbores table" });
    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Wellbore", "Readiness", "Records per category", "Sources", "Action"]);
    expect(screen.queryByRole("columnheader", { name: /Present|Validation/ })).not.toBeInTheDocument();
    const ready = (await screen.findAllByRole("row"))[1]!;
    expect(ready).toHaveTextContent("Trajectory: 120");
    expect(ready).not.toHaveTextContent("Logs: 0");
  });

  it("lists the files per category with the first locator and links to the file in Sources", async () => {
    install({}, f12().routes);
    const open = vi.fn();
    render(panel(P, open));
    const row = (await screen.findAllByRole("row"))[1]!;
    const files = within(row).getByRole("list", { name: "Source files of 15/9-F-12" });
    expect(files).toHaveTextContent("Trajectory: traj.csv (12 trajectory_station; first at line 2)");
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
    expect(await screen.findByRole("region", { name: "Wellbores and processing" })).toBeInTheDocument();
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

describe("Process and Process all (AC-5, AC-6)", () => {
  it("estimates for the wellbore's documents, then needs a separate confirm", async () => {
    const m = install({}, f12().routes);
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Process 15/9-F-12" }));
    expect(await screen.findByRole("button", { name: /Confirm and start run/ })).toBeEnabled();
    expect(estimates(m)).toHaveLength(1);
    expect(estimates(m)[0]!.body).toMatchObject({ documents: [{ document_id: D1, pages: null }] });
    expect(m.calls.some((c) => c.url.endsWith("/confirm"))).toBe(false);
    expect(screen.getByText(/Nothing has been spent/)).toBeInTheDocument();
  });

  it("sends one estimate request on a double click", async () => {
    const m = install({}, f12().routes);
    render(panel());
    await userEvent.dblClick(await screen.findByRole("button", { name: "Process 15/9-F-12" }));
    await screen.findByRole("button", { name: /Confirm and start run/ });
    expect(estimates(m)).toHaveLength(1);
  });

  it("process all ready wellbores estimates over the ready wellbores' documents only", async () => {
    const m = install({}, f12().routes);
    render(panel());
    const all = await screen.findByRole("button", { name: "Process all ready wellbores (1)" });
    await userEvent.dblClick(all);
    await screen.findByRole("button", { name: /Confirm and start run/ });
    expect(estimates(m)).toHaveLength(1);
    expect(estimates(m)[0]!.body).toMatchObject({ documents: [{ document_id: D1 }] });
    expect((estimates(m)[0]!.body as { documents: unknown[] }).documents).toHaveLength(1); // PILOT's D2 is not ready
  });

  it("a non-ready wellbore has no Process action and shows the server reason; no ready wellbore disables Process all", async () => {
    install();
    render(panel());
    const row = await rowOf(/F-11 B/);
    expect(within(row).queryByRole("button", { name: /^Process/ })).not.toBeInTheDocument();
    expect(row).toHaveTextContent("TRAJECTORY_PLANNED_ONLY");
    expect(row).toHaveTextContent("Only a planned survey exists.");
    expect(screen.getByRole("button", { name: "Process all ready wellbores (0)" })).toBeDisabled();
    const gate = screen.getByText(/No wellbore is ready to process/).closest("[role=status]")!;
    expect(gate).toHaveTextContent("NO_VALIDATED_TRAJECTORY");
  });

  it("disables Process with a reason when the wellbore's files are all read by native parsers", async () => {
    const m = install({}, {
      ...f12().routes,
      "GET /processing/documents": () => json({ ...DOCS(), items: [docState(D1, "traj.csv", { no_native_parser: false, native_state: "extracted" })] }),
    });
    render(panel());
    const row = (await screen.findAllByRole("row"))[1]!;
    await waitFor(() => expect(row).toHaveTextContent("Nothing to process: data comes from native parsers"));
    expect(within(row).queryByRole("button", { name: /^Process/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Process all ready wellbores (1)" })).toBeDisabled();
    expect(estimates(m)).toHaveLength(0);
  });

  it("disables Process with a reason when everything is already processed", async () => {
    install({}, {
      ...f12().routes,
      "GET /processing/documents": () => json({ ...DOCS(), items: [docState(D1, "traj.csv", { processing_status: "processed" })] }),
    });
    render(panel());
    const row = (await screen.findAllByRole("row"))[1]!;
    await waitFor(() => expect(row).toHaveTextContent("Nothing to process: no document needs processing"));
  });

  it("reuses an existing unconfirmed estimate for the same documents instead of creating another", async () => {
    const existing = runBody({ run_id: RUN2, created_at: "2026-11-01T09:00:00Z" });
    const m = install({ [RUN2]: existing }, f12().routes);
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Process 15/9-F-12" }));
    expect(await screen.findByText(/An estimate for these documents already exists/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Confirm and start run/ })).toBeEnabled();
    expect(estimates(m)).toHaveLength(0);
  });

  it("shows a rejected estimate with request id and spends nothing", async () => {
    install({}, { ...f12().routes, "POST /processing/runs/estimates": () => err(422, "BUDGET_EXCEEDED", "Over budget.") });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Process 15/9-F-12" }));
    const alert = (await screen.findByText(/The estimate was not created: Over budget\./)).closest("[role=alert]")!;
    expect(alert).toHaveTextContent("BUDGET_EXCEEDED");
    expect(alert).toHaveTextContent("Request ID: req-123");
    expect(alert).toHaveTextContent("Nothing was started or spent");
  });

  it("chooseDocuments skips processed, busy, unprocessable and over-cap documents", () => {
    const st = (id: string, over: Record<string, unknown>) => docState(id, `${id}.pdf`, over) as unknown as Parameters<typeof chooseDocuments>[1][number];
    const out = chooseDocuments(
      ["a", "b", "c", "d", "e", "f"],
      [st("a", {}), st("b", { processing_status: "processed" }), st("c", { processing_status: "running" }), st("d", { processable: false, not_processable_reason: "quarantined" }), st("e", { over_page_cap: true })],
    );
    expect(out.selection).toEqual([{ document_id: "a", pages: null }]);
    expect(out.skipped).toHaveLength(5);
    expect(out.skipped.join("|")).toMatch(/quarantined/);
  });
});

describe("Reconstruction list states (AC-7)", () => {
  it("shows an empty state when no wellbore is identified", async () => {
    install({}, { "GET /identity/exposure": () => json(EXPOSURE({ wells: [] })) });
    render(panel());
    expect(await screen.findByText("No wellbore identified")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Process all ready/ })).not.toBeInTheDocument();
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

  it("never offers Process when readiness could not be read", async () => {
    install({}, { ...f12().routes, "GET /identity/start-gate": () => err(500, "INTERNAL", "gate down") });
    render(panel());
    const alert = (await screen.findByText(/Readiness could not be loaded.*gate down/)).closest("[role=alert]")!;
    expect(alert).toHaveTextContent("req-123");
    expect(screen.getAllByText("Readiness unknown").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /^Process 15/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Process all ready wellbores (0)" })).toBeDisabled();
  });

  it("states stale identities and unresolved records", async () => {
    install({}, { ...f12().routes, "GET /identity/exposure": () => json({ ...f12().exposure, resolved_current: false, unresolved_record_count: 4 }) });
    render(panel());
    expect(await screen.findByText(/Stored identities are out of date/)).toBeInTheDocument();
    expect(screen.getByText(/4 record\(s\) have no resolved wellbore/)).toBeInTheDocument();
  });
});

describe("processing: estimate, confirm, start", () => {
  it("defaults to no-native-parser documents, estimates, then needs a separate confirm", async () => {
    const m = install();
    render(panel());
    const est = await screen.findByRole("button", { name: /Request estimate for 1 document/ });
    expect(screen.getByRole("checkbox", { name: "scan.pdf" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "native.pdf" })).not.toBeChecked();
    expect(screen.getAllByText(/No label \(allowed\)/).length).toBeGreaterThan(0);

    await userEvent.click(est);
    const confirm = await screen.findByRole("button", { name: /Confirm and start run \(USD 0.0300\)/ });
    const post = m.calls.find((c) => c.method === "POST" && c.url.endsWith("/estimates"))!;
    expect(post.body).toMatchObject({ documents: [{ document_id: D1, pages: null }] });
    expect(m.calls.some((c) => c.url.endsWith("/confirm"))).toBe(false); // an estimate never confirms
    const facts = screen.getByRole("group", { name: "Estimate" });
    expect(facts).toHaveTextContent("3");
    expect(facts).toHaveTextContent("1,500 input, 300 output");
    expect(facts).toHaveTextContent("USD 4.9700 of USD 5.0000 total");
    expect(screen.getByText(/Stub provider/)).toBeInTheDocument();
    expect(within(facts).getByText(/no OCR/)).toBeInTheDocument();

    await userEvent.click(confirm);
    await waitFor(() => expect(m.calls.find((c) => c.url.endsWith("/confirm"))?.body).toEqual({ estimated_usd: "0.0300" }));
    expect(await screen.findByRole("status", { name: "Run status" })).toHaveTextContent("Queued");
    expect(screen.getByRole("button", { name: "Cancel run" })).toBeEnabled();
  });

  it("disables confirm when the estimate does not fit the budget", async () => {
    const m = install({}, {
      "POST /processing/runs/estimates": () => {
        m.runs[RUN] = runBody({}, { fits_budget: false, confirmable: false, remaining_budget_usd: "0.0100" });
        return json(m.runs[RUN], 201);
      },
    });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: /Request estimate/ }));
    const confirm = await screen.findByRole("button", { name: /Confirm and start run/ });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(/does not fit the remaining budget/)).toBeInTheDocument();
  });

  it("shows the server's rejection of a stale confirm with code and request id, and spends nothing", async () => {
    const m = install({}, {
      "POST /processing/runs/estimates": () => {
        m.runs[RUN] = runBody();
        return json(m.runs[RUN], 201);
      },
      [`POST /processing/runs/${RUN}/confirm`]: () => err(409, "ESTIMATE_STALE", "The estimate changed."),
    });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: /Request estimate/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Confirm and start run/ }));
    const alert = await screen.findByText(/The action was rejected: The estimate changed./);
    expect(alert.closest("[role=alert]")).toHaveTextContent("ESTIMATE_STALE");
    expect(alert.closest("[role=alert]")).toHaveTextContent("Request ID: req-123");
    expect(alert.closest("[role=alert]")).toHaveTextContent("Nothing was started or spent");
  });

  it("shows an estimate rejection (page cap) as an error", async () => {
    install({}, { "POST /processing/runs/estimates": () => err(422, "PAGE_RANGE_REQUIRED", "Document has more than 500 pages.") });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: /Request estimate/ }));
    expect(await screen.findByText(/The estimate was rejected: Document has more than 500 pages./)).toBeInTheDocument();
  });

  it("requires a valid page range for an over-cap document before calling the API", async () => {
    const m = install({}, {
      "GET /processing/documents": () => json({ ...DOCS(), items: [docState(D1, "big.pdf", { over_page_cap: true, page_count: 900 })] }),
    });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: /Request estimate/ }));
    expect(await screen.findByText(/big.pdf: enter both page numbers/)).toBeInTheDocument();
    expect(m.calls.some((c) => c.url.endsWith("/estimates"))).toBe(false);
    await userEvent.type(screen.getByLabelText("First page of big.pdf"), "1");
    await userEvent.type(screen.getByLabelText("Last page of big.pdf"), "501");
    await userEvent.click(screen.getByRole("button", { name: /Request estimate/ }));
    expect(await screen.findByText(/at most 500 pages per run/)).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Last page of big.pdf"));
    await userEvent.type(screen.getByLabelText("Last page of big.pdf"), "500");
    await userEvent.click(screen.getByRole("button", { name: /Request estimate/ }));
    await waitFor(() => expect(m.calls.find((c) => c.url.endsWith("/estimates"))?.body).toMatchObject({
      documents: [{ document_id: D1, pages: { page_start: 1, page_end: 500 } }],
    }));
  });

  it("starts without a label and with an empty selection disabled", async () => {
    install();
    render(panel());
    await userEvent.click(await screen.findByRole("checkbox", { name: "scan.pdf" }));
    expect(screen.getByRole("button", { name: /Request estimate for 0 document/ })).toBeDisabled();
  });
});

describe("processing: cancel, retry, failure honesty", () => {
  it("cancels a running run", async () => {
    const m = install({ [RUN]: runBody({ status: "running", documents: [runDoc({ state: "running", pages_done: 1 })] }) });
    render(panel());
    expect(await screen.findByText("1 / 3 pages")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel run" }));
    await waitFor(() => expect(m.calls.some((c) => c.method === "POST" && c.url.endsWith("/cancel"))).toBe(true));
    expect(await screen.findByRole("status", { name: "Run status" })).toHaveTextContent("Cancelled");
  });

  it("never shows an interrupted run as success and retry needs its own confirm", async () => {
    const m = install({
      [RUN]: runBody({
        status: "interrupted", error_code: "interrupted", error_message: "The server restarted.",
        documents: [runDoc({ state: "interrupted", retryable: true, failure_code: "interrupted", failure_message: "stopped at page 2", pages_done: 2 })],
      }),
    });
    render(panel());
    const status = await screen.findByRole("status", { name: "Run status" });
    expect(status).toHaveTextContent("Interrupted: not completed");
    expect(status).not.toHaveTextContent("Succeeded");
    expect(screen.getByText(/did not complete successfully/)).toBeInTheDocument();
    expect(screen.queryByText("Processed")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Request retry estimate for 1 document/ }));
    expect(await screen.findByRole("button", { name: /Confirm and start run/ })).toBeEnabled();
    expect(m.calls.some((c) => c.url.endsWith("/confirm"))).toBe(false);
    expect(m.calls.some((c) => c.method === "POST" && c.url.endsWith("/retry"))).toBe(true);
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

  it("says a run is a stub step, not reconstruction", async () => {
    install();
    render(panel());
    expect(await screen.findByText(/it is not reconstruction/)).toBeInTheDocument();
    expect(screen.getAllByText(/no OCR/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/merge review is not\s+yet available/).length).toBeGreaterThan(0);
  });
});

describe("QA repair (D1 and cosmetics)", () => {
  it("labels the remaining budget live only while estimated, otherwise as an estimate-time snapshot", async () => {
    install({ [RUN]: runBody() });
    const view = render(panel());
    const facts = await screen.findByRole("group", { name: "Estimate" });
    expect(facts).toHaveTextContent("Remaining budget");
    expect(facts).not.toHaveTextContent("estimate time");
    view.unmount();
    for (const status of ["queued", "running", "succeeded", "cancelled"] as const) {
      install({ [RUN]: runBody({ status }) });
      const v = render(panel());
      const g = await screen.findByRole("group", { name: "Estimate" });
      expect(g).toHaveTextContent("Remaining at estimate time");
      expect(g).toHaveTextContent("not the current budget");
      expect(g).not.toHaveTextContent(/Remaining budget/);
      v.unmount();
    }
  });

  it("does not repeat the failure code when the message already says it", async () => {
    install({ [RUN]: runBody({ status: "cancelled", error_code: "cancelled", error_message: "cancelled by the user" }) });
    render(panel());
    const note = await screen.findByText(/did not complete successfully/);
    expect(note.textContent).toBe("This run did not complete successfully. cancelled by the user Documents that did not finish are not processed.");
  });

  it("gives every input in the panel an accessible name", async () => {
    install({ [RUN]: runBody({ status: "running", documents: [runDoc({ state: "running", pages_done: 1 })] }) }, {
      "GET /processing/documents": () => json({ ...DOCS(), items: [...DOCS().items, docState(D2, "big.pdf", { over_page_cap: true, page_count: 900 })] }),
    });
    const { container } = render(panel());
    await screen.findByLabelText("First page of big.pdf");
    await screen.findByText("1 / 3 pages");
    const unnamed = [...container.querySelectorAll("input, progress, select, textarea")].filter(
      (el) => (el.getAttribute("aria-label") ?? "") === "" && (el.id === "" || container.querySelector(`label[for="${el.id}"]`) === null),
    );
    expect(unnamed).toEqual([]);
  });
});
