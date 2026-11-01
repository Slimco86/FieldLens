// AX-7: model-proposed candidates are shown with state, reason, validator outcome and a source
// link; accepted/flagged/rejected/unresolved are distinguishable without color; an unresolved
// (model-read) candidate is never rendered as accepted.
import { cleanup, screen, within } from "@testing-library/react";
import { render } from "./render";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CandidateList } from "../src/features/uploads/CandidateList";
import { describeLocator } from "../src/features/uploads/EvidencePanel";
import type { SourceDocumentItem } from "../src/features/uploads/api";

const P = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const R = "11111111-1111-4111-8111-111111111111";
const D = "d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1";
const doc = { document_id: D, original_filename: "completion.pdf" } as unknown as SourceDocumentItem;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function cand(over: Record<string, unknown>) {
  return {
    candidate_id: crypto.randomUUID(),
    project_id: P,
    unit_id: "u1",
    source_revision_id: R,
    document_id: D,
    wellbore_id: null,
    subject: {},
    method: "model_proposal",
    evidence_class: "model_proposal",
    validation_state: "valid",
    state: "accepted",
    label: "model-proposed, rule-validated",
    reason_codes: [],
    validator_results: [],
    attributes: { kind: "measurement", attribute_key: "perforation.top_md", value_text: "4160.00", unit_as_written: "m", unit_defaulted: false },
    quote: "4160.00",
    evidence: { document_id: D, source_revision_id: R, locator: { kind: "text", document_id: D, source_revision_id: R, line_start: 2, line_end: 2 } },
    ...over,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function serve(items: unknown[], nextCursor: string | null = null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(json({ items, page: { limit: 25, next_cursor: nextCursor } }))),
  );
  render(<CandidateList projectId={P} doc={doc} describeLocator={describeLocator} />);
}

describe("candidate list", () => {
  it("distinguishes states by words and symbols and never shows unresolved as accepted", async () => {
    serve([
      cand({}),
      cand({
        state: "flagged",
        validation_state: "conflicting",
        label: "model-proposed, not accepted",
        reason_codes: ["parsed_conflict"],
        validator_results: [{ validator: "parsed_conflict", outcome: "flagged", reason: "parsed_conflict" }],
      }),
      cand({ state: "rejected", validation_state: "invalid", label: "model-proposed, not accepted", reason_codes: ["quote_not_in_span"] }),
      cand({
        state: "candidate",
        method: "model_read",
        validation_state: "unverified",
        label: "model-read, unverified",
        reason_codes: ["model_read_unverified"],
        quote: null,
        attributes: { kind: "page_read", item_type: "packer", name: "Production packer", depth_text: "3064 m", sizes_text: [] },
        evidence: { document_id: D, source_revision_id: R, locator: { kind: "pdf", document_id: D, source_revision_id: R, page: 3 } },
      }),
    ]);
    const list = await screen.findByRole("list", { name: /Model-proposed candidates for completion.pdf/ });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(4);
    const byState = Object.fromEntries(items.map((li) => [li.getAttribute("data-state"), li]));
    expect(within(byState.accepted).getByText(/Accepted by validators/)).toBeInTheDocument();
    expect(within(byState.flagged).getByText(/Flagged/)).toBeInTheDocument();
    expect(within(byState.flagged).getByText(/disagrees with the parsed source value/)).toBeInTheDocument();
    expect(within(byState.rejected).getByText(/Rejected/)).toBeInTheDocument();
    expect(within(byState.rejected).getByText(/the quote is not in the cited text/)).toBeInTheDocument();
    const unresolved = byState.candidate;
    expect(within(unresolved).getByText(/Unresolved candidate \(not an accepted fact\)/)).toBeInTheDocument();
    expect(within(unresolved).getByText(/model-read, unverified/)).toBeInTheDocument();
    expect(unresolved.textContent).not.toMatch(/Accepted/);
    // a link to the exact source location, as words
    expect(within(byState.accepted).getByText(/text line 2/)).toBeInTheDocument();
    expect(within(unresolved).getByText(/pdf page 3/)).toBeInTheDocument();
  });

  it("says so when there are no candidates and when loading fails", async () => {
    serve([]);
    expect(await screen.findByText(/No model-proposed candidates exist for this file/)).toBeInTheDocument();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ error: { code: "internal_error", message: "boom" } }, 500))));
    render(<CandidateList projectId={P} doc={doc} describeLocator={describeLocator} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/);
  });
});

describe("candidate list uses the design kit (TASK-034 integration)", () => {
  it("heading is a level-6 Title, state/validation/evidence class are chips with icons, load more is a kit button", async () => {
    serve([cand({}), cand({ state: "candidate", method: "model_read", validation_state: "unverified", label: "model-read, unverified", reason_codes: ["model_read_unverified"] })], "next");
    const heading = await screen.findByRole("heading", { name: "Model-proposed candidates", level: 6 });
    expect(heading.className).toMatch(/mantine-Title-root/);
    const list = screen.getByRole("list", { name: /Model-proposed candidates for completion.pdf/ });
    for (const li of within(list).getAllByRole("listitem")) {
      const chips = li.querySelectorAll("[data-tone], [data-evidence]");
      expect(chips.length).toBe(3); // state, validation, evidence class
      for (const chip of chips) expect(chip.querySelector("svg[aria-hidden='true']")).not.toBeNull();
      expect(li.textContent).not.toMatch(/[✔⚑✖○]/); // no unicode state symbols
    }
    const unresolved = within(list).getAllByRole("listitem")[1] as HTMLElement;
    expect(unresolved.querySelector("[data-evidence='model_proposal']")).toHaveTextContent("Model-read, unverified");
    expect(unresolved.querySelector("[data-tone='unknown']")).toHaveTextContent("Unresolved candidate (not an accepted fact)");
    const more = screen.getByRole("button", { name: "Load more candidates" });
    expect(more.className).toMatch(/mantine-Button-root/);
  });

  it("the empty note is the shared designed empty state", async () => {
    serve([]);
    const note = await screen.findByText(/No model-proposed candidates exist for this file/);
    expect(note.closest("div")?.className).toMatch(/empty/i);
  });
});
