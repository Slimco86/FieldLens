import { describe, expect, it, vi } from "vitest";
import { VisitHighlight } from "../src/features/scene/visitHighlight";
import { buildFlyOverPlan, FlyOverPlayer } from "../src/features/scene/flyOverPlan";
import { WellPath } from "../src/features/scene/trajectory";

function setup() {
  const apply = vi.fn();
  return { apply, hl: new VisitHighlight(apply) };
}

describe("VisitHighlight (TASK-110)", () => {
  it("lights the visited stop only when it changes", () => {
    const { apply, hl } = setup();
    hl.setVisited("a");
    hl.setVisited("a");
    hl.setVisited("a");
    expect(apply.mock.calls).toEqual([["a", true]]);
    hl.setVisited("b");
    expect(apply.mock.calls).toEqual([["a", true], ["a", false], ["b", true]]);
  });

  it("restores the user's selection when the fly-over ends or is cancelled", () => {
    const { apply, hl } = setup();
    hl.setSelected("sel");
    hl.setVisited("a");
    hl.setVisited(null);
    expect(apply.mock.calls).toEqual([["sel", true], ["a", true], ["a", false]]);
    // Visiting the selected element neither double-lights nor un-lights it afterwards.
    apply.mockClear();
    hl.setVisited("sel");
    hl.setVisited(null);
    expect(apply).not.toHaveBeenCalled();
  });

  it("clear() un-lights everything", () => {
    const { apply, hl } = setup();
    hl.setSelected("s");
    hl.setVisited("v");
    apply.mockClear();
    hl.clear();
    expect(apply.mock.calls).toEqual([["s", false], ["v", false]]);
  });

  it("player stop changes (the only publish points) are one per stop, with aria-live text", () => {
    const stations = Array.from({ length: 61 }, (_, i) => ({ md_m: i * 50, tvd_m: i * 50, east_m: i * 5, north_m: 0 }));
    const path = WellPath.fromTrajectory({ stations, source: "t" }, 3000);
    const els = [100, 1000, 2500].map((md, i) => ({ id: `e${i}`, label: `E${i}`, zone: "downhole" as const, mdTopM: md, mdBottomM: md + 10, outerRadiusM: 0.1 }));
    const plan = buildFlyOverPlan(path, els, { view: { fovDeg: 38, aspect: 1.5 } });
    const { apply, hl } = setup();
    const p = new FlyOverPlayer(plan, false);
    p.play();
    const said: string[] = [];
    for (let i = 0; i < 4000 && p.state === "playing"; i += 1) {
      const f = p.advance(0.05);
      if (f.stopChanged) {
        const s = p.status();
        hl.setVisited(s.stop?.id ?? null);
        said.push(s.announcement);
      }
    }
    expect(apply.mock.calls.filter((c) => c[1] === true)).toHaveLength(3);
    expect(said).toHaveLength(3);
    expect(said[0]).toMatch(/^Stop 1 of 3: E0,/);
  });

  it("reduced motion (stepped) lights the same stops as the animated tour", () => {
    const stations = Array.from({ length: 61 }, (_, i) => ({ md_m: i * 50, tvd_m: i * 50, east_m: i * 5, north_m: 0 }));
    const path = WellPath.fromTrajectory({ stations, source: "t" }, 3000);
    const els = [100, 1000, 2500].map((md, i) => ({ id: `e${i}`, label: `E${i}`, zone: "downhole" as const, mdTopM: md, mdBottomM: md + 10, outerRadiusM: 0.1 }));
    const plan = buildFlyOverPlan(path, els, { view: { fovDeg: 38, aspect: 1.5 } });
    const lit = (stepped: boolean) => {
      const apply = vi.fn();
      const hl = new VisitHighlight(apply);
      const p = new FlyOverPlayer(plan, stepped);
      p.play();
      for (let i = 0; i < 4000 && p.state === "playing"; i += 1) {
        if (p.advance(0.05).stopChanged) hl.setVisited(p.status().stop?.id ?? null);
      }
      return apply.mock.calls.filter((c) => c[1] === true).map((c) => c[0]);
    };
    expect(lit(true)).toEqual(lit(false));
  });
});
