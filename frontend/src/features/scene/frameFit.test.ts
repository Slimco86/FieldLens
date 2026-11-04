import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { boundsExcludingLayers, fitDistance, shouldAutoFit } from "./frameFit";

describe("frame fit (UX-1)", () => {
  it("bounds ignore layers content however large or deep", () => {
    const root = new THREE.Group();
    const well = new THREE.Mesh(new THREE.BoxGeometry(2, 100, 2));
    const layer = new THREE.Group();
    layer.userData["fitIgnore"] = true;
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(50000, 50000));
    plane.position.y = -9000;
    layer.add(plane);
    root.add(well, layer);
    const b = boundsExcludingLayers(root);
    expect(b.max.y).toBe(50);
    expect(b.min.y).toBe(-50);
  });
  it("fit distance is independent of a 0-sized canvas and widens only to a clamp", () => {
    expect(fitDistance(100, 38, 0, 0, 1.1)).toBe(fitDistance(100, 38, 800, 800, 1.1));
    expect(fitDistance(100, 38, 100, 10000, 1.1)).toBeCloseTo(fitDistance(100, 38, 800, 800, 1.1) * 1.6);
  });
  it("auto-fit stops once the user moved the camera", () => {
    expect(shouldAutoFit(false, true)).toBe(true);
    expect(shouldAutoFit(true, true)).toBe(false);
    expect(shouldAutoFit(false, false)).toBe(false);
  });
});
