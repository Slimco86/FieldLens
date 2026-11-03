// TASK-055 AC-10: the Sources evidence panel shows model processing for documents without a native
// parser: the estimate -> confirm flow, per-document states, typed failures with retry, cache hits and
// the model-read result as an unverified proposal. fetch is stubbed; the backend is proven elsewhere.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "./render";
import { EvidencePanel } from "../src/features/uploads/EvidencePanel";
import type { SourceDocumentItem } from "../src/features/uploads/api";

const P = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const D = "d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1";
const RUN = "22222222-2222-4222-8222-222222222222";
const RUN2 = "33333333-3333-4333-8333-333333333333";
const doc = { document_id: D, original_filename: "completion.pdf", storage_state: "stored" } as unknown as SourceDocumentItem;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const report = {
  project_id: P,
  document_id: D,
  source_revision_id: "r",
  run_id: "x",
  status: "unsupported",
  profile_name: null,
  profile_version: null,
  method: null,
  stale: false,
  attempt_no: 1,
  coverage: null,
  record_counts: {},
  wellbores: [],
  issues: [],
  error: null,
  detail: {},
};

function state(over: Record<string, unknown> = {}) {
  return {
    document_id: D,
    original_filename: "completion.pdf",
    page_count: 12,
    native_state: "unsupported",
    no_native_parser: true,
    state_text: "no native parser; model processing available, not started",
    processable: true,
    not_processable_reason: null,
    over_page_cap: false,
    user_labels: [],
    processing_status: "not_started",
    last_run_id: null,
    retryable: false,
    model_read: null,
    ...over,
  };
}

const estimate = (over: Record<string, unknown> = {}, runId = RUN) => ({
  run_id: runId,
  project_id: P,
  status: "estimated",
  step: "model_classification",
  estimate: {
    pages: 5,
    route: "model",
    provider: "meta",
    estimated_input_tokens: 8000,
    estimated_output_tokens: 2000,
    estimated_usd: "0.007400",
    pricing_source: "owner_meta_rates",
    total_cap_usd: "5",
    remaining_budget_usd: "4.5",
    fits_budget: true,
    confirmable: true,
    model: "muse-spark",
    spends_money: true,
    force: false,
    ...over,
  },
  actual_usd: "0",
  attempt_no: 0,
  documents: [
    { document_id: D, state: "estimated", page_count: 12, pages: { page_start: 1, page_end: 5 }, cache_hit: false, retryable: false, actual_usd: "0" },
  ],
});

function runWith(docOver: Record<string, unknown>, over: Record<string, unknown> = {}) {
  const e = estimate();
  return { ...e, status: "failed", ...over, documents: [{ ...e.documents[0], ...docOver }] };
}

const identity = (over: Record<string, unknown> = {}) => ({
  proposal_id: "p1",
  subject_kind: "wellbore",
  name_as_written: "NO 15/9-F-12 H",
  normalized_key: "15/9-F-12 H",
  page: 2,
  quote: "Wellbore: NO 15/9-F-12 H",
  status: "model_proposal",
  label: "Model-read, unverified",
  resolution: "unresolved",
  wellbore_id: null,
  wellbore_key: null,
  ...over,
});

const read = (over: Record<string, unknown> = {}) => ({
  document_id: D,
  run_id: RUN,
  category: "completion_equipment",
  unclassified: false,
  tags: ["packer", "tubing"],
  identities: [identity()],
  warnings: [],
  pages: { page_start: 1, page_end: 5 },
  pages_read: 5,
  provider: "meta",
  model_revision: "muse-1",
  prompt_version: "p1",
  schema_version: "s1",
  extraction_method: "model_classification",
  label: "Model-read, unverified",
  created_at: "2026-11-02T10:00:00Z",
  ...over,
});

const providerInfo = (over: Record<string, unknown> = {}) => ({
  requested: "meta",
  active: "meta",
  model: "muse-spark",
  status: "live",
  missing: [],
  spends_money: true,
  message: "live",
  ...over,
});

const runEntry = (over: Record<string, unknown> = {}) => ({
  run_id: RUN,
  state: "processed",
  provider: "meta",
  model: "muse-spark",
  forced: false,
  created_at: "2026-11-02T10:00:00Z",
  started_at: "2026-11-02T10:00:01Z",
  finished_at: "2026-11-02T10:00:09Z",
  pages: { page_start: 1, page_end: 5 },
  pages_read: 5,
  input_tokens: 8123,
  output_tokens: 456,
  usd_actual: "0.007100",
  cache_hit: false,
  failure_code: null,
  failure_message: null,
  warnings: [],
  message: null,
  ...over,
});

const outcomeBody = (over: Record<string, unknown> = {}) => ({ document_id: D, runs: [], current: null, raw_reply: null, ...over });

interface Server {
  docs: () => unknown;
  info?: () => unknown;
  outcome?: () => Response | unknown;
  bodies?: Record<string, unknown[]>;
  runs?: Record<string, unknown>;
  onEstimate?: () => Response;
  onConfirm?: (body: unknown) => Response;
  onRetry?: () => Response;
  calls: string[];
}

function install(s: Server) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      s.calls.push(`${method} ${url}`);
      if (url === "/api/v1/session") return Promise.resolve(json({ csrf_token: "t".repeat(43) }));
      if (url.endsWith("/extraction")) return Promise.resolve(json(report));
      if (url.includes("/extraction/") || url.includes("/extraction-candidates")) return Promise.resolve(json({ items: [], page: { limit: 25, next_cursor: null }, total: 0 }));
      if (url.endsWith("/processing/documents")) return Promise.resolve(json({ project_id: P, items: [s.docs()], provider_info: (s.info ?? (() => providerInfo()))() }));
      if (url.endsWith(`/documents/${D}/outcome`)) {
        const o = (s.outcome ?? (() => outcomeBody()))();
        return Promise.resolve(o instanceof Response ? o : json(o));
      }
      if (url.endsWith("/runs/estimates") && method === "POST") {
        (s.bodies ??= {})["estimate"] = [...(s.bodies["estimate"] ?? []), JSON.parse(String(init?.body))];
      }
      if (url.endsWith("/runs/estimates") && method === "POST") return Promise.resolve((s.onEstimate ?? (() => json(estimate(), 201)))());
      if (url.endsWith("/confirm")) return Promise.resolve((s.onConfirm ?? (() => json({ ...estimate(), status: "queued" }, 202)))(JSON.parse(String(init?.body))));
      if (url.endsWith("/retry")) return Promise.resolve((s.onRetry ?? (() => json(estimate({}, RUN2), 201)))());
      const m = /\/runs\/([^/]+)$/.exec(url);
      if (m !== null && s.runs?.[m[1] ?? ""] !== undefined) return Promise.resolve(json(s.runs[m[1] ?? ""]));
      return Promise.resolve(json({ error: { code: "not_found", message: "nope" } }, 404));
    }),
  );
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function open() {
  const view = render(<EvidencePanel projectId={P} doc={doc} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /Inspect extraction for completion\.pdf/ }));
  return { user, view };
}

describe("model processing: no native parser", () => {
  it("replaces the unsupported dead end with the Process action and a non-clickable-through estimate", async () => {
    const s: Server = { docs: () => state(), calls: [] };
    install(s);
    const { user } = await open();
    expect(await screen.findByText("No native parser; model processing available")).toBeInTheDocument();
    expect(screen.queryByText(/^Unsupported/)).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /Process with model: completion\.pdf/ }));

    // estimate opens; nothing was confirmed or spent yet
    const dialog = await screen.findByRole("dialog", { name: /Model processing estimate for completion\.pdf/ });
    expect(s.calls.some((c) => c.endsWith("/confirm"))).toBe(false);
    expect(within(dialog).getByText(/5 \(pages 1-5 of 12\)/)).toBeInTheDocument();
    expect(within(dialog).getByText(/8,000 input, 2,000 output/)).toBeInTheDocument();
    expect(within(dialog).getByText("USD 0.007400")).toBeInTheDocument();
    expect(within(dialog).getByText(/USD 4\.5 of USD 5 total cap/)).toBeInTheDocument();
    expect(within(dialog).getByText(/confirming makes live model calls/)).toBeInTheDocument();

    // Cancel spends nothing and returns focus to the Process button
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(s.calls.some((c) => c.endsWith("/confirm"))).toBe(false);
    await waitFor(() => expect(screen.getByRole("button", { name: /Process with model: completion\.pdf/ })).toHaveFocus());
  });

  it("confirm echoes the estimate, then moves focus to the status line", async () => {
    let status = "not_started";
    let body: unknown = null;
    const s: Server = {
      docs: () => state({ processing_status: status, last_run_id: status === "not_started" ? null : RUN, state_text: "model processing confirmed and queued" }),
      runs: { [RUN]: { ...estimate(), status: "queued" } },
      onConfirm: (b) => {
        body = b;
        status = "queued";
        return json({ ...estimate(), status: "queued" }, 202);
      },
      calls: [],
    };
    install(s);
    const { user } = await open();
    await user.click(await screen.findByRole("button", { name: /Process with model: completion\.pdf/ }));
    await user.click(await screen.findByRole("button", { name: /Confirm and start \(USD 0\.007400\)/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(body).toEqual({ estimated_usd: "0.007400" });
    const status_ = await screen.findByText(/Model processing confirmed and queued/);
    expect(status_).toHaveAttribute("role", "status");
    await waitFor(() => expect(status_).toHaveFocus());
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Process with model/ })).not.toBeInTheDocument();
  });

  it("an estimate that does not fit the budget cannot be confirmed", async () => {
    install({ docs: () => state(), calls: [], onEstimate: () => json(estimate({ fits_budget: false, confirmable: false }), 201) });
    const { user } = await open();
    await user.click(await screen.findByRole("button", { name: /Process with model/ }));
    expect(await screen.findByText(/does not fit the remaining budget/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Confirm and start/ })).toBeDisabled();
  });

  it("a confirm that the server rejects shows the error in the dialog and says nothing was spent", async () => {
    install({
      docs: () => state(),
      calls: [],
      onConfirm: () => json({ error: { code: "conflict", message: "estimate changed" } }, 409),
    });
    const { user } = await open();
    await user.click(await screen.findByRole("button", { name: /Process with model/ }));
    await user.click(await screen.findByRole("button", { name: /Confirm and start/ }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/estimate changed/);
    expect(alert).toHaveTextContent(/Nothing was spent/);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("an estimate request error is an alert, no dialog", async () => {
    install({ docs: () => state(), calls: [], onEstimate: () => json({ error: { code: "validation_failed", message: "page range required" } }, 422) });
    const { user } = await open();
    await user.click(await screen.findByRole("button", { name: /Process with model/ }));
    expect(await screen.findByText(/The estimate could not be created: page range required/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("a document over the page cap needs a valid range before an estimate is requested", async () => {
    const s: Server = { docs: () => state({ over_page_cap: true, page_count: 800 }), calls: [] };
    install(s);
    const { user } = await open();
    const last = await screen.findByLabelText("Last page");
    await user.clear(last);
    await user.type(last, "900");
    await user.click(screen.getByRole("button", { name: /Process with model/ }));
    expect(await screen.findByText(/The document has 800 pages/)).toBeInTheDocument();
    expect(s.calls.some((c) => c.endsWith("/runs/estimates"))).toBe(false);
  });

  it("re-reads the state when the native parse settles after the panel opened", async () => {
    let native = "pending_extraction";
    install({ docs: () => state({ native_state: native, no_native_parser: native === "unsupported" }), calls: [] });
    const pending = { ...doc, extraction_state: "pending_extraction" } as unknown as SourceDocumentItem;
    const view = render(<EvidencePanel projectId={P} doc={pending} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Inspect extraction for completion\.pdf/ }));
    await waitFor(() => expect(screen.getByText(/Stored and verified|Unsupported|No native parser/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Process with model/ })).not.toBeInTheDocument();
    native = "unsupported";
    view.rerender(<EvidencePanel projectId={P} doc={{ ...doc, extraction_state: "unsupported" } as unknown as SourceDocumentItem} />);
    expect(await screen.findByRole("button", { name: /Process with model/ })).toBeInTheDocument();
  });

  it("a text file stays not processable and offers no Process action", async () => {
    install({
      docs: () => state({ processable: false, not_processable_reason: "not_a_pdf", page_count: null, state_text: "not processable: not a pdf" }),
      calls: [],
    });
    await open();
    expect(await screen.findByText(/Model processing is not possible: only PDF files can be read by the model/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Process with model/ })).not.toBeInTheDocument();
  });
});

describe("model-read result", () => {
  const processed = (r: unknown, over: Record<string, unknown> = {}) =>
    state({ processing_status: "processed", last_run_id: RUN, model_read: r, state_text: "model read finished", ...over });
  const runOk = { ...estimate(), status: "succeeded" };

  it("shows category, tags and identities with page and quote, labelled model-read, unverified", async () => {
    install({
      docs: () =>
        processed(read({ identities: [identity(), identity({ proposal_id: "p2", name_as_written: "15/9-F-1 C", page: 3, quote: "Well 15/9-F-1 C", resolution: "linked", wellbore_id: "w", wellbore_key: "15/9-F-1 C" })] })),
      runs: { [RUN]: runOk },
      calls: [],
    });
    await open();
    const result = await screen.findByLabelText("Model-read result");
    expect(within(result).getAllByText("Model-read, unverified").length).toBeGreaterThanOrEqual(3);
    expect(within(result).getByText("Model-suggested category (unverified)")).toBeInTheDocument();
    expect(within(result).getByText("Completion equipment")).toBeInTheDocument();
    const tags = within(result).getByRole("list", { name: "Model-read tags" });
    expect(within(tags).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["packer", "tubing"]);
    expect(within(result).getByText("Evidence on page 2:")).toBeInTheDocument();
    expect(within(result).getByText("Wellbore: NO 15/9-F-12 H")).toBeInTheDocument();
    expect(within(result).getByText("Evidence on page 3:")).toBeInTheDocument();
    // linked vs unresolved is stated in words, not colour
    expect(within(result).getByText(/Unresolved \(no existing wellbore matches exactly\)/)).toBeInTheDocument();
    expect(within(result).getByText("Linked to wellbore 15/9-F-1 C")).toBeInTheDocument();
  });

  it("keeps the user's category effective and shows the suggestion separately", async () => {
    install({ docs: () => processed(read(), { user_labels: ["trajectory"] }), runs: { [RUN]: runOk }, calls: [] });
    await open();
    const result = await screen.findByLabelText("Model-read result");
    expect(within(result).getByText("Your category (effective)")).toBeInTheDocument();
    expect(within(result).getByText("Trajectory")).toBeInTheDocument();
    expect(within(result).getByText("Model suggestion (unverified, not applied)")).toBeInTheDocument();
    expect(within(result).getByText("Completion equipment")).toBeInTheDocument();
  });

  it("names the fallback bucket Others (unclassified)", async () => {
    install({ docs: () => processed(read({ category: "general_report", unclassified: true, tags: ["unclassified"] })), runs: { [RUN]: runOk }, calls: [] });
    await open();
    const result = await screen.findByLabelText("Model-read result");
    expect(within(result).getByText("Others (unclassified)")).toBeInTheDocument();
    expect(within(result).queryByText("General report")).not.toBeInTheDocument();
  });

  it("no identity is a non-blocking warning; the document, category and tags stay visible", async () => {
    install({
      docs: () =>
        processed(read({ identities: [], warnings: [{ code: "no_wellbore_identity", message: "No wellbore identity found.", count: 1 }] })),
      runs: { [RUN]: runOk },
      calls: [],
    });
    await open();
    const warn = await screen.findByText(/does not block anything/);
    expect(warn.closest("[role=status]")).not.toBeNull();
    expect(screen.getAllByText(/No wellbore identity found/).length).toBeGreaterThan(0);
    expect(screen.getByText("Completion equipment")).toBeInTheDocument();
    expect(screen.queryByText(/Wellbore identities proposed/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows dropped-identity warnings with their counts", async () => {
    install({
      docs: () => processed(read({ warnings: [{ code: "identity_quote_not_found", message: "A quote was not on the page.", count: 2 }] })),
      runs: { [RUN]: runOk },
      calls: [],
    });
    await open();
    const list = await screen.findByRole("list", { name: "Model-read warnings" });
    expect(list).toHaveTextContent(/identity_quote_not_found/);
    expect(list).toHaveTextContent(/2x/);
  });

  it("a cache hit says the result was reused with no model call", async () => {
    const hit = { ...estimate(), status: "succeeded", documents: [{ ...estimate().documents[0], state: "processed", cache_hit: true }] };
    install({ docs: () => processed(read()), runs: { [RUN]: hit }, calls: [] });
    await open();
    expect(await screen.findByText("Reused stored result, no model call.")).toBeInTheDocument();
  });

  it("a stub run that stored nothing is not presented as a result", async () => {
    install({ docs: () => processed(null, { state_text: "stub processing finished; no data was extracted" }), runs: { [RUN]: runOk }, calls: [] });
    await open();
    expect(await screen.findByText(/This run stored no model-read result/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Model-read result")).not.toBeInTheDocument();
  });
});

describe("typed failures and retry", () => {
  const cases: [string, RegExp][] = [
    ["provider_refused", /Model refusal/],
    ["provider_truncated", /Truncated output/],
    ["provider_malformed", /Malformed output/],
    ["provider_error", /Provider error/],
  ];
  for (const [code, label] of cases) {
    it(`${code}: names the failure, stores no result, and retries through a new estimate and confirm`, async () => {
      const s: Server = {
        docs: () => state({ processing_status: "failed", last_run_id: RUN, retryable: true, state_text: `model processing failed (${code})` }),
        runs: { [RUN]: runWith({ state: "failed", failure_code: code, retryable: true, failure_message: "detail from server" }) },
        calls: [],
      };
      install(s);
      const { user } = await open();
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(label);
      expect(alert).toHaveTextContent(/Nothing was stored/);
      expect(alert).toHaveTextContent(/detail from server/);
      expect(alert).toHaveTextContent(/retryable/);
      expect(screen.queryByLabelText("Model-read result")).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: /Retry model processing: completion\.pdf/ }));
      expect(s.calls).toContain(`POST /api/v1/projects/${P}/processing/runs/${RUN}/retry`);
      expect(await screen.findByRole("dialog", { name: /Model processing estimate/ })).toBeInTheDocument();
      // retry does not start anything until the separate confirm
      expect(s.calls.some((c) => c.endsWith("/confirm"))).toBe(false);
      await user.click(screen.getByRole("button", { name: /Confirm and start/ }));
      expect(s.calls).toContain(`POST /api/v1/projects/${P}/processing/runs/${RUN2}/confirm`);
    });
  }

  it("a budget-exceeded run failure is named and not marked successful", async () => {
    install({
      docs: () => state({ processing_status: "failed", last_run_id: RUN, retryable: true, state_text: "model processing failed (budget_stop)" }),
      runs: { [RUN]: { ...runWith({ state: "failed", failure_code: "budget_stop", retryable: true }), error_code: "budget_stop" } },
      calls: [],
    });
    await open();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/Budget exceeded/);
    expect(alert).toHaveTextContent(/Nothing was marked successful/);
    expect(screen.queryByText("Processed")).not.toBeInTheDocument();
  });

  it("a non-retryable failure offers no retry button", async () => {
    install({
      docs: () => state({ processing_status: "failed", last_run_id: RUN, retryable: false, state_text: "failed" }),
      runs: { [RUN]: runWith({ state: "failed", failure_code: "document_unavailable" }) },
      calls: [],
    });
    await open();
    expect(await screen.findByText(/No retry is offered/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry model processing/ })).not.toBeInTheDocument();
  });

  it("a failed state load is an error with a keyboard retry", async () => {
    let fail = true;
    install({ docs: () => state(), calls: [] });
    const real = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).endsWith("/processing/documents") && fail) return Promise.resolve(json({ error: { code: "internal", message: "boom" } }, 500));
        return real(input, init);
      }),
    );
    const { user } = await open();
    expect(await screen.findByText(/Model processing state could not be loaded: boom/)).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Retry loading model processing state" }));
    expect(await screen.findByRole("button", { name: /Process with model/ })).toBeInTheDocument();
  });
});

// TASK-072 AC-2..AC-6 (UI side): re-process in every state, force opt-in, history, raw reply, stub, misconfiguration.
const processedState = (r: unknown, over: Record<string, unknown> = {}) =>
  state({ processing_status: "processed", last_run_id: RUN, model_read: r, state_text: "model read finished", ...over });
const reprocessBtn = () => screen.findByRole("button", { name: /Re-process with model: completion\.pdf/ });

describe("re-process is always available", () => {
  const cases: [string, Record<string, unknown>][] = [
    ["processed with a model-read", processedState(read())],
    ["processed, no wellbore identity", processedState(read({ identities: [], warnings: [{ code: "no_wellbore_identity", message: "none", count: 1 }] }))],
    ["processed stub run without a result", processedState(null, { state_text: "stub processing finished; no data was extracted" })],
    ["failed and not retryable", state({ processing_status: "failed", last_run_id: RUN, retryable: false, state_text: "failed" })],
    ["cancelled", state({ processing_status: "cancelled", last_run_id: RUN, retryable: false, state_text: "cancelled" })],
  ];
  for (const [name, docs] of cases) {
    it(`${name}: Re-process with model... opens the estimate`, async () => {
      const s: Server = { docs: () => docs, calls: [], runs: { [RUN]: { ...estimate(), status: "succeeded" } } };
      install(s);
      const { user } = await open();
      await user.click(await reprocessBtn());
      expect(await screen.findByRole("dialog", { name: /Model processing estimate/ })).toBeInTheDocument();
      expect(s.calls.some((c) => c.endsWith("/confirm"))).toBe(false);
    });
  }

  it("a retryable failure offers both Retry and Re-process; a first run says Process", async () => {
    install({ docs: () => state({ processing_status: "failed", last_run_id: RUN, retryable: true, state_text: "failed" }), calls: [] });
    await open();
    expect(await screen.findByRole("button", { name: /Retry model processing/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Re-process with model/ })).toBeInTheDocument();
    cleanup();
    install({ docs: () => state(), calls: [] });
    await open();
    expect(await screen.findByRole("button", { name: "Process with model: completion.pdf" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Re-process/ })).not.toBeInTheDocument();
  });

  it("is not offered while a run is active or for a file that is not processable", async () => {
    install({ docs: () => state({ processing_status: "running", last_run_id: RUN, state_text: "running" }), runs: { [RUN]: { ...estimate(), status: "running" } }, calls: [] });
    await open();
    await screen.findAllByText("Running");
    expect(screen.queryByRole("button", { name: /rocess with model/ })).not.toBeInTheDocument();
  });

  it("a document with a result sends force=true by default; the opt-in checkbox sends force=false and re-estimates", async () => {
    const s: Server = { docs: () => processedState(read()), calls: [], bodies: {}, runs: { [RUN]: { ...estimate(), status: "succeeded" } } };
    install(s);
    const { user } = await open();
    await user.click(await reprocessBtn());
    const dialog = await screen.findByRole("dialog");
    const box = within(dialog).getByRole("checkbox", { name: "Reuse the stored result if the document is unchanged (no model call)" });
    expect(box).not.toBeChecked();
    expect(s.bodies?.["estimate"]).toEqual([{ documents: [{ document_id: D }], force: true }]);
    await user.click(box);
    await waitFor(() => expect(s.bodies?.["estimate"]).toHaveLength(2));
    expect(s.bodies?.["estimate"]?.[1]).toEqual({ documents: [{ document_id: D }], force: false });
    await waitFor(() => expect(within(screen.getByRole("dialog")).getByRole("checkbox")).toBeChecked());
    await user.click(within(screen.getByRole("dialog")).getByRole("checkbox"));
    await waitFor(() => expect(s.bodies?.["estimate"]).toHaveLength(3));
    expect(s.bodies?.["estimate"]?.[2]).toEqual({ documents: [{ document_id: D }], force: true });
  });

  it("a never-processed document sends force=false and offers no reuse checkbox", async () => {
    const s: Server = { docs: () => state(), calls: [], bodies: {} };
    install(s);
    const { user } = await open();
    await user.click(await screen.findByRole("button", { name: /Process with model/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(s.bodies?.["estimate"]).toEqual([{ documents: [{ document_id: D }], force: false }]);
  });

  it("the dialog names provider and model and says whether money is spent", async () => {
    install({ docs: () => state(), calls: [] });
    const { user } = await open();
    await user.click(await screen.findByRole("button", { name: /Process with model/ }));
    const live = await screen.findByRole("dialog");
    const facts = within(live).getByLabelText("Provider");
    expect(facts).toHaveTextContent("meta");
    expect(facts).toHaveTextContent("muse-spark");
    expect(facts).toHaveTextContent(/Yes: confirming spends provider budget/);
    expect(within(live).getByText(/USD 4\.5 of USD 5 total cap/)).toBeInTheDocument();
    await user.click(within(live).getByRole("button", { name: "Cancel" }));
    cleanup();
    install({ docs: () => state(), calls: [], info: () => providerInfo({ active: "stub", requested: "stub", status: "stub", model: "stub", spends_money: false }), onEstimate: () => json(estimate({ provider: "stub", model: "stub", spends_money: false, estimated_usd: "0" }), 201) });
    const u2 = (await open()).user;
    await u2.click(await screen.findByRole("button", { name: /Process with model/ }));
    const stub = await screen.findByRole("dialog");
    expect(within(stub).getByLabelText("Provider")).toHaveTextContent(/No: this run spends nothing/);
    expect(within(stub).getByText(/FIELDLENS_PROCESSING_PROVIDER=meta/)).toBeInTheDocument();
  });
});

describe("model processing history", () => {
  const history = [
    runEntry({ run_id: RUN2, forced: true, cache_hit: false, finished_at: "2026-11-02T11:00:09Z", started_at: "2026-11-02T11:00:01Z", warnings: [{ code: "identity_quote_not_found", message: "A quote was not on the page.", count: 2 }] }),
    runEntry({ run_id: "44444444-4444-4444-8444-444444444444", cache_hit: true, input_tokens: null, output_tokens: null, usd_actual: "0" }),
    runEntry({ run_id: "55555555-5555-4555-8555-555555555555", state: "failed", failure_code: "provider_refused", failure_message: "policy", usd_actual: "0.001000" }),
  ];

  it("lists runs newest first with provider/model, times, pages, tokens, USD, cache, forced, failure and warnings", async () => {
    install({ docs: () => processedState(read()), calls: [], outcome: () => outcomeBody({ runs: history, current: read() }) });
    await open();
    const list = await screen.findByRole("list", { name: "Model runs, newest first" });
    const items = within(list).getAllByRole("listitem").filter((li) => li.getAttribute("aria-label")?.startsWith("Run "));
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveAttribute("aria-label", `Run ${RUN2}`);
    expect(items[0]).toHaveTextContent("meta / muse-spark");
    expect(items[0]).toHaveTextContent("Forced re-read");
    expect(items[0]).toHaveTextContent("2026-11-02 11:00:01Z");
    expect(items[0]).toHaveTextContent("5 (window 1-5)");
    expect(items[0]).toHaveTextContent("8,123 input, 456 output");
    expect(items[0]).toHaveTextContent("USD 0.007100");
    expect(items[0]).toHaveTextContent(/identity_quote_not_found.*2x/);
    expect(items[1]).toHaveTextContent("Reused, no model call");
    expect(items[1]).toHaveTextContent("not recorded input, not recorded output");
    expect(items[2]).toHaveTextContent("Failed");
    expect(items[2]).toHaveTextContent("Model refusal");
    expect(items[2]).toHaveTextContent("provider_refused");
    expect(items[2]).toHaveTextContent("policy");
  });

  it("is loaded lazily only when the panel is open and shows a loading state", async () => {
    let release: (r: Response) => void = () => undefined;
    const s: Server = { docs: () => processedState(read()), calls: [], outcome: () => new Response() };
    install(s);
    const base = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn((i: RequestInfo | URL, init?: RequestInit) =>
        String(i).endsWith("/outcome") ? new Promise<Response>((r) => (release = r)) : base(i, init),
      ),
    );
    render(<EvidencePanel projectId={P} doc={doc} />);
    expect(s.calls.some((c) => c.endsWith("/outcome"))).toBe(false);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Inspect extraction for completion\.pdf/ }));
    expect(await screen.findByText("Loading model processing history…")).toBeInTheDocument();
    release(json(outcomeBody({ runs: history })));
    expect(await screen.findByRole("list", { name: "Model runs, newest first" })).toBeInTheDocument();
  });

  it("an empty history is stated", async () => {
    install({ docs: () => processedState(read()), calls: [], outcome: () => outcomeBody() });
    await open();
    expect(await screen.findByText("No model runs yet")).toBeInTheDocument();
  });

  it("an outcome error is announced with a retry that reloads", async () => {
    let fail = true;
    install({ docs: () => processedState(read()), calls: [], outcome: () => (fail ? json({ error: { code: "internal", message: "boom" } }, 500) : outcomeBody({ runs: history })) });
    const { user } = await open();
    expect(await screen.findByText(/The model processing history could not be loaded: boom/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Retry loading model processing history" }));
    expect(await screen.findByRole("list", { name: "Model runs, newest first" })).toBeInTheDocument();
  });

  it("refreshes the history after a run finishes", async () => {
    let status = "running";
    let runs = [runEntry({ state: "running", finished_at: null })];
    install({
      docs: () => processedState(read(), { processing_status: status }),
      calls: [],
      runs: { [RUN]: { ...estimate(), status: "running" } },
      outcome: () => outcomeBody({ runs }),
    });
    render(<EvidencePanel projectId={P} doc={doc} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Inspect extraction for completion\.pdf/ }));
    expect(await screen.findByText("Running", { selector: "li *" })).toBeInTheDocument();
    status = "processed";
    runs = [runEntry({ run_id: RUN2, state: "processed" })];
    expect(await screen.findByText("Processed", { selector: "li *" }, { timeout: 6000 })).toBeInTheDocument();
  }, 10_000);
});

describe("raw model reply", () => {
  const hostile = '<img src=x onerror="alert(1)"><script>alert(2)</script> {"category":"x"}';
  const withRaw = (raw: unknown) => ({ docs: () => processedState(read()), calls: [], outcome: () => outcomeBody({ runs: [runEntry()], current: read(), raw_reply: raw }) }) as Server;

  it("is collapsed by default, keyboard-toggleable, plain text and never HTML", async () => {
    install(withRaw({ text: hostile, truncated: false, max_bytes: 8192 }));
    const { user } = await open();
    const toggle = await screen.findByRole("button", { name: /Show model reply \(raw\)/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const region = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
    expect(region).not.toBeNull();
    expect(region).not.toBeVisible();
    expect(screen.queryByText(/onerror/)).not.toBeInTheDocument();
    toggle.focus();
    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveTextContent("Hide model reply (raw)");
    const pre = await screen.findByText(hostile);
    expect(pre.tagName).toBe("PRE");
    expect(pre.querySelector("img, script")).toBeNull();
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(screen.getByText(/Untrusted model output, shown as plain text/)).toBeInTheDocument();
    expect(screen.queryByText(/Truncated: only the first/)).not.toBeInTheDocument();
    await user.keyboard(" ");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("states the 8 KiB truncation", async () => {
    install(withRaw({ text: "abc", truncated: true, max_bytes: 8192 }));
    const { user } = await open();
    await user.click(await screen.findByRole("button", { name: /Show model reply/ }));
    expect(screen.getByText(/Truncated: only the first 8 KiB \(8,192 bytes\)/)).toBeInTheDocument();
  });

  it("is absent when no reply was recorded", async () => {
    install(withRaw(null));
    await open();
    await screen.findByRole("list", { name: "Model runs, newest first" });
    expect(screen.queryByRole("button", { name: /model reply/ })).not.toBeInTheDocument();
  });
});

describe("stub honesty and provider configuration", () => {
  const stubInfo = () => providerInfo({ active: "stub", requested: "stub", status: "stub", model: "stub", spends_money: false });
  const stubRun = runEntry({ provider: "stub", model: "stub", usd_actual: "0", input_tokens: null, output_tokens: null, message: "Stub provider: no model was called and no data is extracted." });

  it("a stub run is a neutral Stub run, not Processed, with the no-model text and the prefixed setting", async () => {
    install({ docs: () => processedState(null, { state_text: "stub processing finished" }), calls: [], info: stubInfo, outcome: () => outcomeBody({ runs: [stubRun] }) });
    await open();
    const notes = await screen.findAllByText(/Stub provider: no model was called and no data is extracted\. Set FIELDLENS_PROCESSING_PROVIDER=meta to use the live model\./, { selector: "p" });
    expect(notes.length).toBeGreaterThanOrEqual(2); // panel callout and the run in the history
    expect(notes.some((n) => n.closest("[role=status]") !== null)).toBe(true);
    expect(screen.getAllByText("Stub run").length).toBeGreaterThan(0);
    expect(screen.queryByText("Processed", { exact: true })).not.toBeInTheDocument();
    expect(screen.getByText(/Provider:/)).toHaveTextContent("stub / stub (stub, no model call)");
  });

  it("a live provider is shown compactly", async () => {
    install({ docs: () => state(), calls: [] });
    await open();
    expect(await screen.findByText(/Provider:/)).toHaveTextContent("meta / muse-spark (live, spends money)");
  });

  it("provider_misconfigured: a non-blocking alert names missing settings and the action is disabled with a reason", async () => {
    install({
      docs: () => state(),
      calls: [],
      info: () => providerInfo({ active: "stub", status: "provider_misconfigured", missing: ["FIELDLENS_PROCESSING_META_API_KEY", "FIELDLENS_PROCESSING_RUN_CAP_USD"] }),
    });
    await open();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("FIELDLENS_PROCESSING_META_API_KEY");
    expect(alert).toHaveTextContent("FIELDLENS_PROCESSING_RUN_CAP_USD");
    const btn = screen.getByRole("button", { name: /Process with model/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAccessibleDescription(/the live model provider is not configured/);
  });

  it("a 409 provider_misconfigured on estimate is explained, no dialog opens", async () => {
    const body = { error: { code: "conflict", message: "provider is not configured", details: { reason: "provider_misconfigured", missing: ["FIELDLENS_PROCESSING_META_API_KEY"] } } };
    install({ docs: () => state(), calls: [], onEstimate: () => json(body, 409) });
    const { user } = await open();
    await user.click(await screen.findByRole("button", { name: /Process with model/ }));
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => /missing FIELDLENS_PROCESSING_META_API_KEY.*Nothing was started and nothing was spent/.test(a.textContent ?? ""))).toBe(true);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("a 409 provider_misconfigured on confirm is explained inside the dialog", async () => {
    const body = { error: { code: "conflict", message: "provider is not configured", details: { reason: "provider_misconfigured", missing: ["FIELDLENS_PROCESSING_RUN_CAP_USD"] } } };
    install({ docs: () => state(), calls: [], onConfirm: () => json(body, 409) });
    const { user } = await open();
    await user.click(await screen.findByRole("button", { name: /Process with model/ }));
    await user.click(await screen.findByRole("button", { name: /Confirm and start/ }));
    const alert = await within(screen.getByRole("dialog")).findByRole("alert");
    expect(alert).toHaveTextContent(/missing FIELDLENS_PROCESSING_RUN_CAP_USD/);
    expect(alert).toHaveTextContent(/nothing was spent/);
  });

  it("confirming a re-process returns focus to the status line", async () => {
    let status = "processed";
    install({
      docs: () => processedState(read(), { processing_status: status, state_text: status === "queued" ? "confirmed and queued" : "model read finished" }),
      calls: [],
      runs: { [RUN]: { ...estimate(), status: "succeeded" } },
      onConfirm: () => {
        status = "queued";
        return json({ ...estimate(), status: "queued" }, 202);
      },
    });
    const { user } = await open();
    await user.click(await reprocessBtn());
    await user.click(await screen.findByRole("button", { name: /Confirm and start/ }));
    const st = await screen.findByText(/Confirmed and queued/);
    await waitFor(() => expect(st).toHaveFocus());
  });
});
