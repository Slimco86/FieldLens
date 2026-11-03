import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MergeReview } from "../src/features/merge/MergeReview";
import { render } from "./render";

const P = "11111111-1111-4111-8111-111111111111";
const DOC = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";

const member = (name: string, role: "target" | "member", evidence: unknown[] = []) => ({
  key: name.toLowerCase(), kind: "label", name, role, wellbore_id: null, evidence,
});
const proposal = (id: string, status: string, over: Record<string, unknown> = {}) => ({
  proposal_id: id, project_id: P, run_id: "r1", status, acceptable: status === "pending", dataset_current: true, dataset_fingerprint: "f",
  rationale: "same well", decided_by: null, decided_at: null, decision_note: null, created_at: "2026-11-02T08:00:00Z",
  target: member("15/9-F-12", "target"),
  members: [member("F-12", "member", [{ document_id: DOC, quote: "Well F-12 is the same well as 15/9-F-12", content_sha256: "s" }])],
  guard_results: [
    { code: "g1_scope", passed: true, detail: "same project" },
    { code: "g3_designator", passed: status !== "blocked", detail: status === "blocked" ? "different designators" : "designators equal" },
  ],
  ...over,
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function install(items: ReturnType<typeof proposal>[]) {
  const state = { items, posts: [] as string[] };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, opts?: RequestInit) => {
      const url = String(input);
      const method = opts?.method ?? "GET";
      if (url === "/api/v1/session") return Promise.resolve(json({ csrf_token: "tok" }));
      if (method === "GET") return Promise.resolve(json({ items: state.items, total: state.items.length }));
      const m = /merge-proposals\/([^/]+)\/(accept|reject|revert)$/.exec(url);
      if (m === null) throw new Error(`unexpected ${method} ${url}`);
      state.posts.push(`${m[2]} ${m[1]}`);
      const next = { accept: "accepted", reject: "rejected", revert: "reverted" }[m[2] as "accept"];
      state.items = state.items.map((p) => (p.proposal_id === m[1] ? proposal(p.proposal_id, next!) : p));
      return Promise.resolve(json(state.items[0]));
    }),
  );
  return state;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Wellbore name matches (merge review)", () => {
  it("shows aliases, verified quotes and guard results, and merges nothing until Accept", async () => {
    const st = install([proposal("p1", "pending")]);
    render(<MergeReview projectId={P} onChanged={() => undefined} />);
    const list = await screen.findByRole("list", { name: "To review name matches" });
    expect(list).toHaveTextContent("F-12 → 15/9-F-12");
    expect(within(list).getByRole("list", { name: /Quotes for/ })).toHaveTextContent("Well F-12 is the same well as 15/9-F-12");
    expect(within(list).getByRole("list", { name: /Safety checks for/ })).toHaveTextContent("g1_scope");
    expect(st.posts).toEqual([]);
  });

  it("labels survey_match evidence as a server comparison, not a quote", async () => {
    install([
      proposal("p1", "pending", {
        members: [member("F-12", "member", [{ document_id: DOC, evidence_kind: "survey_match", quote: "211 stations, MD 0-3400 m, identical", content_sha256: "s" }])],
      }),
    ]);
    render(<MergeReview projectId={P} onChanged={() => undefined} />);
    const list = await screen.findByRole("list", { name: "To review name matches" });
    const ev = within(list).getByRole("list", { name: /Quotes for/ });
    expect(ev).toHaveTextContent("Matching survey: 211 stations, MD 0-3400 m, identical");
    expect(ev).toHaveTextContent("compared by the server");
    expect(ev.querySelector("q")).toBeNull();
  });

  it("accepts with the keyboard, refreshes the list and reports the change", async () => {
    const st = install([proposal("p1", "pending")]);
    const changed = vi.fn();
    render(<MergeReview projectId={P} onChanged={changed} />);
    const accept = await screen.findByRole("button", { name: "Accept F-12 → 15/9-F-12" });
    accept.focus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(st.posts).toEqual(["accept p1"]));
    expect(await screen.findByRole("list", { name: "Merged name matches" })).toBeInTheDocument();
    expect(changed).toHaveBeenCalledTimes(1);
  });

  it("keeps keyboard focus after Accept (Revert button), Reject and Revert (the proposal row)", async () => {
    install([proposal("p1", "pending"), proposal("p2", "pending", { target: member("15/9-F-13", "target"), members: [member("F-13", "member")] })]);
    render(<MergeReview projectId={P} onChanged={() => undefined} />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept F-12 → 15/9-F-12" }));
    const revert = await screen.findByRole("button", { name: "Revert F-12 → 15/9-F-12" });
    await waitFor(() => expect(document.activeElement).toBe(revert));
    await userEvent.click(screen.getByRole("button", { name: "Reject F-13 → 15/9-F-13" }));
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-proposal-id", "p2"));
    await userEvent.click(screen.getByRole("button", { name: "Revert F-12 → 15/9-F-12" }));
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-proposal-id", "p1"));
    expect(document.activeElement).not.toBe(document.body);
  });

  it("reverts an applied merge", async () => {
    const st = install([proposal("p1", "accepted")]);
    render(<MergeReview projectId={P} onChanged={() => undefined} />);
    await userEvent.click(await screen.findByRole("button", { name: "Revert F-12 → 15/9-F-12" }));
    await waitFor(() => expect(st.posts).toEqual(["revert p1"]));
    expect(await screen.findByRole("list", { name: "Reverted name matches" })).toBeInTheDocument();
  });

  it("offers only Reject for a blocked proposal and shows the failed check", async () => {
    install([proposal("p2", "blocked", { acceptable: false })]);
    render(<MergeReview projectId={P} onChanged={() => undefined} />);
    const list = await screen.findByRole("list", { name: "Cannot be accepted name matches" });
    expect(within(list).queryByRole("button", { name: /^Accept/ })).not.toBeInTheDocument();
    expect(list).toHaveTextContent("different designators");
    expect(list).toHaveTextContent("Failed");
  });

  it("says so when nothing was proposed", async () => {
    install([]);
    render(<MergeReview projectId={P} onChanged={() => undefined} />);
    expect(await screen.findByText("No name matches yet")).toBeInTheDocument();
  });
});
