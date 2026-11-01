// TASK-050 (IN-10) refused-file rendering and TASK-052 (UI-14) bulk labels / column split.
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "./render";
import { UploadForm } from "../src/features/uploads/UploadForm";
import { DocumentList } from "../src/features/uploads/DocumentList";

const P = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const R1 = "11111111-1111-4111-8111-111111111111";
const D1 = "d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1";
const D2 = "d2d2d2d2-d2d2-4d2d-8d2d-d2d2d2d2d2d2";
const SHA = "b".repeat(64);

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

class FakeXhr {
  static all: FakeXhr[] = [];
  body: FormData | null = null;
  status = 0;
  responseText = "";
  upload = { onprogress: null, onload: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;
  constructor() {
    FakeXhr.all.push(this);
  }
  open() {}
  setRequestHeader() {}
  getResponseHeader() {
    return null;
  }
  send(body: FormData) {
    this.body = body;
  }
  abort() {}
  respond(status: number, body: unknown) {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
}
const lastXhr = () => FakeXhr.all[FakeXhr.all.length - 1] as FakeXhr;
const file = (name: string, body = "x,y\n1,2\n") => new File([body], name, { type: "text/plain" });
const metaOf = (x: FakeXhr) =>
  JSON.parse(String(x.body?.get("metadata"))) as { idempotency_key: string; files: { categories: string[] }[] };
const sentNames = (x: FakeXhr) => x.body?.getAll("files").map((f) => (f as File).name);

const refusedFile = (filename: string, position: number, over: Record<string, unknown> = {}) => ({
  filename,
  position,
  reason: "unsupported_signature",
  message: "file signature is not a supported source format",
  error_code: "UNSUPPORTED_MEDIA_TYPE",
  status_code: 415,
  limit: null,
  ...over,
});
const refusalBody = (details: unknown, code = "UNSUPPORTED_MEDIA_TYPE", message = "1 file refused") => ({
  error: { code, message, request_id: "req-9", details },
});
const refusalDetails = (files: unknown[], over: Record<string, unknown> = {}) => ({
  reason: "unsupported_signature",
  scope: "files",
  batch_outcome: "nothing_stored",
  refusals_complete: true,
  file_count: 3,
  limit: null,
  refused_files: files,
  ...over,
});

beforeEach(() => {
  FakeXhr.all = [];
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(json({ csrf_token: "t".repeat(43) }))),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function form() {
  render(<UploadForm projectId={P} expectedParentId={null} onImported={vi.fn()} onStale={vi.fn()} />);
  return userEvent.setup();
}
async function pickAndSend(user: ReturnType<typeof userEvent.setup>, files: File[]) {
  await user.upload(screen.getByLabelText("Choose files"), files);
  await user.click(screen.getByRole("button", { name: /^Upload \d+ file/ }));
}
const row = (name: string) => screen.getByLabelText(`Remove ${name}`).closest("li") as HTMLElement;

describe("refused files (IN-10)", () => {
  it("marks every refused file red with text, keeps the others, says nothing was stored and removes+retries", async () => {
    const user = form();
    await pickAndSend(user, [file("a.csv"), file("tool.bin"), file("c.csv"), file("evil.exe")]);
    const first = lastXhr();
    act(() => first.respond(415, refusalBody(refusalDetails([refusedFile("tool.bin", 1), refusedFile("evil.exe", 3, { reason: "executable_content", message: "executable content" })], { file_count: 4 }))));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Nothing was stored");
    expect(alert).toHaveTextContent("refused 2 of 4 file(s)");
    expect(alert).toHaveTextContent("Every other selected file is still selected");
    expect(alert).not.toHaveTextContent(/may be incomplete/);
    expect(alert).toHaveTextContent("Request ID: req-9");

    for (const [name, reason] of [["tool.bin", "unsupported_signature"], ["evil.exe", "executable_content"]] as const) {
      expect(row(name)).toHaveAttribute("data-refused", "true");
      expect(row(name)).toHaveTextContent(`Refused:`);
      expect(row(name)).toHaveTextContent(reason);
      expect(row(name)).toHaveTextContent("HTTP 415");
    }
    for (const name of ["a.csv", "c.csv"]) {
      expect(row(name)).not.toHaveAttribute("data-refused");
      expect(row(name)).not.toHaveTextContent("Refused:");
    }
    // Normal retry resends the same selection with the same idempotency key.
    await user.click(within(alert).getByRole("button", { name: "Retry upload" }));
    expect(FakeXhr.all).toHaveLength(2);
    expect(metaOf(lastXhr()).idempotency_key).toBe(metaOf(first).idempotency_key);
    expect(sentNames(lastXhr())).toEqual(["a.csv", "tool.bin", "c.csv", "evil.exe"]);
    act(() => lastXhr().respond(415, refusalBody(refusalDetails([refusedFile("tool.bin", 1), refusedFile("evil.exe", 3)], { file_count: 4 }))));

    await user.click(await screen.findByRole("button", { name: "Remove refused files and retry" }));
    expect(FakeXhr.all).toHaveLength(3);
    expect(sentNames(lastXhr())).toEqual(["a.csv", "c.csv"]);
    expect(metaOf(lastXhr()).files).toHaveLength(2);
    expect(metaOf(lastXhr()).idempotency_key).not.toBe(metaOf(first).idempotency_key);
  });

  it("says plainly that a batch-level refusal's list may be incomplete and offers no removal without a match", async () => {
    const user = form();
    await pickAndSend(user, [file("a.csv"), file("b.csv")]);
    act(() =>
      lastXhr().respond(
        413,
        refusalBody(refusalDetails([], { scope: "batch", refusals_complete: false, reason: "batch_too_large", file_count: null }), "PAYLOAD_TOO_LARGE", "batch too large"),
      ),
    );
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("may be incomplete");
    expect(alert).toHaveTextContent("none of it was stored");
    expect(screen.queryByRole("button", { name: /Remove refused files/ })).not.toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Retry upload" })).toBeInTheDocument();
  });

  it("flags an incomplete list even for per-file scope", async () => {
    const user = form();
    await pickAndSend(user, [file("a.csv"), file("b.bin")]);
    act(() => lastXhr().respond(415, refusalBody(refusalDetails([refusedFile("b.bin", 1)], { refusals_complete: false }))));
    expect(await screen.findByRole("alert")).toHaveTextContent("may be incomplete");
    expect(row("b.bin")).toHaveAttribute("data-refused", "true");
  });

  it("falls back to the generic message for missing or malformed details and never crashes", async () => {
    for (const details of [null, "oops", { scope: "files", refused_files: "nope" }, { scope: "weird", refused_files: [] }, { reason: "bad_filename" }]) {
      cleanup();
      FakeXhr.all = [];
      const user = form();
      await pickAndSend(user, [file("a.csv"), file("b.csv")]);
      act(() => lastXhr().respond(415, refusalBody(details, "UNSUPPORTED_MEDIA_TYPE", "unsafe filename")));
      expect(await screen.findByRole("alert")).toHaveTextContent(/does not say which of the selected files was refused/);
      expect(screen.queryByRole("button", { name: /Remove refused files/ })).not.toBeInTheDocument();
      expect(document.querySelector("[data-refused]")).toBeNull();
    }
  });

  it("drops unreadable entries, keeps readable ones and marks the list incomplete", async () => {
    const user = form();
    await pickAndSend(user, [file("a.csv"), file("b.bin")]);
    act(() => lastXhr().respond(415, refusalBody(refusalDetails([refusedFile("b.bin", 1), { filename: 5 }, null]))));
    expect(await screen.findByRole("alert")).toHaveTextContent("may be incomplete");
    expect(row("b.bin")).toHaveAttribute("data-refused", "true");
  });

  it("matches by file name and says so when the server position disagrees; lists unmatched names", async () => {
    const user = form();
    await pickAndSend(user, [file("a.csv"), file("b.bin")]);
    act(() => lastXhr().respond(415, refusalBody(refusalDetails([refusedFile("b.bin", 0), refusedFile("ghost.bin", 7)]))));
    const alert = await screen.findByRole("alert");
    expect(row("b.bin")).toHaveAttribute("data-refused", "true");
    expect(row("b.bin")).toHaveTextContent("position (file 1) differs");
    expect(row("a.csv")).not.toHaveAttribute("data-refused");
    expect(alert).toHaveTextContent("not in the current selection");
    expect(alert).toHaveTextContent("“ghost.bin” (position 8)");
  });
});

describe("bulk category at upload (UI-14)", () => {
  it("applies one hint to the checked subset, or to all when none is checked, in addition to per-file", async () => {
    const user = form();
    await user.upload(screen.getByLabelText("Choose files"), [file("a.csv"), file("b.csv"), file("c.csv")]);
    expect(screen.getByRole("button", { name: "Apply to all 3 file(s)" })).toBeInTheDocument();
    await user.click(screen.getByLabelText("Select a.csv for a bulk category hint"));
    await user.click(screen.getByLabelText("Select c.csv for a bulk category hint"));
    await user.selectOptions(screen.getByLabelText("Category hint to apply"), "well_logs");
    await user.click(screen.getByRole("button", { name: "Apply to 2 checked file(s)" }));
    expect(screen.getByText(/Set the category hint “Well logs” on 2 file\(s\)/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Category hint for b.csv"), "trajectory"); // per-file still works
    await user.click(screen.getByRole("button", { name: "Upload 3 file(s)" }));
    expect(metaOf(lastXhr()).files.map((f) => f.categories)).toEqual([["well_logs"], ["trajectory"], ["well_logs"]]);
  });

  it("select-all checks every file", async () => {
    const user = form();
    await user.upload(screen.getByLabelText("Choose files"), [file("a.csv"), file("b.csv")]);
    await user.click(screen.getByLabelText("Select all files"));
    expect(screen.getByRole("button", { name: "Apply to 2 checked file(s)" })).toBeInTheDocument();
  });
});

function doc(id: string, name: string, over: Record<string, unknown> = {}, cls: Record<string, unknown> = {}) {
  return {
    document_id: id,
    project_id: P,
    original_filename: name,
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
      suggested_categories: ["general_report"],
      tags: ["pilot"],
      categories_origin: "upload_hint",
      classification_method: "filename_rules",
      classification_version: "1",
      metadata_version: 3,
      updated_at: "2026-10-29T12:00:00Z",
      ...cls,
    },
    replaces_document_id: null,
    source_revision_id: R1,
    ...over,
  };
}

function table(patch: (id: string, body: Record<string, unknown>) => Response) {
  const patches: { id: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/session") return Promise.resolve(json({ csrf_token: "t".repeat(43) }));
      if (url.includes("/documents?"))
        return Promise.resolve(
          json({
            items: [doc(D1, "wells.csv"), doc(D2, "notes.txt", {}, { user_categories: ["well_logs"], tags: [], categories_origin: "user_override", metadata_version: 7 })],
            page: { limit: 50, next_cursor: null },
          }),
        );
      const m = /\/documents\/([^/]+)\/classification$/.exec(url);
      if (m !== null && init?.method === "PATCH") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        patches.push({ id: m[1] as string, body });
        return Promise.resolve(patch(m[1] as string, body));
      }
      throw new Error(`unexpected ${init?.method ?? "GET"} ${url}`);
    }),
  );
  render(<DocumentList projectId={P} revisionId={R1} version="v1" polling={false} />);
  return { patches, user: userEvent.setup() };
}

describe("files table columns and details (UI-14)", () => {
  it("has separate Your labels, Suggested labels and Tags columns; identifiers sit in an expandable detail", async () => {
    const { user } = table(() => json({}));
    await screen.findByText("wells.csv");
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(expect.arrayContaining(["Your labels", "Suggested labels", "Tags"]));
    expect(headers).not.toContain("SHA-256");
    const r = screen.getByRole("row", { name: /wells\.csv/ });
    const cells = within(r).getAllByRole("cell");
    // order: select, file, storage, extraction, your, suggested, tags, actions
    expect(cells[4]).toHaveTextContent("Trajectory");
    expect(cells[4]).toHaveTextContent("Confirmed by you");
    expect(cells[5]).toHaveTextContent("General report");
    expect(cells[5]).toHaveTextContent("Suggestion only, not confirmed (method filename_rules)");
    expect(cells[5]).not.toHaveTextContent("Confirmed by you");
    expect(cells[6]).toHaveTextContent("pilot");

    expect(screen.queryByText(SHA)).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Show details for wells.csv" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Hide details for wells.csv" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(SHA)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: `Copy SHA-256: ${SHA}` })).toBeInTheDocument(); // keyboard-reachable, copyable
    expect(screen.getByText("2048 bytes", { exact: false })).toBeInTheDocument();
  });
});

describe("bulk labels in the files table (UI-14)", () => {
  it("adds a category to all selected rows after one confirmation, preserving tags and versions", async () => {
    const { patches, user } = table((id) => json(doc(id, "x")));
    await screen.findByText("wells.csv");
    await user.click(screen.getByLabelText("Select all visible files"));
    expect(screen.getByRole("group", { name: "Bulk labels for 2 selected file(s)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review bulk change" })).toBeDisabled();
    await user.click(within(screen.getByRole("group", { name: "Categories" })).getByLabelText("Perforation history"));
    await user.click(screen.getByRole("button", { name: "Review bulk change" }));
    expect(patches).toHaveLength(0); // nothing is sent before the confirmation
    expect(await screen.findByRole("alert")).toHaveTextContent("changes 2 document(s)");
    await user.click(screen.getByRole("button", { name: "Confirm bulk change for 2 document(s)" }));
    await waitFor(() => expect(patches).toHaveLength(2));
    expect(patches[0]).toEqual({ id: D1, body: { categories: ["trajectory", "perforation_history"], tags: ["pilot"], expected_metadata_version: 3 } });
    expect(patches[1]).toEqual({ id: D2, body: { categories: ["perforation_history", "well_logs"], tags: [], expected_metadata_version: 7 } });
    expect(await screen.findByText(/2 saved, 0 unchanged, 0 failed of 2/)).toBeInTheDocument();
  });

  it("reports a partial failure per document, keeps failed rows selected and skips unchanged ones", async () => {
    const { patches, user } = table((id) =>
      id === D2 ? json({ error: { code: "CONFLICT", message: "version mismatch", request_id: "r", details: null } }, 409) : json(doc(id, "x")),
    );
    await screen.findByText("wells.csv");
    await user.click(screen.getByLabelText("Select wells.csv"));
    await user.click(screen.getByLabelText("Select notes.txt"));
    await user.selectOptions(screen.getByLabelText("Bulk action"), "remove");
    await user.click(within(screen.getByRole("group", { name: "Categories" })).getByLabelText("Trajectory"));
    await user.click(screen.getByRole("button", { name: "Review bulk change" }));
    await user.click(screen.getByRole("button", { name: /^Confirm bulk change/ }));
    // wells.csv loses Trajectory (saved); notes.txt never had it (unchanged, nothing sent)
    await screen.findByText(/1 saved, 1 unchanged, 0 failed of 2/);
    expect(patches.map((p) => p.id)).toEqual([D1]);
    expect(patches[0]?.body["categories"]).toEqual([]);
  });

  it("marks failures with text and leaves the failed document selected for retry", async () => {
    const { user } = table((id) =>
      id === D2 ? json({ error: { code: "CONFLICT", message: "version mismatch", request_id: "r", details: null } }, 409) : json(doc(id, "x")),
    );
    await screen.findByText("wells.csv");
    await user.click(screen.getByLabelText("Select all visible files"));
    await user.selectOptions(screen.getByLabelText("Bulk action"), "set");
    await user.click(within(screen.getByRole("group", { name: "Categories" })).getByLabelText("Geology / reservoir"));
    await user.click(screen.getByRole("button", { name: "Review bulk change" }));
    await user.click(screen.getByRole("button", { name: /^Confirm bulk change/ }));
    const status = await screen.findByText(/1 saved, 0 unchanged, 1 failed of 2/);
    expect(status).toHaveTextContent("failed documents stay selected");
    const results = screen.getByRole("list", { name: "Bulk label results" });
    expect(within(results).getByText(/notes\.txt/).closest("li")).toHaveTextContent("Failed. Not saved: this document's labels were changed elsewhere");
    expect(within(results).getByText(/wells\.csv/).closest("li")).toHaveTextContent("Saved.");
    await waitFor(() => expect(screen.getByLabelText("Select notes.txt")).toBeChecked());
    expect(screen.getByLabelText("Select wells.csv")).not.toBeChecked();
  });
});
