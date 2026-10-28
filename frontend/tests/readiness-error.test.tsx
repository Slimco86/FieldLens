import { render, screen } from "@testing-library/react";
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

afterEach(() => vi.unstubAllGlobals());

describe("readiness shell", () => {
  it("shows loading, then the empty workspace", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(ready)));
    render(<App />);
    expect(screen.getByText(/checking local services/i)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Workspace" })).toBeInTheDocument();
    expect(screen.getByText(/no project is open/i)).toBeInTheDocument();
  });

  it("shows an actionable unavailable state with request id, then recovers on Retry", async () => {
    const envelope = { error: { code: "NOT_READY", message: "Database is not reachable.", request_id: "req-1" } };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(envelope, 503))
      .mockResolvedValueOnce(json(ready));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Database is not reachable.");
    expect(screen.getByText(/req-1/)).toBeInTheDocument();
    expect(screen.queryByText(/local services ready/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Workspace" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("treats a network failure as unavailable, never as ready", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/i);
  });
});
