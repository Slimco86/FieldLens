import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";

/** Screen-space minimum width (CSS px) of every reconstructed trajectory in the field view. */
export const FIELD_TRAJECTORY_MIN_PX = 3;

export interface CompanionWell {
  id: string;
  /** Grid position of the wellbore (x, _, z); the polyline is in wellbore-local coordinates. */
  position: readonly [number, number, number];
  vertices: readonly { position: readonly [number, number, number] }[];
  color: { r: number; g: number; b: number };
}

export interface TubeCompanion {
  geometry: LineSegmentsGeometry;
  /** First segment index of every well (ascending) and the well it belongs to, for picking. */
  segmentStarts: number[];
  wellIds: string[];
  segmentCount: number;
}

/**
 * One merged polyline-segment geometry for all wells: the screen-space companion of the merged tube.
 * Display only; it reuses the same reconstructed vertices and never feeds a calculation.
 */
export function buildTubeCompanion(wells: readonly CompanionWell[]): TubeCompanion | null {
  let segments = 0;
  for (const w of wells) segments += Math.max(0, w.vertices.length - 1);
  if (segments === 0) return null;
  const pos = new Float32Array(segments * 6);
  const col = new Float32Array(segments * 6);
  const segmentStarts: number[] = [];
  const wellIds: string[] = [];
  let s = 0;
  for (const w of wells) {
    if (w.vertices.length < 2) continue;
    segmentStarts.push(s);
    wellIds.push(w.id);
    for (let i = 0; i + 1 < w.vertices.length; i += 1) {
      const a = w.vertices[i]!.position;
      const b = w.vertices[i + 1]!.position;
      pos.set([a[0] + w.position[0], a[1], a[2] + w.position[2], b[0] + w.position[0], b[1], b[2] + w.position[2]], s * 6);
      col.set([w.color.r, w.color.g, w.color.b, w.color.r, w.color.g, w.color.b], s * 6);
      s += 1;
    }
  }
  const geometry = new LineSegmentsGeometry();
  geometry.setPositions(pos);
  geometry.setColors(col);
  return { geometry, segmentStarts, wellIds, segmentCount: segments };
}

/** Well that owns a companion segment (binary search over the ascending starts). */
export function wellOfSegment(segmentStarts: readonly number[], wellIds: readonly string[], segment: number): string | null {
  if (segmentStarts.length === 0 || segment < 0) return null;
  let lo = 0;
  let hi = segmentStarts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (segmentStarts[mid]! <= segment) lo = mid;
    else hi = mid - 1;
  }
  return wellIds[lo] ?? null;
}

/** Material with a pixel-unit line width; `resolution` follows the canvas CSS size (set on resize only). */
export function createCompanionMaterial(widthPx: number = FIELD_TRAJECTORY_MIN_PX): LineMaterial {
  return new LineMaterial({ vertexColors: true, worldUnits: false, linewidth: widthPx, transparent: false });
}

export function createCompanionMesh(companion: TubeCompanion, material: LineMaterial): LineSegments2 {
  const mesh = new LineSegments2(companion.geometry, material);
  mesh.frustumCulled = false;
  mesh.userData["role"] = "tubeLine";
  return mesh;
}

/**
 * CSS-pixel diameter a world-space tube of `radiusM` covers at `distanceM` (vertical FOV in degrees);
 * the companion line is what stays visible when this is below `FIELD_TRAJECTORY_MIN_PX`.
 */
export function tubeScreenWidthPx(radiusM: number, distanceM: number, fovDeg: number, viewportHeightPx: number): number {
  if (!(distanceM > 0) || !(viewportHeightPx > 0)) return 0;
  const worldPerPx = (2 * distanceM * Math.tan((fovDeg * Math.PI) / 360)) / viewportHeightPx;
  return (2 * radiusM) / worldPerPx;
}
