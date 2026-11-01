// Interaction tests with a stubbed fetch. They prove client logic (stale rejection, retained
// values, saved-ID handling). Persistence/restart acceptance lives in tests/e2e against the
// real API and PostgreSQL; nothing here counts as persistence evidence.
import { act, screen, waitFor, within } from "@testing-library/react";
import { render } from "./render";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/app/App";

const A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const ready = { status: "ready", checks: [{ name: "database", ok: true }] };

function project(id: string, name: string, description: string) {
  return {
    project_id: id,
    name,
    description,
    created_at: "2026-10-28T12:00:00Z",
    updated_at: "2026-10-28T12:00:00Z",
    latest_source_revision_id: null,
    active_model_revision_id: null,
  };
}
const pa = project(A, "Alpha", "alpha notes");
const pb = project(B, "Beta", "beta notes");

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}
const envelope = (code: string, message: string) => ({ error: { code, message, request_id: "req-9" } });

type Handler = (url: string, init?: RequestInit) => Promise<Response> | Response | undefined;

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

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("project workspace", () => {
  it("lists, opens a project and names unmet prerequisites per section by keyboard", async () => {
    install((url) => {
      if (url.startsWith("/api/v1/projects?")) return page(pa, pb);
      if (url === `/api/v1/projects/${A}`) return json(pa);
      if (url.startsWith(`/api/v1/projects/${A}/source-revisions`)) return page();
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Open project Alpha" }));
    expect(await screen.findByRole("heading", { name: "Alpha" })).toBeInTheDocument();
    expect(screen.getByText("alpha notes", { selector: "dd" })).toBeInTheDocument();
    expect(await screen.findByText(/no source files/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upload source files" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Project sections" });
    const reconstruction = within(nav).getByRole("button", { name: "Reconstruction" });
    reconstruction.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByText(/requires an imported source revision/i)).toBeInTheDocument();
    expect(reconstruction).toHaveAttribute("aria-current", "page");
    await user.click(within(nav).getByRole("button", { name: "Explore" }));
    expect(screen.getByText(/requires a published model revision/i)).toBeInTheDocument();
    expect(window.localStorage.getItem("fieldlens.selectedProjectId")).toBe(A);
  });

  it("rejects a late response and acknowledgement for a project that was switched away from", async () => {
    let releaseA!: (r: Response) => void;
    let releasePatch!: (r: Response) => void;
    install((url, init) => {
      if (url.startsWith("/api/v1/projects?")) return page(pa, pb);
      if (url === `/api/v1/projects/${A}` && init?.method === "PATCH") {
        return new Promise<Response>((r) => (releasePatch = r)) as unknown as Response;
      }
      if (url === `/api/v1/projects/${A}`) {
        return new Promise<Response>((r) => (releaseA = r)) as unknown as Response;
      }
      if (url === `/api/v1/projects/${B}`) return json(pb);
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Open project Alpha" }));
    expect(screen.getByText(/loading project/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to all projects" }));
    await user.click(await screen.findByRole("button", { name: "Open project Beta" }));
    expect(await screen.findByRole("heading", { name: "Beta" })).toBeInTheDocument();
    releaseA(json(pa)); // the obsolete A response arrives after B is open
    await new Promise((r) => setTimeout(r, 20));
    // The sidebar legitimately lists Alpha; no Alpha content may appear in the project region.
    expect(within(screen.getByRole("main")).queryByText(/alpha/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Beta" })).toBeInTheDocument();
    expect(window.localStorage.getItem("fieldlens.selectedProjectId")).toBe(B);
    expect(releasePatch).toBeUndefined();
  });

  it("drops a pending save acknowledgement after switching projects", async () => {
    let releasePatch!: (r: Response) => void;
    install((url, init) => {
      if (url.startsWith("/api/v1/projects?")) return page(pa, pb);
      if (url === `/api/v1/projects/${A}` && init?.method === "PATCH") {
        return new Promise<Response>((r) => (releasePatch = r)) as unknown as Response;
      }
      if (url === `/api/v1/projects/${A}`) return json(pa);
      if (url === `/api/v1/projects/${B}`) return json(pb);
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Open project Alpha" }));
    await screen.findByRole("heading", { name: "Alpha" });
    await user.click(screen.getByRole("button", { name: "Edit project details" }));
    const name = screen.getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Alpha 2");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(releasePatch).toBeDefined());
    await user.click(screen.getByRole("button", { name: "Back to all projects" }));
    await user.click(await screen.findByRole("button", { name: "Open project Beta" }));
    await screen.findByRole("heading", { name: "Beta" });
    releasePatch(json({ ...pa, name: "Alpha 2" }));
    await new Promise((r) => setTimeout(r, 20));
    const main = within(screen.getByRole("main"));
    expect(screen.queryByText(/Saved/)).not.toBeInTheDocument();
    expect(main.queryByText(/Alpha/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit project details" })); // editor state was reset by the switch
    expect(screen.getByLabelText("Name")).toHaveValue("Beta");
  });

  it("keeps entered values and the stored project when a save fails, and explains a refreshed session", async () => {
    const fetchMock = install((url, init) => {
      if (url.startsWith("/api/v1/projects?")) return page(pa);
      if (url === `/api/v1/projects/${A}` && init?.method === "PATCH") {
        return json(envelope("SESSION_TOKEN_INVALID", "stale"), 403);
      }
      if (url === `/api/v1/projects/${A}`) return json(pa);
      if (url === "/api/v1/session") return json({ csrf_token: "n".repeat(43) });
      if (url.startsWith(`/api/v1/projects/${A}/source-revisions`)) return page();
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Open project Alpha" }));
    await screen.findByRole("heading", { name: "Alpha" });
    await user.click(screen.getByRole("button", { name: "Edit project details" }));
    const name = screen.getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Changed");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/nothing was saved/i);
    expect(screen.getByLabelText("Name")).toHaveValue("Changed"); // entered text retained
    expect(screen.getByRole("heading", { name: "Alpha" })).toBeInTheDocument(); // stored value shown
    expect(fetchMock.mock.calls.filter(([, i]) => i?.method === "PATCH")).toHaveLength(1);
  });

  it("validates the name before sending and shows server failures with a request id", async () => {
    const fetchMock = install((url, init) => {
      if (url.startsWith("/api/v1/projects?")) return page();
      if (init?.method === "POST") return json(envelope("SERVICE_UNAVAILABLE", "project storage is unavailable"), 503);
    });
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create project" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Name is required.");
    expect(screen.getByLabelText("Name")).toHaveFocus();
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === "POST")).toBe(false);
    await user.type(screen.getByLabelText("Name"), "  Gamma ");
    await user.type(screen.getByLabelText("Description (optional)"), "d");
    await user.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/unavailable.*req-9/i);
    expect(screen.getByLabelText("Name")).toHaveValue("  Gamma ");
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ name: "Gamma", description: "d" });
  });

  it("list failure offers Retry; Load more appends the next page", async () => {
    let calls = 0;
    install((url) => {
      if (!url.startsWith("/api/v1/projects?")) return undefined;
      calls += 1;
      if (calls === 1) return json(envelope("SERVICE_UNAVAILABLE", "down"), 503);
      if (url.includes("cursor=next")) return page(pb);
      return json({ items: [pa], page: { limit: 50, next_cursor: "next" } });
    });
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/down/);
    await user.click(screen.getByRole("button", { name: "Retry loading projects" }));
    await screen.findByRole("button", { name: "Open project Alpha" });
    await user.click(screen.getByRole("button", { name: "Load more projects" }));
    expect(await screen.findByRole("button", { name: "Open project Beta" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more projects" })).not.toBeInTheDocument();
  });
});

describe("saved selection", () => {
  it("reopens the saved existing project on reload", async () => {
    window.localStorage.setItem("fieldlens.selectedProjectId", B);
    install((url) => {
      if (url.startsWith("/api/v1/projects?")) return page(pb);
      if (url === `/api/v1/projects/${B}`) return json(pb);
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Beta" })).toBeInTheDocument();
  });

  it("returns to the list with an explanation when the saved ID is missing, never another project", async () => {
    window.localStorage.setItem("fieldlens.selectedProjectId", A);
    install((url) => {
      if (url === `/api/v1/projects/${A}`) return json(envelope("NOT_FOUND", "project not found"), 404);
      if (url.startsWith("/api/v1/projects?")) return page(pb);
    });
    render(<App />);
    expect(await screen.findByText(/was not found/i)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(A))).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Beta" })).not.toBeInTheDocument();
    expect(window.localStorage.getItem("fieldlens.selectedProjectId")).toBeNull();
  });

  it("keeps the saved ID on a transient failure and offers Retry", async () => {
    window.localStorage.setItem("fieldlens.selectedProjectId", A);
    let n = 0;
    install((url) => {
      if (url.startsWith("/api/v1/projects?")) return page(pa);
      if (url !== `/api/v1/projects/${A}`) return undefined;
      n += 1;
      return n === 1 ? json(envelope("SERVICE_UNAVAILABLE", "down"), 503) : json(pa);
    });
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/down/);
    expect(window.localStorage.getItem("fieldlens.selectedProjectId")).toBe(A);
    await user.click(screen.getByRole("button", { name: "Retry loading project" }));
    expect(await screen.findByRole("heading", { name: "Alpha" })).toBeInTheDocument();
  });

  it("treats a malformed saved ID as invalid without a request", async () => {
    window.localStorage.setItem("fieldlens.selectedProjectId", "not-a-uuid");
    const fetchMock = install((url) => (url.startsWith("/api/v1/projects?") ? page() : undefined));
    render(<App />);
    expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("not-a-uuid"))).toBe(false);
  });

  it("rejects a response whose project does not match the requested ID", async () => {
    window.localStorage.setItem("fieldlens.selectedProjectId", A);
    install((url) => {
      if (url.startsWith("/api/v1/projects?")) return page(pa);
      if (url === `/api/v1/projects/${A}`) return json(pb);
    });
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/different project/i);
    expect(screen.queryByText("beta notes")).not.toBeInTheDocument();
  });
});

describe("addresses (repair D5)", () => {
  it("normalizes an unknown tab segment to Sources in the address", async () => {
    window.location.hash = `#/projects/${A}/bogus`;
    install((url) => {
      if (url.startsWith("/api/v1/projects?")) return page(pa);
      if (url === `/api/v1/projects/${A}`) return json(pa);
      if (url.startsWith(`/api/v1/projects/${A}/source-revisions`)) return page();
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Alpha" });
    await waitFor(() => expect(window.location.hash).toBe(`#/projects/${A}/sources`));
  });

  it("a typed address for a missing project does not claim a previously open project", async () => {
    window.location.hash = `#/projects/${A}/sources`;
    install((url) => {
      if (url === `/api/v1/projects/${A}`) return json(envelope("NOT_FOUND", "project not found"), 404);
      if (url.startsWith("/api/v1/projects?")) return page(pb);
    });
    render(<App />);
    expect(await screen.findByText(new RegExp(`No project with ID ${A} was found`))).toBeInTheDocument();
    expect(screen.queryByText(/previously open/i)).not.toBeInTheDocument();
  });

  it("the Saved confirmation clears itself", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      install((url) => {
        if (url.startsWith("/api/v1/projects?")) return page();
        if (url.endsWith("/api/v1/projects")) return json(pa, 201);
      });
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<App />);
      await screen.findByText(/no projects yet/i);
      await user.type(screen.getByLabelText("Name"), "Alpha");
      await user.click(screen.getByRole("button", { name: "Create project" }));
      expect(await screen.findByText(/Saved “Alpha”/)).toBeInTheDocument();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(8500);
      });
      expect(screen.queryByText(/Saved “Alpha”/)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
