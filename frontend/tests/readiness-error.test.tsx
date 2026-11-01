import { screen } from "@testing-library/react";
import { render } from "./render";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/app/App";

const ready = {
  status: "ready",
  checks: [
    { name: "database", ok: true },
    { name: "migrations", ok: true },
    { name: "pgvector", ok: true },
  ],
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const emptyPage = { items: [], page: { limit: 50, next_cursor: null } };

// Readiness is the system under test here; the project list answers with an empty page.
function byUrl(input: RequestInfo | URL): Promise<Response> {
  return Promise.resolve(String(input).startsWith("/api/v1/projects") ? json(emptyPage) : json(ready));
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("readiness shell", () => {
  it("shows loading, then the empty workspace", async () => {
    vi.stubGlobal("fetch", vi.fn(byUrl));
    render(<App />);
    expect(screen.getByText(/checking local services/i)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Workspace" })).toBeInTheDocument();
    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument();
  });

  it("shows an actionable unavailable state with request id, then recovers on Retry", async () => {
    const envelope = { error: { code: "NOT_READY", message: "Database is not reachable.", request_id: "req-1" } };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(envelope, 503))
      .mockResolvedValueOnce(json(ready))
      .mockImplementation(byUrl);
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is not reachable.");
    expect(screen.getByText(/req-1/)).toBeInTheDocument();
    expect(screen.queryByText(/local services ready/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Workspace" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => url === "/ready")).toHaveLength(2);
  });

  it("treats a network failure as unavailable, never as ready", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/i);
  });

  it("retains keyboard focus through retry loading, repeated failure and recovery", async () => {
    const user = userEvent.setup();
    const failure = { error: { code: "NOT_READY", message: "Unavailable", request_id: "req-2" } };
    let completeRetry!: (value: Response) => void;
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(json(failure, 503))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { completeRetry = resolve; }))
      .mockResolvedValueOnce(json(ready))
      .mockImplementation(byUrl));
    render(<App />);
    const retry = await screen.findByRole("button", { name: "Retry" });
    retry.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByText(/checking local services/i)).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveFocus();
    completeRetry(json(failure, 503));
    await screen.findByRole("alert");
    expect(screen.getByRole("main")).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Retry" })).toHaveFocus();
    await user.keyboard("{Enter}");
    await screen.findByRole("heading", { name: "Workspace" });
    expect(screen.getByRole("main")).toHaveFocus();
  });
});
