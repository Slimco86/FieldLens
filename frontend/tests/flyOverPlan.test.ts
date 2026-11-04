import { describe, expect, it } from "vitest";
import { dot, length, normalize, offTangentDeg, type V3 } from "../src/features/scene/cameraPath";
import {
  buildFlyOverPlan,
  buildFrames,
  capRoll,
  FlyOverPlayer,
  MAX_TOUR_S,
  transportNormal,
  viewDirection,
  type PlanElement,
} from "../src/features/scene/flyOverPlan";
import { WellPath } from "../src/features/scene/trajectory";

/** Build -> hold -> drop-off-ish S-curve survey: deviated, then nearly horizontal. */
function surveyPath(): WellPath {
  const stations = [];
  for (let md = 0; md <= 3000; md += 50) {
    const incl = Math.min(90, Math.max(0, (md - 800) / 20)) * (Math.PI / 180);
    stations.push({ md_m: md, incl });
  }
  let tvd = 0;
  let east = 0;
  let prev = 0;
  let prevIncl = 0;
  const out = stations.map((s, i) => {
    if (i > 0) {
      const dm = s.md_m - prev;
      const mid = (s.incl + prevIncl) / 2;
      tvd += dm * Math.cos(mid);
      east += dm * Math.sin(mid);
    }
    prev = s.md_m;
    prevIncl = s.incl;
    return { md_m: s.md_m, tvd_m: tvd, east_m: east, north_m: 0 };
  });
  return WellPath.fromTrajectory({ stations: out, source: "test" }, 3000);
}

const el = (id: string, zone: PlanElement["zone"], top: number | null, bottom: number | null = top): PlanElement => ({
  id,
  label: id.toUpperCase(),
  zone,
  mdTopM: top,
  mdBottomM: bottom,
  outerRadiusM: 0.1,
});

const VIEW = { fovDeg: 38, aspect: 1.6 };

describe("parallel transport (CM-3)", () => {
  const path = surveyPath();
  const frames = buildFrames(path);

  it("keeps normals unit, perpendicular and free of roll jumps", () => {
    let maxStep = 0;
    for (let i = 0; i < frames.length; i += 1) {
      const f = frames[i]!;
      expect(length(f.normal)).toBeCloseTo(1, 6);
      expect(Math.abs(dot(f.normal, f.tangent))).toBeLessThan(1e-6);
      if (i > 0) {
        const p = frames[i - 1]!;
        maxStep = Math.max(maxStep, Math.acos(Math.min(1, Math.max(-1, dot(p.normal, f.normal)))));
      }
    }
    // Consecutive samples (7.5 m apart) never turn the view by more than a few degrees.
    // (bound covers the capRoll correction near vertical sections; no 90°+ flips)
    expect(maxStep).toBeLessThan(0.3);
  });

  it("capRoll leaves a fine direction alone and rotates only about the tangent", () => {
    const t: V3 = [0, -1, 0];
    expect(capRoll(t, [1, 0, 0])).toEqual([1, 0, 0]);
    const tan: V3 = normalize([1, 0.05, 0]);
    const raw: V3 = [0, 1, 0.02];
    const k = dot(raw, tan);
    const n = normalize([raw[0] - k * tan[0], raw[1] - k * tan[1], raw[2] - k * tan[2]]);
    const capped = capRoll(tan, n);
    expect(Math.abs(viewDirection({ tangent: tan, normal: capped })[1])).toBeLessThanOrEqual(0.95 + 1e-9);
    expect(Math.abs(dot(capped, tan))).toBeLessThan(1e-9);
    expect(offTangentDeg(viewDirection({ tangent: tan, normal: capped }), tan)).toBeCloseTo(60, 6);
  });

  it("transports a normal through a vertical hole without a flip", () => {
    const n = transportNormal([1, 0, 0], [0, -1, 0], [0, -1, 0]);
    expect(n).toEqual([1, 0, 0]);
  });

  it("view direction is always >= 35 degrees off the tangent and never vertical", () => {
    for (const f of frames) {
      const d = viewDirection(f);
      expect(offTangentDeg(d, f.tangent)).toBeGreaterThanOrEqual(35);
      expect(Math.abs(d[1])).toBeLessThanOrEqual(0.95 + 1e-9);
    }
  });
});

describe("fly-over plan (CM-3, CM-4 bound)", () => {
  const path = surveyPath();
  const elements: PlanElement[] = [
    el("tubing", "downhole", 0, 2800),
    el("packer", "downhole", 2100, 2102),
    el("tree", "surface", null),
    el("casing", "downhole", 0, 1500),
    el("perfs", "downhole", 2500, 2600),
    el("ghost", "unlocated", null),
  ];
  const plan = buildFlyOverPlan(path, elements, { view: VIEW });

  it("visits every located element exactly once in MD order, lists unlocated", () => {
    const ids = plan.stops.map((s) => s.id);
    expect(ids.sort()).toEqual(["casing", "packer", "perfs", "tree", "tubing"]);
    expect(new Set(ids).size).toBe(ids.length);
    const order = buildFlyOverPlan(path, elements, { view: VIEW }).stops;
    // surface and top-of-hole first (stable by input order), then by MD.
    expect(order.map((s) => s.id)).toEqual(["tubing", "tree", "casing", "packer", "perfs"]);
    const tops = [0, 0, 0, 2100, 2500];
    order.forEach((s, i) => expect(s.md).toBeGreaterThanOrEqual(tops[i]! - 1e-9));
    expect(plan.unlocated).toEqual([{ id: "ghost", label: "GHOST" }]);
  });

  it("is bounded to 60 s at 1x and ends with a fit-all phase", () => {
    expect(plan.durationS).toBeLessThanOrEqual(MAX_TOUR_S);
    expect(plan.fitAllStartS).toBeLessThan(plan.durationS);
    expect(plan.poseAt(plan.fitAllStartS + 0.1).phase).toBe("fitall");
    const many = Array.from({ length: 400 }, (_, i) => el(`e${i}`, "downhole", i * 7, i * 7 + 1));
    expect(buildFlyOverPlan(path, many, { view: VIEW }).durationS).toBeLessThanOrEqual(MAX_TOUR_S);
  });

  it("every pose along the timeline is finite, >= 35 degrees off tangent and continuous", () => {
    let prev: ReturnType<typeof plan.poseAt>["pose"] | null = null;
    for (let t = 0; t < plan.fitAllStartS; t += 0.05) {
      const { pose } = plan.poseAt(t);
      expect(pose.target.every(Number.isFinite) && Number.isFinite(pose.range) && pose.range > 0).toBe(true);
      if (prev !== null) {
        const hop = length([pose.target[0] - prev.target[0], pose.target[1] - prev.target[1], pose.target[2] - prev.target[2]]);
        expect(hop).toBeLessThan(120); // no teleporting between 50 ms samples
        expect(dot(pose.dir, prev.dir)).toBeGreaterThan(0.98);
      }
      prev = pose;
    }
  });

  it("stepped mode snaps to stop poses", () => {
    const s = plan.stops[1]!;
    const mid = plan.poseAt(s.startS + s.travelS / 2, true);
    expect(mid.pose).toEqual(s.pose);
  });

  it("no located elements gives an empty tour", () => {
    const p = buildFlyOverPlan(path, [el("ghost", "unlocated", null)], { view: VIEW });
    expect(p.stops).toHaveLength(0);
    expect(new FlyOverPlayer(p).status().stopCount).toBe(0);
    const pl = new FlyOverPlayer(p);
    pl.play();
    expect(pl.state).toBe("idle");
  });
});

describe("fly-over player (CM-4)", () => {
  const path = surveyPath();
  const plan = buildFlyOverPlan(path, [el("a", "downhole", 100, 200), el("b", "downhole", 1200, 1300), el("c", "downhole", 2600, 2700)], { view: VIEW });

  it("plays, pauses, resumes, stops and finishes with one fit-all", () => {
    const p = new FlyOverPlayer(plan);
    p.play();
    expect(p.state).toBe("playing");
    const changes: number[] = [];
    let fitAll = 0;
    for (let i = 0; i < 4000 && p.state === "playing"; i += 1) {
      const f = p.advance(0.05);
      if (f.stopChanged) changes.push(f.stopIndex);
      if (f.fitAllNow) fitAll += 1;
      if (i === 30) {
        p.pause();
        const t = p.timeS;
        expect(p.advance(1).pose).toBeNull();
        expect(p.timeS).toBe(t);
        p.play();
      }
    }
    expect(changes).toEqual([0, 1, 2]);
    expect(fitAll).toBe(1);
    expect(p.state).toBe("finished");
    expect(p.status().announcement).toMatch(/complete/i);
  });

  it("speed scales the clock and is clamped to 0.5x-4x", () => {
    const a = new FlyOverPlayer(plan);
    a.setSpeed(100);
    expect(a.speed).toBe(4);
    a.setSpeed(0.01);
    expect(a.speed).toBe(0.5);
    a.setSpeed(2);
    a.play();
    a.advance(1);
    expect(a.timeS).toBeCloseTo(2);
  });

  it("next/prev seek to stop arrivals and announce them", () => {
    const p = new FlyOverPlayer(plan);
    p.play();
    expect(p.next()).toEqual(plan.stops[0]!.pose);
    expect(p.next()).toEqual(plan.stops[1]!.pose);
    expect(p.status().announcement).toBe("Stop 2 of 3: B, 1,240 m MD.");
    expect(p.prev()).toEqual(plan.stops[0]!.pose);
    p.stop();
    expect(p.state).toBe("idle");
    expect(p.status().announcement).toBe("");
  });
});
