// Interaction tests for TASK-071 project deletion (AC-9) with a stubbed fetch. They prove client
// logic only; the real backend purge is covered by backend tests and the e2e spec.
import { screen, waitFor, within } from "@testing-library/react";
import { render } from "./render";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/app/App";

const A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const ready = { status: "ready", checks: [{ name: "database", ok: true }] };

function project(id: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    project_id: id,
    name,
    description: "",
    created_at: "2026-10-28T12:00:00Z",
    updated_at: "2026-10-28T12:00:00Z",
    latest_source_revision_id: null,
    active_model_revision_id: null,
    deletion_state: "none",
    deletion_requested_at: null,
    deletion_error: null,
    ...extra,
  };
}
const preview = {
  project_id: A,
  name: "Alpha",
  deletion_state: "none",
  documents: 3,
  stored_bytes: 2048,
  source_revisions: 1,
  wells: 2,
  wellbores: 4,
  extracted_records: 10,
  evidence_chunks: 20,
  processing_runs: 5,
  reconstruction_runs: 6,
  agent_work_units: 7,
  active_jobs: 1,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}
const envelope = (code: string, message: string, details?: Record<string, unknown>) =>
  json({ error: { code, message, request_id: "req-7", details } }, code === "NOT_FOUND" ? 404 : 422);

type Handler = (url: string, init?: RequestInit) => Response | undefined;
function install(handler: Handler) {
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/ready") return Promise.resolve(json(ready));
    if (url === "/api/v1/session") return Promise.resolve(json({ csrf_token: "t".repeat(43) }));
    const out = handler(url, init);
    if (out === undefined) throw new Error(`unexpected request ${init?.method ?? "GET"} ${url}`);
    return Promise.resolve(out);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
const page = (...items: unknown[]) => json({ items, page: { limit: 50, next_cursor: null } });
const notFound = () => json({ error: { code: "NOT_FOUND", message: "Project not found.", request_id: "r" } }, 404);

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

async function openDialog(user: ReturnType<typeof userEvent.setup>, name = "Alpha") {
  render(<App />);
  await user.click(await screen.findByRole("button", { name: `Delete project ${name}` }));
  return await screen.findByRole("dialog");
}

describe("project deletion dialog", () => {
  it("shows the warning and counts and enables Delete only on an exact, untrimmed match", async () => {
    install((url) => {
      if (url.startsWith("/api/v1/projects?")) return page(project(A, "Alpha"));
      if (url === `/api/v1/projects/${A}/deletion-preview`) return json(preview);
    });
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();
    expect(await within(dialog).findByText("Wellbores")).toBeInTheDocument();
    expect(within(dialog).getByText(/2\.0 KiB/)).toBeInTheDocument();
    const del = within(dialog).getByRole("button", { name: "Delete project" });
    const box = within(dialog).getByLabelText(/Type the project name/);
    expect(del).toBeDisabled();
    for (const wrong of ["alpha", "Alph", "Alpha ", " Alpha"]) {
      await user.clear(box);
      await user.type(box, wrong);
      expect(del).toBeDisabled();
    }
    await user.clear(box);
    await user.type(box, "Alpha");
    expect(del).toBeEnabled();
  });

  it("handles a 422 confirm_name_mismatch without starting deletion", async () => {
    const fn = install((url, init) => {
      if (url.startsWith("/api/v1/projects?")) return page(project(A, "Alpha"));
      if (url === `/api/v1/projects/${A}/deletion-preview`) return json(preview);
      if (init?.method === "DELETE") return envelope("VALIDATION_ERROR", "Name mismatch.", { reason: "confirm_name_mismatch" });
    });
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByLabelText(/Type the project name/), "Alpha");
    await user.click(within(dialog).getByRole("button", { name: "Delete project" }));
    expect(await within(dialog).findByText(/did not accept this name/i)).toBeInTheDocument();
    expect(within(dialog).queryByText(/Deleting…/)).not.toBeInTheDocument();
    const del = fn.mock.calls.filter(([, init]) => init?.method === "DELETE");
    expect(del).toHaveLength(1);
    expect(JSON.parse(String(del[0]?.[1]?.body))).toEqual({ confirm_name: "Alpha" });
    expect((del[0]?.[1]?.headers as Record<string, string>)["x-fieldlens-token"]).toBeTruthy();
  });

  it("shows progress, polls until 404, removes the project and clears the stored selection", async () => {
    window.localStorage.setItem("fieldlens.selectedProjectId", A);
    window.location.hash = `#/projects/${A}/sources`;
    let deleted = false;
    let polls = 0;
    install((url, init) => {
      if (url.startsWith("/api/v1/projects?")) return page(...(deleted ? [project(B, "Beta")] : [project(A, "Alpha"), project(B, "Beta")]));
      if (url === `/api/v1/projects/${A}/deletion-preview`) return json(preview);
      if (init?.method === "DELETE") {
        return json({ project_id: A, deletion_state: "deleting", deletion_requested_at: "2026-11-02T12:00:00Z", deletion_error: null }, 202);
      }
      if (url === `/api/v1/projects/${A}`) {
        polls += 1;
        if (polls < 3) return json(project(A, "Alpha", { deletion_state: "deleting" }));
        deleted = true;
        return notFound();
      }
      if (url === `/api/v1/projects/${B}`) return json(project(B, "Beta"));
      if (url.includes("/source-revisions")) return page();
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Delete project Alpha" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Type the project name/), "Alpha");
    await user.click(within(dialog).getByRole("button", { name: "Delete project" }));
    expect(await within(dialog).findByText(/Deleting…/)).toBeInTheDocument();
    expect(within(dialog).getByRole("status")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument(), { timeout: 6000 });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Open project Alpha" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Open project Beta" })).toBeInTheDocument();
    expect(window.localStorage.getItem("fieldlens.selectedProjectId")).not.toBe(A);
    await waitFor(() => expect(window.location.hash).toBe(`#/projects/${B}/sources`));
  }, 15000);

  it("shows a failed deletion with its error and retries with the same name", async () => {
    let deleteCalls = 0;
    install((url, init) => {
      if (url.startsWith("/api/v1/projects?")) return page(project(A, "Alpha"));
      if (url === `/api/v1/projects/${A}/deletion-preview`) return json(preview);
      if (init?.method === "DELETE") {
        deleteCalls += 1;
        return json({ project_id: A, deletion_state: "deleting", deletion_requested_at: "2026-11-02T12:00:00Z", deletion_error: null }, 202);
      }
      if (url === `/api/v1/projects/${A}`) {
        return deleteCalls === 1
          ? json(project(A, "Alpha", { deletion_state: "failed", deletion_error: "storage root mismatch" }))
          : notFound();
      }
    });
    const user = userEvent.setup();
    const dialog = await openDialog(user);
    await user.type(within(dialog).getByLabelText(/Type the project name/), "Alpha");
    await user.click(within(dialog).getByRole("button", { name: "Delete project" }));
    expect(await within(dialog).findByText("storage root mismatch", {}, { timeout: 4000 })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Retry deletion" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument(), { timeout: 6000 });
    expect(deleteCalls).toBe(2);
    expect(await screen.findByText(/No projects yet/)).toBeInTheDocument();
  }, 15000);

  it("marks a deleting project with a badge and reopens its progress", async () => {
    install((url) => {
      if (url.startsWith("/api/v1/projects?")) return page(project(A, "Alpha", { deletion_state: "deleting" }));
      if (url === `/api/v1/projects/${A}`) return json(project(A, "Alpha", { deletion_state: "deleting" }));
    });
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText("Deleting…")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deletion status of project Alpha" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("status")).toHaveTextContent(/Deleting…/);
  });
});
