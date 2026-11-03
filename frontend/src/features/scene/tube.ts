import * as THREE from "three";
import type { PathPoint } from "./trajectory";

export interface TubeOptions {
  outerRadius: number;
  /** Inner radius; null makes a solid rod (no inner wall or annular caps). */
  innerRadius: number | null;
  /** Remove a wedge facing the default camera to show what is inside. */
  cutaway: boolean;
  radialSegments?: number;
}

const CUT_CENTER = Math.PI / 4;
const CUT_HALF = (70 * Math.PI) / 180;

/**
 * A hollow tube following path points (parallel-transport frames, so no twisting on curves).
 * Normals are written explicitly: outer wall outward, inner wall inward, caps along the axis.
 */
export function buildTubeGeometry(points: readonly PathPoint[], opts: TubeOptions): THREE.BufferGeometry {
  const n = points.length;
  const seg = opts.radialSegments ?? 36;
  const a0 = opts.cutaway ? CUT_CENTER + CUT_HALF : 0;
  const span = opts.cutaway ? Math.PI * 2 - 2 * CUT_HALF : Math.PI * 2;
  const thetas: number[] = Array.from({ length: seg + 1 }, (_, j) => a0 + (span * j) / seg);

  // Frames.
  const tans: THREE.Vector3[] = [];
  const poss: THREE.Vector3[] = points.map((p) => new THREE.Vector3(p.position[0], p.position[1], p.position[2]));
  for (let i = 0; i < n; i += 1) {
    const a = poss[Math.max(0, i - 1)]!;
    const b = poss[Math.min(n - 1, i + 1)]!;
    const t = b.clone().sub(a);
    tans.push(t.lengthSq() < 1e-12 ? new THREE.Vector3(...points[i]!.tangent) : t.normalize());
  }
  const ref = Math.abs(tans[0]!.x) > 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
  const normals: THREE.Vector3[] = [];
  const binormals: THREE.Vector3[] = [];
  let nPrev = ref.clone().sub(tans[0]!.clone().multiplyScalar(ref.dot(tans[0]!))).normalize();
  for (let i = 0; i < n; i += 1) {
    if (i > 0) {
      const axis = new THREE.Vector3().crossVectors(tans[i - 1]!, tans[i]!);
      const s = axis.length();
      if (s > 1e-9) {
        const angle = Math.atan2(s, tans[i - 1]!.dot(tans[i]!));
        nPrev = nPrev.clone().applyAxisAngle(axis.normalize(), angle);
      }
    }
    normals.push(nPrev.clone());
    binormals.push(new THREE.Vector3().crossVectors(tans[i]!, nPrev).normalize());
  }

  const pos: number[] = [];
  const nor: number[] = [];
  const idx: number[] = [];
  const dir = (i: number, th: number) => normals[i]!.clone().multiplyScalar(Math.cos(th)).add(binormals[i]!.clone().multiplyScalar(Math.sin(th)));

  const addWall = (radius: number, inward: boolean) => {
    const base = pos.length / 3;
    for (let i = 0; i < n; i += 1) {
      for (const th of thetas) {
        const d = dir(i, th);
        const p = poss[i]!.clone().add(d.clone().multiplyScalar(radius));
        pos.push(p.x, p.y, p.z);
        const nn = inward ? d.clone().negate() : d;
        nor.push(nn.x, nn.y, nn.z);
      }
    }
    const row = seg + 1;
    for (let i = 0; i < n - 1; i += 1) {
      for (let j = 0; j < seg; j += 1) {
        const a = base + i * row + j;
        const b = a + 1;
        const c = a + row;
        const d = c + 1;
        idx.push(a, c, b, b, c, d);
      }
    }
  };
  const addCap = (i: number, sign: 1 | -1) => {
    const base = pos.length / 3;
    const ri = opts.innerRadius ?? 0;
    for (const th of thetas) {
      for (const r of [opts.outerRadius, ri]) {
        const p = poss[i]!.clone().add(dir(i, th).multiplyScalar(r));
        pos.push(p.x, p.y, p.z);
        const nn = tans[i]!.clone().multiplyScalar(sign);
        nor.push(nn.x, nn.y, nn.z);
      }
    }
    for (let j = 0; j < seg; j += 1) {
      const a = base + j * 2;
      idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
    }
  };
  const addWallSide = (th: number, sign: 1 | -1) => {
    // Flat wall of the cut: radial strip between inner and outer radius along the path.
    const base = pos.length / 3;
    const ri = opts.innerRadius ?? 0;
    for (let i = 0; i < n; i += 1) {
      const d = dir(i, th);
      const tang = binormals[i]!.clone().multiplyScalar(Math.cos(th)).sub(normals[i]!.clone().multiplyScalar(Math.sin(th))).multiplyScalar(sign);
      for (const r of [opts.outerRadius, ri]) {
        const p = poss[i]!.clone().add(d.clone().multiplyScalar(r));
        pos.push(p.x, p.y, p.z);
        nor.push(tang.x, tang.y, tang.z);
      }
    }
    for (let i = 0; i < n - 1; i += 1) {
      const a = base + i * 2;
      idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
    }
  };

  addWall(opts.outerRadius, false);
  if (opts.innerRadius !== null) addWall(opts.innerRadius, true);
  if (n > 1) {
    addCap(0, -1);
    addCap(n - 1, 1);
  }
  if (opts.cutaway && n > 1) {
    addWallSide(thetas[0]!, -1);
    addWallSide(thetas[seg]!, 1);
  }

  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  g.setIndex(idx);
  g.computeBoundingSphere();
  g.computeBoundingBox();
  return g;
}
