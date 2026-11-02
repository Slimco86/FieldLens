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

const EST = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const stage = (name: string, state: string, over: Record<string, unknown> = {}) => ({
  stage: name, kind: name === "extract" || name === "identify" ? "agent" : "deterministic",
  ordinal: ["gather", "extract", "identify", "assemble"].indexOf(name) + 1, state, counts: {}, input_tokens: 0, output_tokens: 0,
  actual_usd: "0", reason_code: null, error_code: null, message: null, started_at: null, finished_at: null, ...over,
});
const SUMMARY = () => ({
  wellbore_id: "b3", wellbore_name: "15/9-F-12", draft: true, published: false, scene_3d: "not_generated",
  note: "Draft assembled from validated records; agent stages did not run.", actual_usd: "0",
  stages_succeeded: ["gather", "assemble"], stages_not_available: ["extract", "identify"], stages_failed: [],
  coverage: [
    { category: "trajectory", present: true, record_count: 120, accepted_candidate_count: 0, open_candidate_count: 1, conflicting_record_count: 0, gap_reasons: [], evidence_truncated: false,
      evidence: [{ document_id: D1, filename: "traj.csv", record_kind: "trajectory_station", locator: { kind: "text", document_id: D1, line_start: 26, line_end: 26 } }] },
    { category: "logs", present: false, record_count: 0, accepted_candidate_count: 0, open_candidate_count: 0, conflicting_record_count: 0, gap_reasons: ["NO_RECORDS"], evidence: [], evidence_truncated: false },
  ],
  unresolved: [{ kind: "unlocated_surface", code: "SURFACE_LOCATION_MISSING", message: "No surface location in sources.", count: null, reference_id: null, scope: "wellbore", evidence: [] }],
  conflicts: [{ category: "trajectory", code: "DEPTH_UNIT_CONFLICT", message: "Units disagree", severity: "error", evidence: [{ document_id: D1, filename: "traj.csv", record_kind: null, locator: { page: 4 } }] }],
});
/** A stored run of 15/9-F-12 (b3). `partial` is the honest end state of this build. */
const runOf = (status: string, over: Record<string, unknown> = {}) => ({
  run_id: RUN, project_id: P, well_id: "w", wellbore_id: "b3", wellbore_name: "15/9-F-12", estimate_id: EST, source_revision: "rev1",
  status, provider: "stub", pricing_source: "stub_illustrative", estimated_usd: "0.0200", actual_usd: "0", confirmed_usd: "0.0200",
  confirmed_at: "2026-11-02T08:00:00Z", created_at: "2026-11-02T08:00:00Z", started_at: null, finished_at: null, cancel_requested: false,
  retry_of_run_id: null, error_code: null, error_message: null, retryable: ["failed", "cancelled", "interrupted"].includes(status),
  stages: status === "partial"
    ? [stage("gather", "succeeded"), stage("extract", "not_available", { reason_code: "agent_step_not_implemented" }), stage("identify", "not_available", { reason_code: "agent_step_not_implemented" }), stage("assemble", "succeeded")]
    : [stage("gather", status === "running" ? "running" : "pending"), stage("extract", "pending"), stage("identify", "pending"), stage("assemble", "pending")],
  summary: status === "partial" ? SUMMARY() : null, ...over,
});
const estItem = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  wellbore_id: id, wellbore_name: name, source_revision: "rev1", run_id: RUN, run_status: "estimated", already_active: false, estimated_usd: "0.0200",
  stages: [
    { stage: "gather", kind: "deterministic", availability: "will_run", estimated_usd: "0.0000", reason_code: null, page_cap: null },
    { stage: "extract", kind: "agent", availability: "not_available", estimated_usd: "0.0200", reason_code: "agent_step_not_implemented", page_cap: 500 },
    { stage: "identify", kind: "agent", availability: "not_available", estimated_usd: "0.0000", reason_code: "agent_step_not_implemented", page_cap: null },
    { stage: "assemble", kind: "deterministic", availability: "will_run", estimated_usd: "0.0000", reason_code: null, page_cap: null },
  ], ...over,
});
const ESTIMATE = (items: unknown[], over: Record<string, unknown> = {}) => ({
  project_id: P, estimate_id: EST, items, total_estimated_usd: "0.0200", total_cap_usd: "5.0000", remaining_budget_usd: "4.9000",
  fits_budget: true, confirmable: true, confirmed: false, live_calls: false, provider: "stub", pricing_source: "stub_illustrative",
  pricing_label: "stub planning rate, illustrative", ...over,
});

interface Mock {
  calls: { method: string; url: string; body: unknown }[];
  runs: ReturnType<typeof runOf>[];
  routes: Record<string, (body: unknown) => Response | Promise<Response>>;
}

/** `runs` seeds the stored reconstruction runs; routes override any `METHOD /path` below the project. */
function install(runs: ReturnType<typeof runOf>[] = [], routes: Mock["routes"] = {}, project = P): Mock {
  const m: Mock = { calls: [], runs: [...runs], routes };
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
    if (key === "GET /reconstruction-runs") return Promise.resolve(json({ items: m.runs, total: m.runs.length }));
    if (key === "POST /reconstruction-runs/estimates") return Promise.resolve(json(ESTIMATE([estItem("b3", "15/9-F-12")]), 201));
    if (/^POST \/reconstruction-runs\/estimates\/[^/]+\/confirm$/.test(key)) {
      m.runs = [runOf("queued")];
      return Promise.resolve(json({ items: m.runs, total: 1 }, 202));
    }
    if (/^POST \/reconstruction-runs\/[^/]+\/cancel$/.test(key)) {
      m.runs = m.runs.map((r) => ({ ...r, status: "cancelled", retryable: true }));
      return Promise.resolve(json(m.runs[0]));
    }
    if (/^POST \/reconstruction-runs\/[^/]+\/retry$/.test(key)) return Promise.resolve(json(ESTIMATE([estItem("b3", "15/9-F-12")]), 201));
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
    install([], f12().routes);
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
    install([], f12().routes);
    render(panel());
    await screen.findByRole("region", { name: "Identified wellbores table" });
    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toEqual(["Wellbore", "Readiness", "Sources", "Action"]);
    const ready = (await screen.findAllByRole("row"))[1]!;
    const cats = within(ready).getByRole("group", { name: "Source files of 15/9-F-12" });
    expect(cats).toHaveTextContent("Trajectory - 120 records");
    expect(cats.textContent!.match(/Trajectory/g)).toHaveLength(1);
    expect(ready).not.toHaveTextContent("Logs");
  });

  it("lists the files under their category with own count and first locator, linking to Sources", async () => {
    install([], f12().routes);
    const open = vi.fn();
    render(panel(P, open));
    const row = (await screen.findAllByRole("row"))[1]!;
    const files = within(row).getByRole("list", { name: "Trajectory files of 15/9-F-12" });
    expect(files).toHaveTextContent("traj.csv (12 records; first at line 2)");
    await userEvent.click(within(files).getByRole("link", { name: "Open traj.csv in Sources" }));
    expect(open).toHaveBeenCalledWith(D1);
    expect(await rowOf(/Well F-12/)).toHaveTextContent("No source file carries data");
  });

  it("keeps gaps, conflicts and findings in an expandable detail row only", async () => {
    install([], f12().routes);
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
    install([], { ...f.routes, "GET /identity/start-gate": () => json(gate) });
    render(panel());
    const list = await screen.findByRole("list", { name: "Gate warnings" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(list).toHaveTextContent("Wellbores: F-12, 15/9-F-12 PILOT.");
  });

  it("shows only human source locators, never ids or kinds", async () => {
    const f = f12();
    const ex = f.exposure as unknown as { wells: { wellbores: { categories: { groups: { sample: { locator: unknown }[] }[] }[] }[] }[] };
    ex.wells[0]!.wellbores[1]!.categories[0]!.groups[0]!.sample[0]!.locator = { kind: "pdf", document_id: D1, page: 4, table: 2 };
    install([], { ...f.routes, "GET /identity/exposure": () => json(f.exposure) });
    render(panel());
    const files = await screen.findByRole("group", { name: "Source files of 15/9-F-12" });
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

const openDialog = async (name = "Reconstruct 15/9-F-12") => {
  await userEvent.click(await screen.findByRole("button", { name }));
  return screen.findByRole("dialog");
};
const posts = (m: Mock, tail: string) => m.calls.filter((c) => c.method === "POST" && c.url.endsWith(tail));
const CONFIRM = /Confirm and start/;

describe("Reconstruct: estimate, separate confirm (RR-6)", () => {
  it("offers Reconstruct only on ready rows; non-ready rows keep the server reason and have no button", async () => {
    const m = install([], f12().routes);
    render(panel());
    const ready = (await screen.findAllByRole("row"))[1]!;
    expect(within(ready).getByRole("button", { name: "Reconstruct 15/9-F-12" })).toBeEnabled();
    const pilot = await rowOf(/PILOT/);
    expect(within(pilot).queryByRole("button", { name: /Reconstruct/ })).not.toBeInTheDocument();
    expect(pilot).toHaveTextContent("Not available: not ready");
    expect(pilot).toHaveTextContent("TRAJECTORY_PLANNED_ONLY");
    expect(m.calls.filter((c) => c.method !== "GET")).toEqual([]);
  });

  it("requests an estimate, shows it in a dialog and starts nothing until Confirm", async () => {
    const m = install([], f12().routes);
    render(panel());
    const dlg = await openDialog();
    expect(posts(m, "/estimates")[0]!.body).toEqual({ wellbore_ids: ["b3"] });
    expect(within(dlg).getByRole("table", { name: "Estimate per wellbore" })).toHaveTextContent("15/9-F-12");
    expect(dlg).toHaveTextContent("USD 0.0200");
    expect(dlg).toHaveTextContent("USD 4.9000 of USD 5.0000 total cap");
    expect(dlg).toHaveTextContent("stub");
    expect(dlg).toHaveTextContent("no live model calls");
    expect(dlg).toHaveTextContent("capped at 500");
    expect(dlg).toHaveTextContent("Not available yet");
    expect(dlg).toHaveTextContent("Extract");
    expect(posts(m, "/confirm")).toHaveLength(0);
    await userEvent.click(within(dlg).getByRole("button", { name: CONFIRM }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posts(m, "/confirm")).toHaveLength(1);
    expect(posts(m, "/confirm")[0]!.body).toEqual({ estimated_usd: "0.0200" });
    expect((await screen.findAllByText("Queued")).length).toBeGreaterThan(0);
  });

  it("sends one estimate request on a double click", async () => {
    const m = install([], f12().routes);
    render(panel());
    await userEvent.dblClick(await screen.findByRole("button", { name: "Reconstruct 15/9-F-12" }));
    await screen.findByRole("dialog");
    expect(posts(m, "/estimates")).toHaveLength(1);
  });

  it("sends one confirm request on a double click", async () => {
    const m = install([], f12().routes);
    render(panel());
    const dlg = await openDialog();
    await userEvent.dblClick(within(dlg).getByRole("button", { name: CONFIRM }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posts(m, "/confirm")).toHaveLength(1);
  });

  it("Cancel and Escape close the dialog without confirming; focus returns to the button", async () => {
    const m = install([], f12().routes);
    render(panel());
    const dlg = await openDialog();
    await userEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posts(m, "/confirm")).toHaveLength(0);
    await waitFor(() => expect(screen.getByRole("button", { name: "Reconstruct 15/9-F-12" })).toHaveFocus());
    await new Promise((r) => setTimeout(r, 1100));
    await openDialog();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posts(m, "/confirm")).toHaveLength(0);
  });

  it("Reconstruct all ready wellbores estimates over every ready wellbore with one confirm", async () => {
    const m = install([], f12().routes);
    render(panel());
    const all = await screen.findByRole("button", { name: "Reconstruct all ready wellbores (1)" });
    expect(all).toBeEnabled();
    await userEvent.click(all);
    const dlg = await screen.findByRole("dialog", { name: /all ready wellbores/ });
    expect(posts(m, "/estimates")[0]!.body).toEqual({ all_ready: true });
    await userEvent.click(within(dlg).getByRole("button", { name: CONFIRM }));
    await waitFor(() => expect(posts(m, "/confirm")).toHaveLength(1));
  });

  it("disables bulk when no wellbore is ready", async () => {
    install([]);
    render(panel());
    expect(await screen.findByRole("button", { name: "Reconstruct all ready wellbores (0)" })).toBeDisabled();
  });

  it("has no Process action, no Document processing pane and never says Processed", async () => {
    const m = install([], f12().routes);
    const { container } = render(panel());
    await screen.findByRole("region", { name: "Identified wellbores table" });
    expect(screen.queryByRole("button", { name: /^Process/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Document processing")).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/Processed|stub processing/);
    expect(m.calls.some((c) => c.url.includes("/processing/"))).toBe(false);
  });
});

describe("Reconstruct: duplicate start and errors", () => {
  it("shows an already-active answer without an error and does not open a dialog", async () => {
    const f = f12();
    install([runOf("running")], {
      ...f.routes,
      "POST /reconstruction-runs/estimates": () =>
        json(ESTIMATE([estItem("b3", "15/9-F-12", { already_active: true, run_status: "running", estimated_usd: "0.0000" })], { estimate_id: null, total_estimated_usd: "0.0000" }), 201),
    });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Reconstruct all ready wellbores (1)" }));
    expect(await screen.findByText(/already has an active run/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("marks an already-active wellbore inside a mixed estimate", async () => {
    install([], {
      ...f12().routes,
      "POST /reconstruction-runs/estimates": () =>
        json(ESTIMATE([estItem("b3", "15/9-F-12"), estItem("b9", "F-99", { already_active: true, run_status: "queued", estimated_usd: "0.0000" })]), 201),
    });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Reconstruct all ready wellbores (1)" }));
    const dlg = await screen.findByRole("dialog");
    expect(dlg).toHaveTextContent("Already active");
    expect(dlg).toHaveTextContent("shown, not started again");
  });

  it("disables Reconstruct on a wellbore whose run is queued or running", async () => {
    install([runOf("running")], f12().routes);
    render(panel());
    expect(await screen.findByRole("button", { name: "Reconstruct 15/9-F-12" })).toBeDisabled();
  });

  it("shows a not-ready rejection with code and request id as an alert and starts nothing", async () => {
    const m = install([], { ...f12().routes, "POST /reconstruction-runs/estimates": () => err(422, "WELLBORE_NOT_READY", "Wellbore is not ready: NO_VALIDATED_TRAJECTORY") });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Reconstruct 15/9-F-12" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Wellbore is not ready: NO_VALIDATED_TRAJECTORY");
    expect(alert).toHaveTextContent("WELLBORE_NOT_READY");
    expect(alert).toHaveTextContent("req-123");
    expect(alert).toHaveTextContent("Nothing was started or spent");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(posts(m, "/confirm")).toHaveLength(0);
  });

  it("shows a network failure on estimate as an alert", async () => {
    install([], {
      ...f12().routes,
      "POST /reconstruction-runs/estimates": () => Promise.reject(new TypeError("fetch failed")) as unknown as Response,
    });
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Reconstruct 15/9-F-12" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The local API is unreachable");
  });

  it("disables Confirm when the estimate does not fit the budget", async () => {
    install([], {
      ...f12().routes,
      "POST /reconstruction-runs/estimates": () =>
        json(ESTIMATE([estItem("b3", "15/9-F-12")], { fits_budget: false, confirmable: false, remaining_budget_usd: "0.0100" }), 201),
    });
    render(panel());
    const dlg = await openDialog();
    expect(within(dlg).getByRole("button", { name: CONFIRM })).toBeDisabled();
    expect(within(dlg).getByRole("alert")).toHaveTextContent("does not fit the remaining budget");
  });

  it("shows a rejected confirm (cap exceeded) inside the dialog and spends nothing", async () => {
    install([], {
      ...f12().routes,
      [`POST /reconstruction-runs/estimates/${EST}/confirm`]: () => err(409, "BUDGET_EXCEEDED", "The USD 5 total cap would be exceeded"),
    });
    render(panel());
    const dlg = await openDialog();
    await userEvent.click(within(dlg).getByRole("button", { name: CONFIRM }));
    const alert = await within(dlg).findByRole("alert");
    expect(alert).toHaveTextContent("The USD 5 total cap would be exceeded");
    expect(alert).toHaveTextContent("BUDGET_EXCEEDED");
    expect(alert).toHaveTextContent("req-123");
    expect(alert).toHaveTextContent("Nothing was spent");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows a run-state load failure with retry while the table stays", async () => {
    let fail = true;
    install([], { ...f12().routes, "GET /reconstruction-runs": () => (fail ? err(500, "INTERNAL", "runs down") : json({ items: [], total: 0 })) });
    render(panel());
    const alert = (await screen.findByText(/Run state could not be loaded: runs down/)).closest("[role=alert]")!;
    expect(alert).toHaveTextContent("req-123");
    expect(screen.getByRole("region", { name: "Identified wellbores table" })).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry loading run state" }));
    await waitFor(() => expect(screen.queryByText(/Run state could not be loaded/)).not.toBeInTheDocument());
  });
});

describe("Run state and draft detail (RR-8)", () => {
  it("reads a partial run as partial, names the unavailable stages and never as processed, complete or succeeded", async () => {
    install([runOf("partial")], f12().routes);
    render(panel());
    const row = (await screen.findAllByRole("row"))[1]!;
    expect(row).toHaveTextContent("Partial");
    expect(row).toHaveTextContent("This is not a finished reconstruction");
    const stages = within(row).getByRole("list", { name: "Stages of 15/9-F-12" });
    expect(stages).toHaveTextContent("Extract: Not available yet: agent extraction");
    expect(stages).toHaveTextContent("Identify: Not available yet: agent merge identification");
    expect(stages).toHaveTextContent("Gather: Done");
    expect(row.textContent).not.toMatch(/Processed|Succeeded|Complete/);
  });

  it("shows the draft summary with coverage, human evidence, unresolved and conflicts, and says it is not the published model", async () => {
    const open = vi.fn();
    install([runOf("partial")], f12().routes);
    render(panel(P, open));
    await userEvent.click(await screen.findByRole("button", { name: "Show run draft of 15/9-F-12" }));
    const sec = await screen.findByRole("region", { name: "Run draft of 15/9-F-12" });
    expect(sec).toHaveTextContent("draft");
    expect(sec).toHaveTextContent("not the published 3D model or charts");
    expect(sec.textContent).not.toMatch(/Processed|Complete/);
    const cov = within(sec).getByRole("list", { name: "Coverage of 15/9-F-12" });
    expect(cov).toHaveTextContent("trajectory: 120 record(s)");
    expect(cov).toHaveTextContent("logs: no data (gaps: NO_RECORDS)");
    expect(cov).toHaveTextContent("traj.csv");
    expect(cov).toHaveTextContent("line 26");
    expect(sec.textContent).not.toMatch(/line_start|line_end|kind/);
    expect(sec.textContent).not.toContain(D1);
    expect(within(sec).getByRole("list", { name: "Unresolved items of 15/9-F-12" })).toHaveTextContent("SURFACE_LOCATION_MISSING");
    const conf = within(sec).getByRole("list", { name: "Conflicts of 15/9-F-12" });
    expect(conf).toHaveTextContent("DEPTH_UNIT_CONFLICT");
    expect(conf).toHaveTextContent("page 4");
    await userEvent.click(within(cov).getByRole("link", { name: "Open traj.csv in Sources" }));
    expect(open).toHaveBeenCalledWith(D1);
  });

  it("cancels a running run, then offers Retry that needs a new estimate and its own confirm", async () => {
    const m = install([runOf("running")], f12().routes);
    render(panel());
    await userEvent.click(await screen.findByRole("button", { name: "Cancel reconstruction of 15/9-F-12" }));
    await waitFor(() => expect(posts(m, "/cancel")).toHaveLength(1));
    const retry = await screen.findByRole("button", { name: "Retry reconstruction of 15/9-F-12" });
    expect((await screen.findAllByText("Cancelled")).length).toBeGreaterThan(0);
    await userEvent.click(retry);
    const dlg = await screen.findByRole("dialog");
    expect(posts(m, "/retry")).toHaveLength(1);
    expect(posts(m, "/confirm")).toHaveLength(0);
    await userEvent.click(within(dlg).getByRole("button", { name: CONFIRM }));
    await waitFor(() => expect(posts(m, "/confirm")).toHaveLength(1));
  });

  it("shows failed and interrupted runs as such with Retry, never as success", async () => {
    for (const status of ["failed", "interrupted"] as const) {
      install([runOf(status, { error_message: "provider failure", error_code: "PROVIDER_ERROR" })], f12().routes);
      const v = render(panel());
      const row = (await screen.findAllByRole("row"))[1]!;
      expect(row).toHaveTextContent(status === "failed" ? "Failed" : "Interrupted");
      expect(within(row).getByRole("button", { name: "Retry reconstruction of 15/9-F-12" })).toBeEnabled();
      expect(row.textContent).not.toMatch(/Succeeded|Processed|Complete/);
      v.unmount();
    }
  });

  it("polls while a run is active and stops when it is terminal", async () => {
    const m = install([runOf("running")], f12().routes);
    render(panel());
    await screen.findAllByText("Running");
    m.runs = [runOf("partial")];
    await waitFor(() => expect(screen.getAllByText("Partial").length).toBeGreaterThan(0), { timeout: 8000 });
    const count = () => m.calls.filter((c) => c.url.endsWith("/reconstruction-runs")).length;
    const n = count();
    await new Promise((r) => setTimeout(r, 3500));
    expect(count()).toBe(n);
  }, 20000);
});

describe("Sources column nits (TASK-067 follow-up)", () => {
  it("renders the category label as a heading with its count and lists each file once with combined count", async () => {
    const f = f12();
    const ex = f.exposure as unknown as { wells: { wellbores: { categories: { groups: unknown[] }[] }[] }[] };
    const cat = ex.wells[0]!.wellbores[1]!.categories[0]!;
    cat.groups = [
      grp(D1, "traj.csv", "trajectory_station", {
        record_count: 100,
        sample: [{ record_id: "r", kind: "t", ordinal: 1, validation_state: "u", locator: { kind: "text", document_id: D1, line_start: 26, line_end: 26 }, attributes: [] }],
      }),
      grp(D1, "traj.csv", "trajectory_header", { record_count: 20 }),
    ];
    install([], { ...f.routes, "GET /identity/exposure": () => json(f.exposure) });
    render(panel());
    const row = (await screen.findAllByRole("row"))[1]!;
    expect(within(row).getByRole("heading", { name: "Trajectory - 120 records" })).toBeInTheDocument();
    const files = within(row).getByRole("list", { name: "Trajectory files of 15/9-F-12" });
    expect(within(files).getAllByRole("listitem")).toHaveLength(1);
    expect(files).toHaveTextContent("traj.csv (120 records; first at line 26)");
    expect(files.textContent).not.toMatch(/line_end|line_start|kind|trajectory_/);
  });
});

describe("Reconstruction list states (AC-7)", () => {
  it("shows an empty state when no wellbore is identified", async () => {
    install([], { "GET /identity/exposure": () => json(EXPOSURE({ wells: [] })) });
    render(panel());
    expect(await screen.findByText("No wellbore identified")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reconstruct all ready/ })).not.toBeInTheDocument();
  });

  it("shows a failing endpoint with request id and retries", async () => {
    let fail = true;
    install([], { "GET /identity/exposure": () => (fail ? err(500, "INTERNAL", "boom") : json(EXPOSURE())) });
    render(panel());
    const alert = (await screen.findByText(/Identified wellbores could not be loaded: boom/)).closest("[role=alert]")!;
    expect(alert).toHaveTextContent("req-123");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry loading identified wellbores" }));
    expect(await screen.findByRole("region", { name: "Identified wellbores table" })).toBeInTheDocument();
  });

  it("never offers Reconstruct when readiness could not be read", async () => {
    install([], { ...f12().routes, "GET /identity/start-gate": () => err(500, "INTERNAL", "gate down") });
    render(panel());
    const alert = (await screen.findByText(/Readiness could not be loaded.*gate down/)).closest("[role=alert]")!;
    expect(alert).toHaveTextContent("req-123");
    expect(screen.getAllByText("Readiness unknown").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /^Reconstruct 15/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconstruct all ready wellbores (0)" })).toBeDisabled();
  });

  it("states stale identities and unresolved records", async () => {
    install([], { ...f12().routes, "GET /identity/exposure": () => json({ ...f12().exposure, resolved_current: false, unresolved_record_count: 4 }) });
    render(panel());
    expect(await screen.findByText(/Stored identities are out of date/)).toBeInTheDocument();
    expect(screen.getByText(/4 record\(s\) have no resolved wellbore/)).toBeInTheDocument();
  });
});

describe("stale project", () => {
  it("drops answers that arrive after the project changed", async () => {
    let release: (r: Response) => void = () => undefined;
    install([], { "GET /identity/exposure": () => new Promise<Response>((res) => (release = res)) as unknown as Response });
    const view = render(panel(P));
    await waitFor(() => expect(screen.getByText("Loading identified wellbores…")).toBeInTheDocument());
    view.rerender(<ReconstructionPanel key={Q} projectId={Q} revisionId={R} onOpenSource={() => undefined} />);
    release(json(EXPOSURE({ project_id: P })));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("region", { name: "Identified wellbores table" })).not.toBeInTheDocument();
  });

  it("drops a payload stamped with another project", async () => {
    install([], { "GET /identity/exposure": () => json(EXPOSURE({ project_id: Q })) });
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

