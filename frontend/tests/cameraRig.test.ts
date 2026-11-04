import { describe, expect, it } from "vitest";
import { CameraRig } from "../src/features/scene/cameraRig";
import { normalize, positionOf, type OrbitPose } from "../src/features/scene/cameraPath";

const to: OrbitPose = { target: [0, -500, 0], dir: normalize([1, 0.3, 1]), range: 40 };

describe("CameraRig (CM-1, CM-6)", () => {
  it("flies from the synced pose and ends exactly on the target pose", () => {
    const rig = new CameraRig({ position: [100, 50, 100], target: [0, 0, 0] });
    expect(rig.fly(to)).toBeNull();
    expect(rig.active).toBe(true);
    const dur = rig.durationS;
    expect(dur).toBeGreaterThanOrEqual(0.6);
    expect(dur).toBeLessThanOrEqual(2);
    const first = rig.step(0.016)!;
    expect(Math.hypot(first.target[0], first.target[1], first.target[2])).toBeLessThan(5);
    let last = first;
    for (let i = 0; i < 400 && rig.active; i += 1) last = rig.step(0.016)!;
    expect(rig.active).toBe(false);
    expect(last.target).toEqual(to.target);
    const p = positionOf(to);
    last.position.forEach((v, i) => expect(v).toBeCloseTo(p[i]!, 9));
    expect(rig.step(0.016)).toBeNull();
  });

  it("retargets mid-flight from the current pose without a jump", () => {
    const rig = new CameraRig({ position: [100, 50, 100], target: [0, 0, 0] });
    rig.fly(to);
    for (let i = 0; i < 20; i += 1) rig.step(0.016);
    const before = rig.step(0.0)!;
    rig.fly({ target: [300, -100, 0], dir: normalize([0, 1, 1]), range: 60 });
    const after = rig.step(0.0)!;
    before.position.forEach((v, i) => expect(after.position[i]).toBeCloseTo(v, 6));
    before.target.forEach((v, i) => expect(after.target[i]).toBeCloseTo(v, 6));
  });

  it("cancel stops motion and keeps the last pose", () => {
    const rig = new CameraRig({ position: [10, 10, 10], target: [0, 0, 0] });
    rig.fly(to);
    rig.step(0.2);
    const cur = rig.current;
    rig.cancel();
    expect(rig.active).toBe(false);
    expect(rig.step(1)).toBeNull();
    expect(rig.current).toEqual(cur);
  });

  it("sync lets a user-moved camera become the flight origin", () => {
    const rig = new CameraRig();
    rig.sync({ position: [0, 0, 50], target: [0, 0, 0] });
    expect(rig.current.range).toBeCloseTo(50);
    rig.fly(to, { durationS: 1 });
    expect(rig.durationS).toBe(1);
  });
});
