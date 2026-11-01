// Component tests with a stubbed fetch and a fake XMLHttpRequest. They prove client behavior
// (request shape, limits, error surfacing, status wording, polling cleanup). Storage, hashing and
// restart behavior are proven by the backend tests and tests/e2e/uploads.spec.ts, not here.
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import { render } from "./render";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SourcesPanel } from "../src/features/uploads/SourcesPanel";
import { MAX_FILE_BYTES } from "../src/features/uploads/api";

const P = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const R1 = "11111111-1111-4111-8111-111111111111";
const R2 = "22222222-2222-4222-8222-222222222222";
const D1 = "d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1";
const D2 = "d2d2d2d2-d2d2-4d2d-8d2d-d2d2d2d2d2d2";
const J1 = "j1j1j1j1-j1j1-4j1j-8j1j-j1j1j1j1j1j1";
const SHA = "a".repeat(64);

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}
const envelope = (code: string, message: string, details?: Record<string, unknown>) => ({
  error: { code, message, request_id: "req-7", details: details ?? null },
});

function revision(over: Record<string, unknown> = {}) {
  return {
    source_revision_id: R1,
    project_id: P,
    manifest_hash: "f".repeat(64),
    created_at: "2026-10-29T12:00:00Z",
    status: "ready",
    parent_source_revision_id: null,
    coverage: null,
    is_latest: true,
    member_count: 2,
    stored_count: 2,
    quarantined_count: 0,
    pending_extraction_count: 1,
    unsupported_count: 1,
    job_id: J1,
    job_status: "succeeded",
    ...over,
  };
}
function document(over: Record<string, unknown> = {}) {
  return {
    document_id: D1,
    project_id: P,
    original_filename: "wells.csv",
    sha256: SHA,
    size_bytes: 2048,
    created_at: "2026-10-29T12:00:00Z",
    detected_media_type: "text/csv",
    format_family: "csv",
    origin_metadata: {},
    storage_state: "stored",
    extraction_state: "pending_extraction",
    processing_detail: null,
    classification: {
      user_categories: ["trajectory"],
      suggested_categories: [],
      tags: ["pilot"],
      categories_origin: "upload_hint",
      classification_method: "none",
      classification_version: "1",
      metadata_version: 3,
      updated_at: "2026-10-29T12:00:00Z",
    },
    replaces_document_id: null,
    source_revision_id: R1,
    ...over,
  };
}
function job(over: Record<string, unknown> = {}) {
  return {
    job_id: J1,
    project_id: P,
    kind: "storage_verification",
    source_revision_id: R1,
    status: "succeeded",
    stage: null,
    progress: { processed: 2, total: 2, unit: "files" },
    cancel_requested: false,
    attempts: [
      { attempt_no: 1, status: "failed", stage: "hashing", fencing_token: 1, started_at: "2026-10-29T12:00:00Z", heartbeat_at: "2026-10-29T12:00:01Z", ended_at: "2026-10-29T12:00:02Z", error_code: "io_error" },
      { attempt_no: 2, status: "succeeded", stage: null, fencing_token: 2, started_at: "2026-10-29T12:00:03Z", heartbeat_at: "2026-10-29T12:00:04Z", ended_at: "2026-10-29T12:00:05Z", error_code: null },
    ],
    result: { result_kind: "storage_verification", documents: 2, stored: 2, quarantined: 0, pending_extraction: 1, unsupported: 1, extraction_performed: false },
    error: null,
    created_at: "2026-10-29T12:00:00Z",
    updated_at: "2026-10-29T12:00:05Z",
    finished_at: "2026-10-29T12:00:05Z",
    ...over,
  };
}
const page = (...items: unknown[]) => ({ items, page: { limit: 50, next_cursor: null } });

type Handler = (url: string, init?: RequestInit) => Response | undefined;
function install(handler: Handler) {
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/v1/session") return Promise.resolve(json({ csrf_token: "t".repeat(43) }));
    const out = handler(url, init);
    if (out === undefined) throw new Error(`unexpected request ${init?.method ?? "GET"} ${url}`);
    return Promise.resolve(out);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
const count = (fn: ReturnType<typeof install>, part: string) =>
  fn.mock.calls.filter(([u]) => String(u).includes(part)).length;

const emptyHandler: Handler = (url) => {
  if (url.includes("/source-revisions")) return json(page());
};

class FakeXhr {
  static all: FakeXhr[] = [];
  method = "";
  url = "";
  headers: Record<string, string> = {};
  body: FormData | null = null;
  aborted = false;
  status = 0;
  responseText = "";
  upload: { onprogress: ((e: ProgressEvent) => void) | null; onload: (() => void) | null } = { onprogress: null, onload: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;
  constructor() {
    FakeXhr.all.push(this);
  }
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k.toLowerCase()] = v;
  }
  getResponseHeader() {
    return null;
  }
  send(body: FormData) {
    this.body = body;
  }
  abort() {
    this.aborted = true;
    this.onabort?.();
  }
  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ loaded, total, lengthComputable: true } as ProgressEvent);
    if (loaded >= total) this.upload.onload?.();
  }
  respond(status: number, body: unknown) {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
  fail() {
    this.onerror?.();
  }
}
const lastXhr = () => FakeXhr.all[FakeXhr.all.length - 1] as FakeXhr;
const csv = () => new File(["well,md\nA,1\n"], "wells.csv", { type: "text/csv" });
const txt = () => new File(["notes"], "notes.txt", { type: "text/plain" });

function panel(latest: string | null = null, onProjectChanged = vi.fn()) {
  render(<SourcesPanel projectId={P} latestRevisionId={latest} onProjectChanged={onProjectChanged} />);
  return onProjectChanged;
}

beforeEach(() => {
  FakeXhr.all = [];
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function selectAndSubmit(user: ReturnType<typeof userEvent.setup>, files: File[]) {
  await user.upload(screen.getByLabelText("Choose files"), files);
  await user.click(screen.getByRole("button", { name: /^Upload \d+ file/ }));
}

describe("upload form", () => {
  it("sends metadata first, files aligned, expected parent and hints; shows progress and success", async () => {
    const fetchFn = install(emptyHandler);
    const changed = panel(null);
    const user = userEvent.setup();
    expect(await screen.findByText(/no source files yet/i)).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Choose files"), [csv(), txt()]);
    await user.selectOptions(screen.getByLabelText(/Category hint for wells\.csv/), "trajectory");
    await user.click(screen.getByRole("button", { name: "Upload 2 file(s)" }));

    const xhr = lastXhr();
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe(`/api/v1/projects/${P}/imports`);
    expect(xhr.headers["x-fieldlens-token"]).toBe("t".repeat(43));
    const keys = Array.from(xhr.body?.keys() ?? []);
    expect(keys).toEqual(["metadata", "files", "files"]);
    const meta = JSON.parse(String(xhr.body?.get("metadata"))) as {
      expected_parent_source_revision_id: string | null;
      idempotency_key: string;
      files: { categories: string[]; tags: string[]; replaces_document_id: null }[];
    };
    expect(meta.expected_parent_source_revision_id).toBeNull();
    expect(meta.idempotency_key).toMatch(/^[A-Za-z0-9._:~-]{1,128}$/);
    expect(meta.files).toEqual([
      { categories: ["trajectory"], tags: [], replaces_document_id: null },
      { categories: [], tags: [], replaces_document_id: null },
    ]);
    expect(xhr.body?.getAll("files").map((f) => (f as File).name)).toEqual(["wells.csv", "notes.txt"]);

    act(() => xhr.progress(50, 100));
    expect(await screen.findByText(/50% sent/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abort upload" })).toBeInTheDocument();
    const before = count(fetchFn, "/source-revisions");
    act(() =>
      xhr.respond(202, {
        source_revision_id: R1, job_id: J1, status: "staging", deduplicated: false, replayed: false,
        document_ids: [D1, D2], created_document_ids: [D1, D2],
      }),
    );
    expect(await screen.findByText(/Import accepted: 2 new file/)).toBeInTheDocument();
    expect(screen.getByText(/not extraction or engineering validation/)).toBeInTheDocument();
    await waitFor(() => expect(count(fetchFn, "/source-revisions")).toBeGreaterThan(before));
    expect(changed).toHaveBeenCalled();
  });

  it("reports an idempotent replay honestly (HTTP 200)", async () => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv()]);
    act(() =>
      lastXhr().respond(200, {
        source_revision_id: R1, job_id: J1, status: "ready", deduplicated: false, replayed: true,
        document_ids: [D1], created_document_ids: [],
      }),
    );
    expect(await screen.findByText(/already accepted earlier \(replay\)/)).toBeInTheDocument();
  });

  it("aborts before completion and says nothing was imported; selection stays for retry", async () => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv()]);
    act(() => lastXhr().progress(10, 100));
    await user.click(await screen.findByRole("button", { name: "Abort upload" }));
    expect(lastXhr().aborted).toBe(true);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/nothing was imported/i);
    await waitFor(() => expect(alert).toHaveFocus());
    expect(screen.getByRole("button", { name: "Upload 1 file(s)" })).toBeEnabled();
  });

  it("aborting after all bytes were sent says the outcome is unknown", async () => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv()]);
    act(() => lastXhr().progress(100, 100));
    await user.click(await screen.findByRole("button", { name: "Abort upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/may still have accepted it/i);
  });

  it("blocks oversize files and too many files client-side with accessible messages", async () => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    const big = new File(["x"], "huge.las");
    Object.defineProperty(big, "size", { value: MAX_FILE_BYTES + 1 });
    await user.upload(screen.getByLabelText("Choose files"), big);
    expect(await screen.findByRole("alert")).toHaveTextContent(/“huge\.las” is .*the limit is 128 MiB per file/);
    expect(screen.getByRole("button", { name: "Upload 1 file(s)" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Remove huge.las" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    const many = Array.from({ length: 201 }, (_, i) => new File(["x"], `f${i}.txt`));
    await user.upload(screen.getByLabelText("Choose files"), many);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Too many files: 201 selected, at most 200/);
    expect(screen.getByRole("button", { name: "Upload 201 file(s)" })).toBeDisabled();
    expect(FakeXhr.all).toHaveLength(0);
  });

  it.each([
    [409, "CONFLICT", { reason: "import_in_progress" }, /Another import is still being processed/],
    [409, "CONFLICT", { reason: "idempotency_key_reuse" }, /Conflict: server said/],
    [413, "PAYLOAD_TOO_LARGE", { reason: "file_too_large", limit: 1 }, /rejected the upload as too large/],
    [415, "UNSUPPORTED_MEDIA_TYPE", { reason: "executable" }, /unsupported file type.*binary or executable/],
  ])("surfaces HTTP %i explicitly", async (status, code, details, text) => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv()]);
    act(() => lastXhr().respond(status, envelope(code, "server said", details)));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(text);
    expect(alert).toHaveTextContent("Request ID: req-7");
    expect(screen.getByRole("button", { name: "Upload 1 file(s)" })).toBeEnabled();
  });

  it("a stale parent refreshes project state and a network error explains retry safety", async () => {
    install(emptyHandler);
    const changed = panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv()]);
    act(() => lastXhr().respond(409, envelope("CONFLICT", "stale", { reason: "stale_parent" })));
    expect(await screen.findByRole("alert")).toHaveTextContent(/revision changed/);
    expect(changed).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Upload 1 file(s)" }));
    const first = lastXhr();
    act(() => first.fail());
    expect(await screen.findByRole("alert")).toHaveTextContent(/connection to the local API failed.*same idempotency key/);
  });

  it("reuses the idempotency key when the same selection is resubmitted", async () => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv()]);
    const keyOf = (x: FakeXhr) => (JSON.parse(String(x.body?.get("metadata"))) as { idempotency_key: string }).idempotency_key;
    const a = keyOf(lastXhr());
    act(() => lastXhr().fail());
    await user.click(await screen.findByRole("button", { name: "Upload 1 file(s)" }));
    expect(keyOf(lastXhr())).toBe(a);
  });
});

describe("focus after removing a selected file", () => {
  it("moves focus to the next remove button, then the previous, then the file picker", async () => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await user.upload(screen.getByLabelText("Choose files"), [csv(), txt()]);
    await user.click(screen.getByRole("button", { name: "Remove wells.csv" }));
    expect(screen.getByRole("button", { name: "Remove notes.txt" })).toHaveFocus();
    await user.upload(screen.getByLabelText("Choose files"), [csv()]);
    // Remove the last entry: focus falls back to the previous remove button.
    await user.click(screen.getAllByRole("button", { name: "Remove wells.csv" })[0] as HTMLElement);
    expect(screen.getByRole("button", { name: "Remove notes.txt" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Remove notes.txt" }));
    expect(screen.getByLabelText("Choose files")).toHaveFocus();
  });
});

describe("source list", () => {
  it("shows loading, then the empty state", async () => {
    install(emptyHandler);
    panel(null);
    expect(screen.getByText("Loading source revisions…")).toBeInTheDocument();
    expect(await screen.findByText(/no source files yet/i)).toBeInTheDocument();
  });

  it("shows a retryable error", async () => {
    let fail = true;
    install((url) => {
      if (url.includes("/source-revisions")) return fail ? json(envelope("SERVICE_UNAVAILABLE", "db down"), 503) : json(page());
    });
    panel(null);
    const user = userEvent.setup();
    expect(await screen.findByRole("alert")).toHaveTextContent("Source revisions could not be loaded: db down");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Retry loading source revisions" }));
    expect(await screen.findByText(/no source files yet/i)).toBeInTheDocument();
  });

  it("renders exact statuses, hashes, counts, job attempts and never implies extraction", async () => {
    install((url) => {
      if (url.includes("/source-revisions")) return json(page(revision()));
      if (url.includes("/documents?"))
        return json(
          page(
            document(),
            document({
              document_id: D2, original_filename: "notes.txt", extraction_state: "unsupported",
              processing_detail: "no reader for plain text",
              classification: { ...document().classification, user_categories: [], tags: [], categories_origin: "none", suggested_categories: ["general_report"] },
            }),
          ),
        );
      if (url.includes(`/jobs/${J1}`)) return json(job());
    });
    panel(R1);
    expect(await screen.findByText("Pending extraction (not yet extracted)")).toBeInTheDocument();
    expect(screen.getByText("Unsupported (no reader; not extracted)")).toBeInTheDocument();
    expect(screen.getAllByText("Stored (hash-verified)")).toHaveLength(2);
    expect(screen.getByText("no reader for plain text")).toBeInTheDocument();
    expect(screen.getAllByText(SHA)).toHaveLength(2);
    expect(screen.getAllByText(/suggestion only, not confirmed/)).toHaveLength(2);
    expect(screen.getByText("Ready (files stored; not extracted)")).toBeInTheDocument();
    expect(screen.getByText(/Attempt 1: failed, stage hashing, error code io_error/)).toBeInTheDocument();
    expect(screen.getByText(/Attempt 2: succeeded/)).toBeInTheDocument();
    expect(screen.getByText(/retried once automatically/)).toBeInTheDocument();
    expect(screen.getByText(/Extraction performed: no/)).toBeInTheDocument();
    expect(screen.queryByText(/extracted successfully|validated successfully/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel import" })).not.toBeInTheDocument();
  });

  it("warns that a partial latest revision may have displaced a good version", async () => {
    install((url) => {
      if (url.includes("/source-revisions"))
        return json(
          page(
            revision({
              source_revision_id: R2, status: "ready_with_issues", parent_source_revision_id: R1,
              quarantined_count: 1, stored_count: 1, job_status: "partial", job_id: null,
            }),
            revision({ is_latest: false, job_id: null }),
          ),
        );
      if (url.includes("/documents?"))
        return json(page(document({ source_revision_id: R2, replaces_document_id: D2, storage_state: "quarantined" })));
    });
    panel(R2);
    const warnings = await screen.findByLabelText("Revision warnings");
    expect(within(warnings).getByText(/Partial revision: 1 file\(s\) were quarantined.*displaced a previously good version/)).toBeInTheDocument();
    expect(within(warnings).getByText(new RegExp(`parent revision ${R1}`))).toBeInTheDocument();
    expect(screen.getByText("Partial: ready with issues")).toBeInTheDocument();
    const files = within(await screen.findByRole("table", { name: "Files in this source revision" }));
    const row = files.getByRole("row", { name: /wells\.csv/ });
    expect(within(row).getByRole("cell", { name: "Quarantined" })).toBeInTheDocument();
    expect(screen.getByText(D2, { selector: "code" })).toBeInTheDocument();
    expect(screen.getByText("(superseded)", { exact: false })).toBeInTheDocument();
  });

  it("does not call a never-current revision superseded; shows cancelled imports as Cancelled", async () => {
    install((url) => {
      if (url.includes("/source-revisions"))
        return json(
          page(
            revision({
              source_revision_id: R2, is_latest: false, status: "failed", job_status: "cancelled",
              parent_source_revision_id: null, job_id: null,
            }),
          ),
        );
      if (url.includes("/documents?")) return json(page());
    });
    panel(null);
    await screen.findByText(/Cancelled \(import stopped/);
    expect(screen.getByText("(not current)", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("(superseded)", { exact: false })).toBeNull();
    expect(screen.getByRole("region", { name: "Source revisions table" })).toHaveAttribute("tabindex", "0");
  });

  it("polls an in-progress import, refreshes silently, and stops polling after unmount", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let status: "staging" | "ready" = "staging";
    const fetchFn = install((url) => {
      if (url.includes("/source-revisions"))
        return json(page(revision({ status, job_status: status === "staging" ? "running" : "succeeded" })));
      if (url.includes("/documents?")) return json(page(document()));
      if (url.includes(`/jobs/${J1}`)) return json(job({ status: status === "staging" ? "running" : "succeeded" }));
    });
    const { unmount } = render(<SourcesPanel projectId={P} latestRevisionId={R1} onProjectChanged={vi.fn()} />);
    await screen.findByText(/An import is in progress/);
    expect(await screen.findByRole("button", { name: "Cancel import" })).toBeInTheDocument();
    const polls = () => count(fetchFn, "/source-revisions");
    const first = polls();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(polls()).toBeGreaterThan(first);
    expect(screen.queryByText("Loading source revisions…")).not.toBeInTheDocument(); // silent refresh

    status = "ready";
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    await waitFor(() => expect(screen.queryByText(/An import is in progress/)).not.toBeInTheDocument());
    const settled = fetchFn.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchFn.mock.calls.length).toBe(settled); // finished imports are not polled

    status = "staging";
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchFn.mock.calls.length).toBe(settled);
  });

  it("unmounting while an import is in progress clears the poll timers", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchFn = install((url) => {
      if (url.includes("/source-revisions")) return json(page(revision({ status: "staging", job_status: "running" })));
      if (url.includes("/documents?")) return json(page(document()));
      if (url.includes(`/jobs/${J1}`)) return json(job({ status: "running" }));
    });
    const { unmount } = render(<SourcesPanel projectId={P} latestRevisionId={R1} onProjectChanged={vi.fn()} />);
    await screen.findByText(/An import is in progress/);
    unmount();
    const after = fetchFn.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });
    expect(fetchFn.mock.calls.length).toBe(after);
  });

  it("cancels a running import through the job route", async () => {
    let cancelled = false;
    const fetchFn = install((url, init) => {
      if (url.includes("/source-revisions")) return json(page(revision({ status: "staging", job_status: "running" })));
      if (url.includes("/documents?")) return json(page(document()));
      if (url.endsWith(`/jobs/${J1}/cancel`) && init?.method === "POST") {
        cancelled = true;
        return json(job({ status: "running", cancel_requested: true }), 202);
      }
      if (url.includes(`/jobs/${J1}`)) return json(job({ status: "running", cancel_requested: cancelled }));
    });
    panel(R1);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Cancel import" }));
    expect(await screen.findByText(/Cancellation was requested/)).toBeInTheDocument();
    expect(fetchFn.mock.calls.some(([u, i]) => String(u).endsWith("/cancel") && i?.method === "POST")).toBe(true);
    expect(await screen.findByText(/cancellation requested/)).toBeInTheDocument();
  });
});

describe("classification edit", () => {
  const handlerWith = (patch: (init: RequestInit | undefined) => Response): Handler => (url, init) => {
    if (url.includes("/source-revisions")) return json(page(revision()));
    if (url.includes("/documents?")) return json(page(document()));
    if (url.includes(`/jobs/${J1}`)) return json(job());
    if (url.endsWith(`/documents/${D1}/classification`) && init?.method === "PATCH") return patch(init);
  };

  it("sends categories, tags and the expected metadata version, then returns focus", async () => {
    let body: unknown = null;
    install(handlerWith((init) => {
      body = JSON.parse(String(init?.body));
      return json(document());
    }));
    panel(R1);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit labels for wells.csv" }));
    await waitFor(() => expect(globalThis.document.activeElement).not.toBe(globalThis.document.body));
    expect(screen.getByRole("form", { name: "Edit labels for wells.csv" }).contains(globalThis.document.activeElement)).toBe(true);
    await user.click(screen.getByLabelText("Well logs"));
    const tags = screen.getByLabelText("Tags (comma separated)");
    await user.clear(tags);
    await user.type(tags, "pilot, extra, pilot");
    await user.click(screen.getByRole("button", { name: "Save labels" }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({ categories: ["trajectory", "well_logs"], tags: ["pilot", "extra"], expected_metadata_version: 3 });
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit labels for wells.csv" })).toHaveFocus());
  });

  it("explains a stale-version conflict and keeps the editor open", async () => {
    install(handlerWith(() => json(envelope("CONFLICT", "version mismatch"), 409)));
    panel(R1);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit labels for wells.csv" }));
    await user.click(screen.getByRole("button", { name: "Save labels" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed elsewhere.*Nothing was saved/);
    expect(screen.getByRole("button", { name: "Save labels" })).toBeEnabled();
  });

  it("rejects too many tags before sending", async () => {
    const fetchFn = install(handlerWith(() => json(document())));
    panel(R1);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit labels for wells.csv" }));
    const tags = screen.getByLabelText("Tags (comma separated)");
    await user.clear(tags);
    await user.type(tags, Array.from({ length: 21 }, (_, i) => `t${i}`).join(","));
    await user.click(screen.getByRole("button", { name: "Save labels" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("At most 20 tags");
    expect(fetchFn.mock.calls.some(([, i]) => i?.method === "PATCH")).toBe(false);
  });
});

describe("job panel wording (repair D3)", () => {
  const withJob = (over: Record<string, unknown>) => {
    install((url) => {
      if (url.includes("/source-revisions")) return json(page(revision()));
      if (url.includes("/documents?")) return json(page(document()));
      if (url.includes(`/jobs/${J1}`)) return json(job(over));
    });
    panel(R1);
  };

  it("pluralizes the progress unit and labels the counts as job-completion values", async () => {
    withJob({ progress: { processed: 4, total: 4, unit: "document" } });
    expect(await screen.findByText("4 of 4 documents")).toBeInTheDocument();
    expect(screen.getByText(/Result at job completion \(the table below is live and may be newer\)/)).toBeInTheDocument();
  });

  it("shows the stage of the last attempt when the job reports none, and omits the row when nothing names one", async () => {
    withJob({
      stage: null,
      attempts: [{ attempt_no: 1, status: "succeeded", stage: "verify_blobs", fencing_token: 1, started_at: "2026-10-29T12:00:00Z", heartbeat_at: "2026-10-29T12:00:00Z", ended_at: "2026-10-29T12:00:01Z", error_code: null }],
    });
    expect(await screen.findByText("verify_blobs", { selector: "dd" })).toBeInTheDocument();
    cleanup();
    vi.unstubAllGlobals();
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    withJob({ stage: null, attempts: [] });
    await screen.findByText(/Storage verification job/);
    expect(screen.queryByText("Stage")).not.toBeInTheDocument();
  });
});

describe("upload failure wording (repair D4)", () => {
  it("makes a proper sentence, names the only selected file and keeps the Request ID", async () => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv()]);
    act(() => lastXhr().respond(415, envelope("UNSUPPORTED_MEDIA_TYPE", "file signature is not a supported source format", { reason: "unsupported_signature" })));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("source format. The only selected file is “wells.csv”. Remove the refused file and try again.");
    expect(alert).toHaveTextContent("Request ID: req-7");
  });

  it("says honestly that the server did not identify the file when several were selected", async () => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv(), txt()]);
    act(() => lastXhr().respond(415, envelope("UNSUPPORTED_MEDIA_TYPE", "unsafe filename", { reason: "bad_filename" })));
    expect(await screen.findByRole("alert")).toHaveTextContent(/does not say which of the selected files was refused/);
  });

  it("uses the file the server names when it names one", async () => {
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup();
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv(), txt()]);
    act(() => lastXhr().respond(415, envelope("UNSUPPORTED_MEDIA_TYPE", "empty file", { reason: "empty_file", filename: "notes.txt" })));
    expect(await screen.findByRole("alert")).toHaveTextContent("The server named the file: “notes.txt”.");
  });
});

describe("transient status (repair D5)", () => {
  it("clears the import confirmation after it was shown", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    install(emptyHandler);
    panel(null);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await screen.findByText(/no source files yet/i);
    await selectAndSubmit(user, [csv()]);
    act(() => lastXhr().respond(202, { source_revision_id: R1, job_id: J1, status: "staging", deduplicated: false, replayed: false, document_ids: [D1], created_document_ids: [D1] }));
    expect(await screen.findByText(/Import accepted: 1 new file/)).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_500);
    });
    expect(screen.queryByText(/Import accepted: 1 new file/)).not.toBeInTheDocument();
  });
});
