import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { FieldScene } from "../src/features/scene/FieldScene";
import { render } from "./render";

const dir = join(import.meta.dirname, "fixtures", "asset-specs");
const spec = (f: string): unknown => JSON.parse(readFileSync(join(dir, f), "utf8"));

// A plain function (not vi.fn): rejected 404 promises are the normal "no spec yet" answer here.
let specImpl: (id: string) => Promise<unknown> = async () => {
  throw new Error("not configured");
};
vi.mock("../src/features/scene/api", () => ({
  getAssetSpec: (_p: string, id: string) => specImpl(id),
  generateAssetSpec: vi.fn(),
}));

const WELLS = [
  { id: "a", name: "Field A / A-1" },
  { id: "b", name: "Field A / A-2" },
  { id: "c", name: "Field A / A-3" },
];

function mockSpecs(files: Record<string, string | null | "fail">) {
  specImpl = async (id: string) => {
    const f = files[id];
    if (f === null || f === undefined) throw new ApiError(404, null, "none", null);
    if (f === "fail") throw new ApiError(500, null, "down", null);
    return { spec: spec(f), revision: 2, state: "current" };
  };
}

function mount(selected: string | null = null) {
  const onSelect = vi.fn();
  const onOpen = vi.fn();
  render(<FieldScene projectId="p" wellbores={WELLS} selectedId={selected} onSelect={onSelect} onOpen={onOpen} />);
  return { onSelect, onOpen };
}

describe("field scene (no WebGL in jsdom: list and inspector paths)", () => {
  it("lists every wellbore, labels the ones without a spec, and carries the permanent badges", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: null, c: "fail" });
    mount();
    expect(screen.getByTestId("illustrative-badge")).toHaveTextContent("Illustrative visual — not an engineering model");
    expect(screen.getByTestId("field-layout-badge")).toHaveTextContent(/schematic layout, not map positions/i);
    await waitFor(() => expect(screen.getByTestId("field-summary")).toHaveTextContent("1 with asset spec, 1 without, 1 failed"));
    const items = screen.getAllByRole("button").filter((b) => b.hasAttribute("data-wellbore-id"));
    expect(items.map((b) => b.getAttribute("data-status"))).toEqual(["spec", "missing", "error"]);
    expect(items[1]).toHaveTextContent("No asset spec yet");
  });

  it("shows a clear empty state when no wellbore has a spec and keeps the list", async () => {
    mockSpecs({});
    mount();
    expect(await screen.findByText("No visual asset specs yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button").filter((b) => b.hasAttribute("data-wellbore-id"))).toHaveLength(3);
    expect(screen.getByTestId("illustrative-badge")).toBeInTheDocument();
  });

  it("list selection selects first and opens the wellbore view on the second activation", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: "f12-unlocated.json" });
    const first = mount();
    await waitFor(() => expect(screen.getByTestId("field-summary")).toHaveTextContent("3 with asset spec"));
    fireEvent.click(document.querySelector('[data-wellbore-id="b"]')!);
    expect(first.onSelect).toHaveBeenCalledWith("b");
    expect(first.onOpen).not.toHaveBeenCalled();
  });

  it("an already selected wellbore opens; the inspector summarises it and Open is enabled", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: null });
    const { onOpen } = mount("b");
    await waitFor(() => expect(screen.getByTestId("field-inspector-name")).toHaveTextContent("Field A / A-2"));
    expect(screen.getByTestId("field-inspector")).toHaveTextContent("Revision");
    expect(screen.getByTestId("field-open")).toBeEnabled();
    fireEvent.click(document.querySelector('[data-wellbore-id="b"]')!);
    expect(onOpen).toHaveBeenCalledWith("b");
  });

  it("arrow keys move focus through the list", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: "f12-unlocated.json" });
    mount();
    await waitFor(() => expect(screen.getByTestId("field-summary")).toHaveTextContent("3 with asset spec"));
    const items = Array.from(document.querySelectorAll<HTMLButtonElement>("button[data-wellbore-id]"));
    items[0]!.focus();
    fireEvent.keyDown(items[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(items[1]!, { key: "End" });
    expect(document.activeElement).toBe(items[2]);
  });

  it("returning from the wellbore view focuses the selected list item", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: "f12-unlocated.json" });
    render(<FieldScene projectId="p" wellbores={WELLS} selectedId="b" onSelect={vi.fn()} onOpen={vi.fn()} restoreFocus />);
    await waitFor(() => expect(document.activeElement).toBe(document.querySelector('button[data-wellbore-id="b"]')));
  });

  it("does not steal focus on a first visit", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: "f5-generic.json", c: "f12-unlocated.json" });
    mount("b");
    await waitFor(() => expect(screen.getByTestId("field-summary")).toHaveTextContent("3 with asset spec"));
    expect(document.activeElement).toBe(document.body);
  });

  it("a missing-spec wellbore explains the placeholder in the inspector", async () => {
    mockSpecs({ a: "f14-dimensioned.json", b: null, c: null });
    mount("b");
    await waitFor(() => expect(screen.getByTestId("field-inspector")).toHaveTextContent("placeholder ring"));
  });
});
