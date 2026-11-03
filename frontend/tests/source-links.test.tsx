import { readFileSync } from "node:fs";
import { join } from "node:path";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SourceLink } from "../src/features/documents/SourceLink";
import { contentFailureText, documentContentUrl, isPdfSource } from "../src/features/documents/content";
import { Inspector } from "../src/features/scene/Inspector";
import { buildSceneModel, type SceneElement, type VisualAssetSpec } from "../src/features/scene/sceneModel";
import { WellPath } from "../src/features/scene/trajectory";
import { toTrajectoryState } from "../src/features/scene/trajectorySource";
import { render } from "./render";

const P = "11111111-1111-4111-8111-111111111111";
const D = "22222222-2222-4222-8222-222222222222";
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-/i;

let status = 206;
let body: unknown = null;
const calls: { url: string; range: string | null }[] = [];
beforeEach(() => {
  status = 206;
  body = null;
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, range: new Headers(init?.headers).get("range") });
      return new Response(body === null ? null : JSON.stringify(body), { status, headers: { "content-type": body === null ? "application/pdf" : "application/json" } });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("content helpers", () => {
  it("builds the same-origin url with #page and rejects odd pages", () => {
    expect(documentContentUrl(P, D, 3)).toBe(`/api/v1/projects/${P}/documents/${D}/content#page=3`);
    expect(documentContentUrl(P, D, 0)).toBe(`/api/v1/projects/${P}/documents/${D}/content`);
    expect(documentContentUrl(P, D, null)).not.toContain("#");
  });
  it("treats format first, extension otherwise", () => {
    expect(isPdfSource("pdf", "a.csv")).toBe(true);
    expect(isPdfSource("csv", "a.pdf")).toBe(false);
    expect(isPdfSource(undefined, "A.PDF")).toBe(true);
    expect(isPdfSource(undefined, null)).toBe(false);
  });
  it("words failures", () => {
    expect(contentFailureText(409, "hash_mismatch")).toContain("checksum");
    expect(contentFailureText(415, undefined)).toContain("Only PDF");
    expect(contentFailureText(503, undefined)).toContain("unavailable");
  });
});

describe("SourceLink", () => {
  it("makes no request until opened, then opens the viewer dialog at the page (C-1, C-4)", async () => {
    render(<SourceLink projectId={P} documentId={D} filename="SSR.pdf" page={3} locator="page 3, table 2" statement='Casing 9 5/8" at 2,431 m MD' />);
    expect(calls).toHaveLength(0);
    expect(screen.getByText("page 3, table 2", { exact: false })).toBeInTheDocument();
    expect(screen.getByText('Casing 9 5/8" at 2,431 m MD')).toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Open SSR.pdf in viewer at page 3" });
    await userEvent.click(trigger);
    const dlg = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dlg).getByTitle("SSR.pdf (PDF)")).toBeInTheDocument());
    expect(within(dlg).getByTitle("SSR.pdf (PDF)")).toHaveAttribute("src", `/api/v1/projects/${P}/documents/${D}/content#page=3`);
    expect(within(dlg).getByTitle("SSR.pdf (PDF)")).not.toHaveAttribute("sandbox");
    const tab = within(dlg).getByRole("link", { name: "Open in new tab" });
    expect(tab).toHaveAttribute("target", "_blank");
    expect(tab).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(calls).toHaveLength(1);
    expect(calls[0]?.range).toBe("bytes=0-0");
  });

  it("is labelled, closes on Escape and returns focus to the trigger (C-3)", async () => {
    render(<SourceLink projectId={P} documentId={D} filename="SSR.pdf" />);
    const trigger = screen.getByRole("button", { name: "Open SSR.pdf in viewer" });
    await userEvent.click(trigger);
    const dlg = await screen.findByRole("dialog", { name: /SSR\.pdf/ });
    expect(within(dlg).getByRole("button", { name: "Close document viewer" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it.each([
    [409, { error: { code: "CONFLICT", message: "x", details: { reason: "hash_mismatch" } } }, /checksum/],
    [415, { error: { code: "UNSUPPORTED_MEDIA_TYPE", message: "x" } }, /Only PDF/],
    [503, { error: { code: "UNAVAILABLE", message: "x" } }, /unavailable/],
  ])("shows the route failure %s instead of the frame (C-3)", async (code, payload, text) => {
    status = code;
    body = payload;
    render(<SourceLink projectId={P} documentId={D} filename="SSR.pdf" page={2} />);
    await userEvent.click(screen.getByRole("button", { name: /Open SSR.pdf in viewer/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByTitle("SSR.pdf (PDF)")).not.toBeInTheDocument();
  });

  it("keeps the jump to Sources for non-PDF files and never offers the viewer", async () => {
    const onOpen = vi.fn();
    render(<SourceLink projectId={P} documentId={D} filename="traj.csv" format="csv" onOpenSource={onOpen} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Open traj.csv in Sources" }));
    expect(onOpen).toHaveBeenCalledWith(D);
    expect(calls).toHaveLength(0);
  });

  it("never shows a bare id: unknown file name reads 'Document (filename unavailable)' (C-2)", () => {
    const { container } = render(<SourceLink projectId={P} documentId={D} />);
    expect(screen.getByRole("link", { name: "Open Document (filename unavailable) in Sources" })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(UUID);
  });

  it("falls back to filename + locator without a statement (C-2)", () => {
    render(<SourceLink projectId={P} documentId={D} filename="SSR.pdf" locator="page 3, row 5" />);
    expect(screen.getByText("SSR.pdf")).toBeInTheDocument();
    expect(screen.getByText("(page 3, row 5)", { exact: false })).toBeInTheDocument();
    expect(document.querySelector("q")).toBeNull();
  });
});

const spec = JSON.parse(readFileSync(join(import.meta.dirname, "fixtures", "asset-specs", "f14-dimensioned.json"), "utf8")) as VisualAssetSpec;
function element(evidence: unknown[]): SceneElement {
  const m = buildSceneModel(spec, WellPath.unavailable(1000, "test"), { surfaceScale: 1 });
  const el = m.elements[0]!;
  return { ...el, source: { ...el.source, evidence } as never };
}

describe("Inspector evidence and survey links", () => {
  it("shows filename, locator and quoted statement, and no bare UUID (C-2)", async () => {
    const el = element([
      { document_id: D, filename: "completion.pdf", page: 4, locator: "page 4, table 1, row 2", statement: 'Casing 9 5/8" at 2,431 m MD', quote: "extracted_record x" },
      { document_id: D, filename: "completion.pdf", page: 5, quote: "raw quote" },
      { document_id: D },
    ]);
    render(<Inspector element={el} projectId={P} />);
    const items = screen.getAllByTestId("inspector-evidence-item");
    expect(items[0]).toHaveTextContent('completion.pdf (page 4, table 1, row 2)Casing 9 5/8" at 2,431 m MD');
    expect(items[1]).toHaveTextContent("completion.pdf (page 5)raw quote");
    expect(items[2]).toHaveTextContent("Document (filename unavailable)");
    expect(screen.getByTestId("inspector-evidence").textContent).not.toMatch(UUID);
    await userEvent.click(within(items[0]!).getByRole("button", { name: "Open completion.pdf in viewer at page 4" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("links the survey file name and opens the PDF at the survey page", async () => {
    const dto = {
      survey_set: { document_id: D, run_id: "r", filename: "SSR.pdf", page: 7, survey_status: "as_built", station_count: 3, validated: true, used: true, reasons: [] },
      survey_status: "as_built",
      md_min_m: 0,
      md_max_m: 1000,
      md_reference: "RKB",
      tvd_reference: null,
      azimuth_reference: null,
      north_reference: "grid",
      surface_location: null,
      points: [],
      displayed_count: 0,
      source_count: 0,
      other_sets: [],
      warnings: [],
    };
    render(<Inspector element={null} projectId={P} survey={toTrajectoryState(dto as never)} />);
    expect(screen.getByTestId("survey-label")).toHaveTextContent("Survey: SSR.pdf, as-built, MD 0-1000 m");
    await userEvent.click(screen.getByRole("button", { name: "Open SSR.pdf in viewer at page 7" }));
    const dlg = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dlg).getByTitle("SSR.pdf (PDF)")).toHaveAttribute("src", expect.stringContaining("#page=7")));
  });
});
