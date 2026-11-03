import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { VisualAssetSpec } from "../src/features/scene/sceneModel";
import { buildSceneModel, COMPONENT_KINDS, isSurfaceKind, locatedMdMax } from "../src/features/scene/sceneModel";
import { WellPath } from "../src/features/scene/trajectory";
import { ComponentList } from "../src/features/scene/ComponentList";
import { Inspector } from "../src/features/scene/Inspector";

const dir = join(import.meta.dirname, "fixtures", "asset-specs");
const load = (f: string) => JSON.parse(readFileSync(join(dir, f), "utf8")) as VisualAssetSpec;
const FILES = ["f14-dimensioned.json", "f12-unlocated.json", "f5-generic.json"];

function model(file: string, scale = 1) {
  const spec = load(file);
  const path = WellPath.unavailable(Math.max(locatedMdMax(spec), 100), "test");
  return { spec, m: buildSceneModel(spec, path, { surfaceScale: scale }) };
}

describe("spec -> scene mapping", () => {
  it.each(FILES)("%s: every component gets an element with a label", (f) => {
    const { spec, m } = model(f);
    expect(m.elements).toHaveLength((spec.components ?? []).length);
    for (const el of m.elements) expect(el.label.trim().length).toBeGreaterThan(0);
    expect(m.downhole.length + m.surface.length + m.unlocated.length).toBe(m.elements.length);
  });

  it("covers every kind in the enum", () => {
    expect(new Set(COMPONENT_KINDS).size).toBe(20);
  });

  it("unlocated components go to the tray and keep no invented depth", () => {
    const { m } = model("f12-unlocated.json");
    expect(m.unlocated.length).toBeGreaterThan(0);
    for (const el of m.unlocated) {
      expect(el.mdTopM).toBeNull();
      expect(el.zone).toBe("unlocated");
    }
    expect(m.tray).not.toBeNull();
  });

  it("surface kinds sit on the ground plane near the wellhead", () => {
    const { m } = model("f14-dimensioned.json");
    for (const el of m.surface) {
      expect(isSurfaceKind(el.kind)).toBe(true);
      expect(el.position[1]).toBeCloseTo(0, 5);
    }
  });

  it("a missing trajectory yields a labelled placeholder", () => {
    const { m } = model("f5-generic.json");
    expect(m.path.available).toBe(false);
    expect(m.path.sourceLabel.length).toBeGreaterThan(0);
  });

  it("interpolates MD to position along the stations", () => {
    const path = WellPath.fromTrajectory(
      {
        source: "test",
        stations: [
          { md_m: 0, tvd_m: 0 },
          { md_m: 1000, tvd_m: 1000 },
          { md_m: 2000, tvd_m: 1500, east_m: 500 },
        ],
      },
      2000,
    );
    expect(path.available).toBe(true);
    expect(path.mdMax).toBe(2000);
  });
});

describe("component list and inspector", () => {
  it("selects on click and shows details in the inspector", () => {
    const { m } = model("f12-unlocated.json");
    const onSelect = vi.fn();
    const { rerender } = render(<ComponentList model={m} selectedId={null} onSelect={onSelect} />);
    expect(screen.getByText(/Unlocated components/)).toBeTruthy();
    const first = m.elements[0]!;
    fireEvent.click(document.querySelector(`button[data-element-id="${first.id}"]`)!);
    expect(onSelect).toHaveBeenCalledWith(first.id);
    rerender(<Inspector element={first} />);
    expect(screen.getByTestId("inspector-label").textContent).toBe(first.label);
    expect(screen.getByTestId("inspector-placement")).toBeTruthy();
    expect(screen.getByTestId("inspector-representation")).toBeTruthy();
  });

  it("moves focus with the arrow keys", () => {
    const { m } = model("f14-dimensioned.json");
    render(<ComponentList model={m} selectedId={null} onSelect={() => undefined} />);
    const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>("button[data-element-id]"));
    buttons[0]!.focus();
    fireEvent.keyDown(buttons[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(buttons[1]);
    fireEvent.keyDown(buttons[1]!, { key: "End" });
    expect(document.activeElement).toBe(buttons[buttons.length - 1]);
  });

  it("shows a prompt when nothing is selected", () => {
    render(<Inspector element={null} />);
    expect(screen.getByText(/Select a component/)).toBeTruthy();
  });
});
