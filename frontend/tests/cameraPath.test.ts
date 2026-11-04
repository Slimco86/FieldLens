import { describe, expect, it } from "vitest";
import {
  arrivalPose,
  easeInOut,
  flightDuration,
  inFrustum,
  length,
  normalize,
  offTangentDeg,
  offTangentDirection,
  planFlight,
  poseFromPositions,
  positionOf,
  rangeToFit,
  samplePose,
  sub,
  type OrbitPose,
  type V3,
} from "../src/features/scene/cameraPath";

const pose = (target: V3, dir: V3, range: number): OrbitPose => ({ target, dir: normalize(dir), range });
const VIEW = { fovDeg: 38, aspect: 1.6 };

describe("easing and duration (CM-1)", () => {
  it("is exact at the ends and monotonic", () => {
    expect(easeInOut(0)).toBe(0);
    expect(easeInOut(1)).toBe(1);
    expect(easeInOut(-3)).toBe(0);
    expect(easeInOut(9)).toBe(1);
    let prev = -1;
    for (let i = 0; i <= 100; i += 1) {
      const v = easeInOut(i / 100);
      expect(v).toBeGreaterThanOrEqual(prev);
      prev = v;
    }
    expect(easeInOut(0.5)).toBeCloseTo(0.5, 9);
  });

  it("scales with distance inside 0.6-2.0 s", () => {
    const a = pose([0, 0, 0], [1, 1, 1], 20);
    const near = flightDuration(a, pose([1, 0, 0], [1, 1, 1], 20));
    const mid = flightDuration(a, pose([200, -300, 0], [1, 1, 1], 20));
    const far = flightDuration(a, pose([20000, -3000, 0], [-1, 0.2, 1], 2000));
    expect(near).toBeGreaterThanOrEqual(0.6);
    expect(near).toBeLessThan(mid);
    expect(mid).toBeLessThan(far);
    expect(far).toBeLessThanOrEqual(2.0);
  });
});

describe("zoom-pan flight", () => {
  const from = pose([0, 0, 0], [1, 0.4, 1], 30);
  const to = pose([0, -2500, 0], [-1, 0.2, 0.5], 40);

  it("starts and ends exactly on the given poses (no jump)", () => {
    const f = planFlight(from, to);
    expect(samplePose(f, 0)).toEqual(from);
    expect(samplePose(f, 1)).toEqual(to);
    const early = samplePose(f, 0.001);
    expect(length(sub(early.target, from.target))).toBeLessThan(0.1);
    expect(Math.abs(early.range - from.range)).toBeLessThan(0.5);
  });

  it("zooms out on a long hop and back in, with unit directions and finite values", () => {
    const f = planFlight(from, to);
    const mid = samplePose(f, 0.5);
    expect(mid.range).toBeGreaterThan(Math.max(from.range, to.range) * 5);
    for (let i = 0; i <= 50; i += 1) {
      const p = samplePose(f, i / 50);
      expect(length(p.dir)).toBeCloseTo(1, 6);
      expect(Number.isFinite(p.range) && p.range > 0).toBe(true);
      expect(positionOf(p).every(Number.isFinite)).toBe(true);
    }
  });

  it("keeps a short hop level (no pointless zoom-out)", () => {
    const f = planFlight(from, pose([4, -3, 2], [1, 0.4, 1], 30));
    for (let i = 0; i <= 20; i += 1) expect(samplePose(f, i / 20).range).toBeLessThanOrEqual(30 * 1.001);
  });

  it("handles antipodal directions without NaN", () => {
    const f = planFlight(pose([0, 0, 0], [1, 0, 0], 10), pose([0, 0, 0], [-1, 0, 0], 10));
    for (let i = 0; i <= 10; i += 1) expect(length(samplePose(f, i / 10).dir)).toBeCloseTo(1, 6);
  });

  it("retarget from a mid-flight pose starts at that pose", () => {
    const f = planFlight(from, to);
    const midPose = samplePose(f, 0.4);
    const g = planFlight(midPose, from);
    expect(samplePose(g, 0)).toEqual(midPose);
  });

  it("poseFromPositions round-trips", () => {
    const p = poseFromPositions([10, 20, 30], [1, 2, 3]);
    const back = positionOf(p);
    expect(back[0]).toBeCloseTo(10);
    expect(back[1]).toBeCloseTo(20);
    expect(back[2]).toBeCloseTo(30);
  });
});

describe("arrival pose faces the trajectory (CM-2)", () => {
  const tangents: V3[] = [
    [0, -1, 0],
    [0, 1, 0],
    normalize([0.3, -1, 0.1]),
    normalize([1, -0.05, 0]),
    normalize([1, -1, 1]),
  ];
  const prefs: V3[] = [normalize([1, 0.42, 1]), [0, 1, 0], [0, -1, 0], [0, 0, 1], normalize([1, -0.9, 0.1])];

  it("is >= 35 degrees off the tangent for every combination", () => {
    for (const t of tangents) {
      for (const p of prefs) {
        const d = offTangentDirection(p, t);
        expect(offTangentDeg(d, t)).toBeGreaterThanOrEqual(35);
        expect(length(d)).toBeCloseTo(1, 9);
      }
    }
  });

  it("keeps an already-good direction untouched", () => {
    const p = normalize([1, 0, 0]);
    expect(offTangentDirection(p, [0, -1, 0])).toEqual(p);
  });

  it("puts the windowed trajectory samples inside the frustum", () => {
    const target: V3 = [100, -2000, 50];
    const tangent = normalize([0.2, -1, 0.1]);
    const window: V3[] = [];
    for (let k = -6; k <= 6; k += 1) window.push([target[0] + tangent[0] * 15 * k, target[1] + tangent[1] * 15 * k, target[2] + tangent[2] * 15 * k]);
    const pre = normalize([0, 1, 0]); // looking straight down the hole: worst case
    const a = arrivalPose({ target, fitRange: 12, preferredDir: pre, tangent, window, view: VIEW });
    expect(offTangentDeg(a.dir, tangent)).toBeGreaterThanOrEqual(35);
    for (const p of window) expect(inFrustum(p, a.target, a.dir, a.range, VIEW)).toBe(true);
    expect(inFrustum(target, a.target, a.dir, a.range, VIEW)).toBe(true);
  });

  it("rangeToFit grows with the window and a narrow aspect", () => {
    const pts: V3[] = [[0, 50, 0], [0, -50, 0]];
    const wide = rangeToFit(pts, [0, 0, 0], [1, 0, 0], { fovDeg: 38, aspect: 2 });
    const narrow = rangeToFit(pts, [0, 0, 0], [0, 0, 1], { fovDeg: 38, aspect: 0.5 });
    expect(wide).toBeGreaterThan(0);
    expect(narrow).toBeGreaterThan(0);
    expect(rangeToFit([], [0, 0, 0], [1, 0, 0], VIEW)).toBe(0);
  });

  it("without a tangent the fit range and preferred direction apply", () => {
    const a = arrivalPose({ target: [0, 0, 0], fitRange: 33, preferredDir: [0, 2, 0], tangent: null, window: [], view: VIEW });
    expect(a.range).toBe(33);
    expect(a.dir).toEqual([0, 1, 0]);
  });
});
