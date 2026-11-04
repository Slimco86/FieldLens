import { afterEach, describe, expect, it, vi } from "vitest";
import { CameraRig } from "../src/features/scene/cameraRig";
import { normalize, positionOf, type OrbitPose } from "../src/features/scene/cameraPath";
import { buildFlyOverPlan, FlyOverPlayer } from "../src/features/scene/flyOverPlan";
import { WellPath } from "../src/features/scene/trajectory";

afterEach(() => vi.restoreAllMocks());

describe("reduced motion (CM-5)", () => {
  const to: OrbitPose = { target: [5, -800, 0], dir: normalize([1, 0.4, 1]), range: 55 };

  it("an instant flight applies the same final pose as the animated one, with no animation", () => {
    const animated = new CameraRig({ position: [100, 50, 100], target: [0, 0, 0] });
    animated.fly(to);
    let last = animated.step(0)!;
    while (animated.active) last = animated.step(0.05)!;

    const instant = new CameraRig({ position: [100, 50, 100], target: [0, 0, 0] });
    const applied = instant.fly(to, { instant: true })!;
    expect(instant.active).toBe(false);
    expect(instant.step(0.1)).toBeNull();
    expect(applied.target).toEqual(last.target);
    applied.position.forEach((v, i) => expect(v).toBeCloseTo(last.position[i]!, 9));
    expect(positionOf(to)).toEqual(applied.position);
  });

  it("stepped fly-over jumps stop to stop with the same announcements as the animated tour", () => {
    const stations = Array.from({ length: 61 }, (_, i) => ({ md_m: i * 50, tvd_m: i * 50, east_m: i * 5, north_m: 0 }));
    const path = WellPath.fromTrajectory({ stations, source: "t" }, 3000);
    const els = [100, 1000, 2500].map((md, i) => ({ id: `e${i}`, label: `E${i}`, zone: "downhole" as const, mdTopM: md, mdBottomM: md + 10, outerRadiusM: 0.1 }));
    const plan = buildFlyOverPlan(path, els, { view: { fovDeg: 38, aspect: 1.5 } });

    const run = (stepped: boolean) => {
      const p = new FlyOverPlayer(plan, stepped);
      p.play();
      const said: string[] = [];
      const poses: string[] = [];
      for (let i = 0; i < 4000 && p.state === "playing"; i += 1) {
        const f = p.advance(0.05);
        if (f.stopChanged) said.push(p.status().announcement);
        if (f.pose !== null) poses.push(f.pose.target.join(","));
      }
      return { said, distinctPoses: new Set(poses).size };
    };
    const smooth = run(false);
    const stepped = run(true);
    expect(stepped.said).toEqual(smooth.said);
    expect(stepped.distinctPoses).toBe(3);
    expect(smooth.distinctPoses).toBeGreaterThan(10);
  });
});
