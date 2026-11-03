import { describe, expect, it } from "vitest";
import {
  FIELD_TRAJECTORY_MIN_PX,
  buildTubeCompanion,
  createCompanionMaterial,
  createCompanionMesh,
  tubeScreenWidthPx,
  wellOfSegment,
  type CompanionWell,
} from "../src/features/scene/tubeLine";
import { tubeRadiusFor } from "../src/features/scene/fieldModel";

const well = (id: string, x: number, n: number): CompanionWell => ({
  id,
  position: [x, 0, 0],
  vertices: Array.from({ length: n }, (_, i) => ({ position: [0, -i * 100, 0] as [number, number, number] })),
  color: { r: 1, g: 0, b: 0 },
});

describe("screen-space tube companion", () => {
  it("is 3 CSS px wide with pixel units (not world units)", () => {
    const m = createCompanionMaterial();
    expect(FIELD_TRAJECTORY_MIN_PX).toBeGreaterThanOrEqual(3);
    expect(m.linewidth).toBe(FIELD_TRAJECTORY_MIN_PX);
    expect(m.worldUnits).toBe(false);
    m.dispose();
  });

  it("the default world tube is sub-pixel at overview zoom, so the companion is what stays visible", () => {
    const px = tubeScreenWidthPx(tubeRadiusFor(3500), 4000, 38, 700);
    expect(px).toBeLessThan(FIELD_TRAJECTORY_MIN_PX);
    // zoomed in, the world tube is thicker than the minimum again
    expect(tubeScreenWidthPx(tubeRadiusFor(3500), 60, 38, 700)).toBeGreaterThan(FIELD_TRAJECTORY_MIN_PX);
    expect(tubeScreenWidthPx(1, 0, 38, 700)).toBe(0);
  });

  it("merges all wells into one geometry/one mesh with a segment→well map", () => {
    const c = buildTubeCompanion([well("a", 0, 4), well("b", 500, 3), well("skip", 9, 1)])!;
    expect(c.segmentCount).toBe(5);
    expect(c.segmentStarts).toEqual([0, 3]);
    expect(c.wellIds).toEqual(["a", "b"]);
    expect(wellOfSegment(c.segmentStarts, c.wellIds, 2)).toBe("a");
    expect(wellOfSegment(c.segmentStarts, c.wellIds, 3)).toBe("b");
    expect(wellOfSegment(c.segmentStarts, c.wellIds, -1)).toBeNull();
    const mat = createCompanionMaterial();
    const mesh = createCompanionMesh(c, mat);
    expect(mesh.userData["role"]).toBe("tubeLine");
    expect(mesh.frustumCulled).toBe(false);
    // The offset of the grid position is applied to the polyline.
    const start = c.geometry.getAttribute("instanceStart");
    expect(start.getX(3)).toBe(500);
  });

  it("disposes its geometry and material", () => {
    const c = buildTubeCompanion([well("a", 0, 3)])!;
    const mat = createCompanionMaterial();
    let g = 0;
    let m = 0;
    c.geometry.addEventListener("dispose", () => (g += 1));
    mat.addEventListener("dispose", () => (m += 1));
    c.geometry.dispose();
    mat.dispose();
    expect([g, m]).toEqual([1, 1]);
    expect(buildTubeCompanion([])).toBeNull();
  });
});
