import * as THREE from "three";
import type { MaterialRole } from "../../design/scenePalette";
import { SceneResources, type GeoKey } from "./resources";
import type { SceneElement } from "./sceneModel";
import { buildTubeGeometry } from "./tube";
import type { WellPath } from "./trajectory";

export interface BuildContext {
  lib: SceneResources;
  path: WellPath;
  /** Radial exaggeration of downhole components (1 = physical). */
  exaggeration: number;
  /** Uniform scale of surface equipment and unlocated samples (1 = physical). */
  surfaceScale: number;
  cutaway: boolean;
}

const HALF_PI = Math.PI / 2;

/** Small drawing kit: adds shared-geometry meshes (scaled unit shapes) to one parent group. */
class Kit {
  constructor(
    readonly parent: THREE.Object3D,
    readonly lib: SceneResources,
    readonly generic: boolean,
  ) {}

  private place(m: THREE.Object3D, role: MaterialRole | null, x: number, y: number, z: number): void {
    m.position.set(x, y, z);
    if (role !== null) m.userData["matKey"] = `${role}|${this.generic ? 1 : 0}`;
    this.parent.add(m);
  }

  mesh(geo: GeoKey, role: MaterialRole, sx: number, sy: number, sz: number, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0): THREE.Mesh {
    const m = new THREE.Mesh(this.lib.geo(geo), this.lib.mat(role, this.generic));
    m.scale.set(sx, sy, sz);
    m.rotation.set(rx, ry, rz);
    this.place(m, role, x, y, z);
    return m;
  }

  /** Cylinder along Y by default; `axis` rotates it to X or Z. */
  cyl(role: MaterialRole, r: number, h: number, x = 0, y = 0, z = 0, axis: "x" | "y" | "z" = "y", low = false): THREE.Mesh {
    const rot: [number, number, number] = axis === "x" ? [0, 0, HALF_PI] : axis === "z" ? [HALF_PI, 0, 0] : [0, 0, 0];
    return this.mesh(low ? "cylLow" : "cyl", role, r, h, r, x, y, z, ...rot);
  }

  box(role: MaterialRole, w: number, h: number, d: number, x = 0, y = 0, z = 0): THREE.Mesh {
    return this.mesh("box", role, w, h, d, x, y, z);
  }

  sphere(role: MaterialRole, r: number, x = 0, y = 0, z = 0, sx = 1, sy = 1, sz = 1): THREE.Mesh {
    return this.mesh("sphere", role, r * sx, r * sy, r * sz, x, y, z);
  }

  /** Cone with its apex at +Y (or -Y when flipped). */
  cone(role: MaterialRole, r: number, h: number, x = 0, y = 0, z = 0, flip = false): THREE.Mesh {
    return this.mesh("cone", role, r, h, r, x, y, z, flip ? Math.PI : 0, 0, 0);
  }

  /** Torus ring around the Y axis (or X/Z axis). */
  ring(role: MaterialRole, r: number, tube: number, x = 0, y = 0, z = 0, axis: "x" | "y" | "z" = "y"): THREE.Mesh {
    const m = new THREE.Mesh(this.lib.torus(tube), this.lib.mat(role, this.generic));
    m.scale.set(r, r, r);
    if (axis === "y") m.rotation.x = HALF_PI;
    else if (axis === "x") m.rotation.y = HALF_PI;
    this.place(m, role, x, y, z);
    return m;
  }

  /** `count` small boxes spread around a circle (bolts, slips, pads) as one instanced draw. */
  around(role: MaterialRole, radius: number, y: number, count: number, w: number, h: number, d: number): THREE.InstancedMesh {
    const im = new THREE.InstancedMesh(this.lib.geo("box"), this.lib.mat(role, this.generic), count);
    const dummy = new THREE.Object3D();
    for (let i = 0; i < count; i += 1) {
      const a = (i / count) * Math.PI * 2;
      dummy.position.set(Math.cos(a) * radius, y, Math.sin(a) * radius);
      dummy.rotation.set(0, -a, 0);
      dummy.scale.set(d, h, w);
      dummy.updateMatrix();
      im.setMatrixAt(i, dummy.matrix);
    }
    im.instanceMatrix.needsUpdate = true;
    im.userData["matKey"] = `${role}|${this.generic ? 1 : 0}`;
    this.parent.add(im);
    return im;
  }

  /** Gate (default) or ball valve at a point; flow along `axis`; `s` is the body size. */
  valve(x: number, y: number, z: number, s: number, axis: "x" | "z" = "x", style: "gate" | "ball" = "gate", body: MaterialRole = "paintBlue", wheel: MaterialRole = "paintRed"): void {
    const g = new THREE.Group();
    const sub = new Kit(g, this.lib, this.generic);
    if (style === "gate") {
      sub.box(body, s * 1.0, s * 0.85, s * 0.7);
      sub.cyl("steelDark", s * 0.3, s * 0.55, 0, s * 0.7, 0);
      sub.cyl("steelBright", s * 0.05, s * 0.5, 0, s * 1.15, 0);
      sub.ring(wheel, s * 0.34, 0.14, 0, s * 1.4, 0, "y");
    } else {
      sub.sphere(body, s * 0.55);
      sub.cyl("steelDark", s * 0.12, s * 0.5, 0, s * 0.6, 0);
      sub.box(wheel, s * 0.1, s * 0.08, s * 0.9, 0, s * 0.9, 0);
    }
    sub.cyl("steelBright", s * 0.42, s * 0.1, -s * 0.55, 0, 0, "x", true);
    sub.cyl("steelBright", s * 0.42, s * 0.1, s * 0.55, 0, 0, "x", true);
    if (axis === "z") g.rotation.y = HALF_PI;
    g.position.set(x, y, z);
    this.parent.add(g);
  }
}

const tag = (g: THREE.Object3D, el: SceneElement): THREE.Object3D => {
  g.name = el.id;
  g.userData["elementId"] = el.id;
  return g;
};

// ---------------------------------------------------------------- downhole axial equipment

function packer(k: Kit, R: number, L: number): void {
  k.cyl("steelDark", R * 0.55, L);
  for (const dy of [-0.2, 0, 0.2]) {
    k.cyl("rubber", R, L * 0.15, 0, dy * L);
    k.cyl("brass", R * 0.97, L * 0.025, 0, dy * L + L * 0.085);
    k.cyl("brass", R * 0.97, L * 0.025, 0, dy * L - L * 0.085);
  }
  for (const s of [1, -1]) {
    k.cone("steel", R * 0.82, L * 0.14, 0, s * L * 0.33, 0, s === 1);
    k.around("steelBright", R * 0.88, s * L * 0.4, 8, R * 0.22, L * 0.1, R * 0.12);
    k.cyl("steel", R * 0.78, L * 0.04, 0, s * L * 0.47);
  }
}

function pumpEsp(k: Kit, R: number, L: number): void {
  const seg = (a: number, b: number) => ({ h: (b - a) * L, y: (-0.5 + (a + b) / 2) * L });
  const motor = seg(0, 0.42);
  const prot = seg(0.42, 0.58);
  const intake = seg(0.58, 0.66);
  const pump = seg(0.66, 0.97);
  k.cyl("paintGreen", R * 0.92, motor.h, 0, motor.y);
  for (let i = 0; i <= 5; i += 1) k.ring("steelDark", R * 0.93, 0.03, 0, motor.y - motor.h / 2 + (motor.h * i) / 5);
  k.cyl("steel", R * 0.86, prot.h, 0, prot.y);
  k.ring("brass", R * 0.88, 0.05, 0, prot.y + prot.h / 2);
  k.ring("brass", R * 0.88, 0.05, 0, prot.y - prot.h / 2);
  k.cyl("steelDark", R * 0.84, intake.h, 0, intake.y);
  for (let i = 0; i < 6; i += 1) {
    const a = (i / 6) * Math.PI * 2;
    k.box("rubber", R * 0.1, intake.h * 0.55, R * 0.34, Math.cos(a) * R * 0.82, intake.y, Math.sin(a) * R * 0.82).rotation.y = -a;
  }
  k.cyl("steelBright", R * 0.98, pump.h, 0, pump.y);
  const stages = 12;
  for (let i = 0; i <= stages; i += 1) k.cyl("steelDark", R * 1.03, pump.h * 0.012, 0, pump.y - pump.h / 2 + (pump.h * i) / stages, 0, "y", true);
  k.cone("steelBright", R * 0.9, L * 0.05, 0, L * 0.5 - L * 0.015, 0);
  // Power cable clamped along the side.
  k.cyl("rubber", R * 0.12, L * 1.0, R * 1.06, 0, 0);
  for (const f of [-0.35, -0.1, 0.15, 0.4]) k.ring("steelDark", R * 0.14, 0.08, R * 1.06, f * L, 0, "y");
}

function bearing(k: Kit, R: number, L: number): void {
  k.cyl("steelDark", R, L * 0.6);
  k.cyl("steelBright", R * 0.36, L);
  for (const s of [1, -1]) {
    k.cyl("steel", R * 1.04, L * 0.1, 0, s * L * 0.34);
    k.around("brass", R * 0.7, s * L * 0.28, 10, R * 0.2, L * 0.04, R * 0.16);
  }
  k.ring("brass", R * 1.01, 0.04, 0, 0);
}

function plug(k: Kit, R: number, L: number): void {
  k.cyl("paintOrange", R * 0.8, L * 0.5);
  k.cone("paintOrange", R * 0.8, L * 0.25, 0, L * 0.375, 0);
  k.cone("steelDark", R * 0.8, L * 0.25, 0, -L * 0.375, 0, true);
  k.cyl("rubber", R, L * 0.16, 0, L * 0.02);
  k.around("steelBright", R * 0.92, -L * 0.2, 8, R * 0.22, L * 0.1, R * 0.12);
  k.ring("brass", R * 0.82, 0.05, 0, L * 0.26);
}

function nipple(k: Kit, R: number, L: number): void {
  k.cyl("steelDark", R, L);
  for (const f of [-0.3, 0, 0.3]) k.ring("steelBright", R * 1.0, 0.07, 0, f * L);
  for (const s of [1, -1]) k.cyl("steel", R * 1.06, L * 0.12, 0, s * L * 0.44);
}

function valveDownhole(k: Kit, R: number, L: number): void {
  k.cyl("steelDark", R * 0.78, L);
  k.sphere("paintBlue", R * 1.1, 0, 0, 0, 1, Math.min(1, (L * 0.5) / (R * 1.1)), 1);
  for (const s of [1, -1]) k.cyl("steel", R, L * 0.1, 0, s * L * 0.4);
  k.cyl("steelBright", R * 0.16, R * 1.1, R * 1.2, 0, 0, "x");
  k.ring("paintRed", R * 0.38, 0.14, R * 1.8, 0, 0, "x");
}

function mandrel(k: Kit, R: number, L: number): void {
  k.cyl("steel", R * 0.85, L);
  for (const s of [1, -1]) k.cyl("steelBright", R, L * 0.08, 0, s * L * 0.46);
  const pr = R * 0.45;
  k.cyl("paintYellow", pr, L * 0.7, R * 0.78, -L * 0.02, 0);
  k.mesh("dome", "paintYellow", pr, pr, pr, R * 0.78, L * 0.33, 0);
  k.ring("brass", pr * 1.02, 0.07, R * 0.78, -L * 0.28, 0, "y");
  k.box("steelDark", R * 0.2, L * 0.12, R * 0.34, R * 1.2, L * 0.1, 0);
}

/**
 * Wellhead: casing-head spool and tubing spool (blue-grey steel) between dark flanges with stud rings, brass
 * seal rings, a red and a blue gate valve with contrasting handwheels, and a pressure gauge with a cream dial.
 * Repeated studs are instanced; everything uses shared unit geometries and the shared material cache.
 */
function wellheadBody(k: Kit, R: number, H: number): void {
  const y0 = -H / 2;
  // Casing head: base flange, spool, mid flange.
  k.cyl("steelDark", R, H * 0.12, 0, y0 + H * 0.06);
  k.around("steelBright", R * 0.88, y0 + H * 0.06, 16, R * 0.08, H * 0.16, R * 0.08);
  k.cyl("casing", R * 0.7, H * 0.28, 0, y0 + H * 0.26);
  k.cyl("steelDark", R * 0.9, H * 0.08, 0, y0 + H * 0.44);
  k.around("brass", R * 0.8, y0 + H * 0.44, 12, R * 0.07, H * 0.11, R * 0.07);
  // Tubing spool and top flange.
  k.cyl("steel", R * 0.62, H * 0.3, 0, y0 + H * 0.63);
  k.ring("brass", R * 0.64, 0.05, 0, y0 + H * 0.5);
  k.cyl("steelDark", R * 0.8, H * 0.08, 0, y0 + H * 0.82);
  k.around("steelBright", R * 0.7, y0 + H * 0.82, 12, R * 0.07, H * 0.12, R * 0.07);
  k.cyl("steelBright", R * 0.4, H * 0.1, 0, y0 + H * 0.95);
  // Side outlets: one red valve with a blue wheel, one blue valve with a red wheel.
  const wing: [number, MaterialRole, MaterialRole][] = [
    [1, "paintRed", "paintBlue"],
    [-1, "paintBlue", "paintRed"],
  ];
  for (const [s, body, wheel] of wing) {
    k.cyl("steel", R * 0.12, R * 0.9, s * R * 1.0, y0 + H * 0.26, 0, "x", true);
    k.valve(s * R * 1.7, y0 + H * 0.26, 0, R * 0.34, "x", "gate", body, wheel);
  }
  // Pressure gauge on the top cap: stem, bezel and cream dial facing +Z.
  k.cyl("steelDark", R * 0.05, R * 0.3, 0, y0 + H * 1.0 + R * 0.1, 0, "y", true);
  k.cyl("steelBright", R * 0.17, R * 0.06, 0, y0 + H * 1.0 + R * 0.34, 0, "z", true);
  k.cyl("paintCream", R * 0.14, R * 0.07, 0, y0 + H * 1.0 + R * 0.34, R * 0.01, "z", true);
}

function christmasTree(k: Kit, R: number, H: number): void {
  const y0 = -H / 2;
  k.cyl("steelDark", R * 0.7, H * 0.05, 0, y0 + H * 0.025);
  k.around("steelBright", R * 0.6, y0 + H * 0.025, 12, R * 0.06, H * 0.05, R * 0.06);
  const s = R * 0.55;
  k.cyl("steel", R * 0.2, H * 0.78, 0, y0 + H * 0.44);
  k.valve(0, y0 + H * 0.18, 0, s, "x", "gate", "paintBlue");
  k.box("paintBlue", R * 0.34, R * 0.42, R * 0.34, 0, y0 + H * 0.5, 0);
  // Flow cross arms: wing valves, choke on the +X arm.
  k.cyl("steel", R * 0.13, R * 2.0, 0, y0 + H * 0.5, 0, "x");
  k.valve(-R * 0.75, y0 + H * 0.5, 0, s * 0.8, "x", "gate", "paintBlue");
  k.valve(R * 0.62, y0 + H * 0.5, 0, s * 0.8, "x", "gate", "paintBlue");
  k.box("brass", R * 0.3, R * 0.3, R * 0.3, R * 1.18, y0 + H * 0.5, 0);
  k.cyl("steelBright", R * 0.06, R * 0.5, R * 1.18, y0 + H * 0.5 + R * 0.3, 0);
  k.ring("paintRed", R * 0.2, 0.14, R * 1.18, y0 + H * 0.5 + R * 0.55, 0, "y");
  k.valve(0, y0 + H * 0.72, 0, s * 0.85, "z", "ball", "paintBlue");
  k.cyl("steel", R * 0.2, H * 0.12, 0, y0 + H * 0.86);
  k.cyl("steelBright", R * 0.26, H * 0.03, 0, y0 + H * 0.93);
  // Pressure gauge.
  k.cyl("steelDark", R * 0.12, R * 0.12, 0, y0 + H * 0.97, 0, "z");
  k.cyl("steelBright", R * 0.03, R * 0.2, 0, y0 + H * 0.93 + R * 0.12);
}

function genericBlock(k: Kit, R: number, L: number): void {
  k.box("genericGrey", R * 2, L, R * 2);
  const edges = new THREE.LineSegments(k.lib.track(new THREE.EdgesGeometry(new THREE.BoxGeometry(R * 2, L, R * 2))), k.lib.lineMat());
  k.parent.add(edges);
}

// ---------------------------------------------------------------- surface equipment (centred about the origin)

function separator(k: Kit, R: number, L: number): void {
  const bodyL = L - R * 1.6;
  k.cyl("paintCream", R, bodyL, 0, R * 1.2, 0, "x");
  for (const s of [1, -1]) {
    const d = k.mesh("dome", "paintCream", R, R * 0.8, R, s * bodyL * 0.5, R * 1.2, 0, 0, 0, -s * HALF_PI);
    d.userData["matKey"] = "paintCream|" + (k.generic ? 1 : 0);
  }
  for (const s of [-0.3, 0.3]) {
    k.box("steelDark", R * 0.16, R * 0.9, R * 1.8, s * L, R * 0.45, 0);
    k.box("steelDark", R * 0.5, R * 0.08, R * 2.2, s * L, R * 0.0, 0);
  }
  k.ring("paintBlue", R * 1.005, 0.015, bodyL * 0.2, R * 1.2, 0, "x");
  k.ring("paintBlue", R * 1.005, 0.015, -bodyL * 0.2, R * 1.2, 0, "x");
  const nozzle = (x: number, y: number, up: boolean, r: number) => {
    k.cyl("steel", r, R * 0.55, x, y + (up ? 1 : -1) * R * 0.25);
    k.cyl("steelBright", r * 1.45, R * 0.08, x, y + (up ? 1 : -1) * R * 0.52);
  };
  nozzle(-bodyL * 0.38, R * 2.2, true, R * 0.14);
  nozzle(bodyL * 0.3, R * 2.2, true, R * 0.12);
  nozzle(bodyL * 0.38, R * 0.2, false, R * 0.14);
  k.cyl("steelDark", R * 0.3, R * 0.14, 0, R * 2.22);
  k.cyl("steelBright", R * 0.32, R * 0.04, 0, R * 2.3);
  k.cyl("steelDark", R * 0.05, R * 0.4, -bodyL * 0.12, R * 2.35);
  k.sphere("paintRed", R * 0.12, -bodyL * 0.12, R * 2.6, 0);
}

function choke(k: Kit, R: number, L: number): void {
  k.cyl("steelDark", R * 0.55, L, 0, 0, 0, "x");
  k.box("brass", L * 0.34, R * 1.3, R * 1.3, 0, 0, 0);
  k.cyl("steelDark", R * 0.35, R * 1.0, 0, R * 1.1, 0);
  k.cyl("steelBright", R * 0.08, R * 0.9, 0, R * 1.9, 0);
  k.ring("paintRed", R * 0.55, 0.12, 0, R * 2.4, 0, "y");
  for (const s of [1, -1]) k.cyl("steelBright", R * 0.8, R * 0.12, s * L * 0.46, 0, 0, "x");
}

function manifold(k: Kit, R: number, L: number): void {
  k.cyl("paintYellow", R, L, 0, R * 2, 0, "x");
  for (const s of [1, -1]) k.cyl("steelBright", R * 1.35, R * 0.18, s * L * 0.5, R * 2, 0, "x");
  const n = 4;
  for (let i = 0; i < n; i += 1) {
    const x = -L * 0.36 + (L * 0.72 * i) / (n - 1);
    k.cyl("paintYellow", R * 0.55, L * 0.3, x, R * 2, L * 0.15, "z");
    k.valve(x, R * 2, L * 0.17, R * 0.9, "z", "gate", "paintGreen");
    k.cyl("steelBright", R * 0.8, R * 0.14, x, R * 2, L * 0.31, "z");
    k.box("steelDark", R * 0.3, R * 1.8, R * 0.3, x, R * 0.9, L * 0.05);
  }
  for (const s of [-1, 1]) k.box("steelDark", L * 1.05, R * 0.2, R * 0.3, 0, R * 0.1, s * L * 0.18 + L * 0.05);
  for (let i = 0; i <= 4; i += 1) k.box("steelDark", R * 0.3, R * 0.2, L * 0.4, -L * 0.5 + (L * i) / 4, R * 0.1, L * 0.05);
}

function tank(k: Kit, R: number, H: number): void {
  k.cyl("paintCream", R, H);
  k.cone("paintGrey", R * 1.03, H * 0.14, 0, H * 0.57, 0);
  k.ring("paintRed", R * 1.003, 0.012, 0, H * 0.3, 0, "y");
  k.ring("paintRed", R * 1.003, 0.012, 0, -H * 0.1, 0, "y");
  k.cyl("steelDark", R * 1.06, H * 0.03, 0, -H * 0.5);
  k.cyl("steelBright", R * 0.08, H * 0.04, 0, H * 0.66);
  k.box("steelDark", R * 0.04, H * 1.0, R * 0.2, R * 1.04, 0, R * 0.3);
  k.box("steelDark", R * 0.03, H * 1.0, R * 0.03, R * 1.1, 0, R * 0.2);
  k.box("steelDark", R * 0.03, H * 1.0, R * 0.03, R * 1.1, 0, R * 0.4);
  for (let i = 0; i < 9; i += 1) k.box("steelBright", R * 0.04, R * 0.025, R * 0.2, R * 1.08, -H * 0.45 + (H * 0.9 * i) / 8, R * 0.3);
  k.cyl("steel", R * 0.1, R * 0.5, -R * 1.2, -H * 0.4, 0, "x");
  k.cyl("steelBright", R * 0.15, R * 0.08, -R * 1.4, -H * 0.4, 0, "x");
  k.cyl("steelDark", R * 0.22, H * 0.04, R * 0.35, H * 0.59, R * 0.2);
}

function pumpSurface(k: Kit, R: number, L: number): void {
  k.box("steelDark", L, R * 0.22, R * 2.6, 0, -R * 0.95, 0);
  for (const s of [-1, 1]) for (const t of [-1, 1]) k.box("steelDark", R * 0.3, R * 0.5, R * 0.3, s * L * 0.42, -R * 1.3, t * R * 1.1);
  const mL = L * 0.45;
  k.cyl("paintBlue", R, mL, -L * 0.25, 0, 0, "x");
  for (let i = 0; i < 9; i += 1) k.ring("paintBlue", R * 1.06, 0.05, -L * 0.25 - mL / 2 + (mL * (i + 0.5)) / 9, 0, 0, "x");
  k.box("steelDark", R * 0.7, R * 0.5, R * 0.8, -L * 0.25, R * 1.1, 0);
  k.cyl("paintYellow", R * 0.5, L * 0.1, -L * 0.0, 0, 0, "x");
  k.cyl("paintGreen", R * 0.95, L * 0.22, L * 0.18, 0, 0, "x");
  k.sphere("paintGreen", R * 0.95, L * 0.3, 0, 0, 0.4, 1, 1);
  k.cyl("steel", R * 0.22, R * 1.3, L * 0.18, R * 1.1, 0);
  k.cyl("steelBright", R * 0.34, R * 0.1, L * 0.18, R * 1.75, 0);
  k.cyl("steel", R * 0.22, R * 1.3, L * 0.34, R * 0.2, R * 0.5, "z");
  k.cyl("steelBright", R * 0.34, R * 0.1, L * 0.34, R * 0.2, R * 1.15, "z");
}

function flowline(k: Kit, R: number, route: readonly (readonly [number, number, number])[]): void {
  const pts = route.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
  for (let i = 0; i < pts.length - 1; i += 1) {
    const a = pts[i]!;
    const b = pts[i + 1]!;
    const len = a.distanceTo(b);
    if (len < 1e-6) continue;
    const m = k.mesh("cyl", "paintYellow", R, len, R, (a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
    m.rotation.setFromQuaternion(m.quaternion);
    const supports = Math.max(1, Math.floor(len / 6));
    for (let s = 0; s <= supports; s += 1) {
      const p = a.clone().lerp(b, s / supports);
      k.box("concrete", R * 1.4, p.y, R * 1.4, p.x, p.y / 2 - R, p.z);
    }
  }
  for (let i = 1; i < pts.length - 1; i += 1) k.sphere("paintYellow", R * 1.12, pts[i]!.x, pts[i]!.y, pts[i]!.z);
  for (const [i, dir] of [[0, 1], [pts.length - 1, -1]] as const) {
    const p = pts[i]!;
    const q = pts[i === 0 ? 1 : i - 1]!;
    const d = q.clone().sub(p).normalize().multiplyScalar(dir === 1 ? R * 0.1 : R * 0.1);
    const f = k.mesh("cyl", "steelBright", R * 1.6, R * 0.2, R * 1.6, p.x + d.x, p.y + d.y, p.z + d.z);
    f.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), q.clone().sub(p).normalize());
    f.rotation.setFromQuaternion(f.quaternion);
  }
}

// ---------------------------------------------------------------- path-following builders

function casingTube(el: SceneElement, ctx: BuildContext, group: THREE.Group, generic: boolean): void {
  const top = el.mdTopM ?? 0;
  const bottom = el.mdBottomM ?? 0;
  const R = el.outerRadiusM * ctx.exaggeration;
  const r = (el.innerRadiusM ?? el.outerRadiusM * 0.9) * ctx.exaggeration;
  const role: MaterialRole = el.kind === "tubing" ? "steelBright" : el.kind === "liner" ? "steel" : "casing";
  const step = Math.max(10, (bottom - top) / 80);
  const pts = ctx.path.slice(top, bottom, step);
  const geo = ctx.lib.track(buildTubeGeometry(pts, { outerRadius: R, innerRadius: r, cutaway: ctx.cutaway }));
  const mesh = new THREE.Mesh(geo, ctx.lib.mat(role, generic));
  mesh.userData["matKey"] = `${role}|${generic ? 1 : 0}`;
  group.add(mesh);
  // Shoe at the bottom (casing/liner) and hanger/head at the top.
  const shoeLen = Math.min(Math.max((bottom - top) * 0.012, 3), 40);
  if (el.kind !== "tubing" && bottom - top > shoeLen * 3) {
    const sp = ctx.path.slice(bottom - shoeLen, bottom);
    const sg = ctx.lib.track(buildTubeGeometry(sp, { outerRadius: R * 1.06, innerRadius: r, cutaway: ctx.cutaway }));
    const sm = new THREE.Mesh(sg, ctx.lib.mat("steelDark", generic));
    sm.userData["matKey"] = `steelDark|${generic ? 1 : 0}`;
    group.add(sm);
  }
  if (el.kind === "liner" && bottom - top > shoeLen * 3) {
    const hp = ctx.path.slice(top, top + shoeLen);
    const hg = ctx.lib.track(buildTubeGeometry(hp, { outerRadius: R * 1.08, innerRadius: r, cutaway: ctx.cutaway }));
    const hm = new THREE.Mesh(hg, ctx.lib.mat("brass", generic));
    hm.userData["matKey"] = `brass|${generic ? 1 : 0}`;
    group.add(hm);
  }
}

function perforations(el: SceneElement, ctx: BuildContext, group: THREE.Group, generic: boolean): void {
  const top = el.mdTopM ?? 0;
  const bottom = el.mdBottomM ?? 0;
  const R = el.outerRadiusM * ctx.exaggeration;
  const r = R * 0.9;
  const pts = ctx.path.slice(top, bottom, Math.max(5, (bottom - top) / 30));
  const band = new THREE.Mesh(ctx.lib.track(buildTubeGeometry(pts, { outerRadius: R * 1.03, innerRadius: r, cutaway: ctx.cutaway })), ctx.lib.mat("steelDark", generic));
  band.userData["matKey"] = `steelDark|${generic ? 1 : 0}`;
  group.add(band);
  const count = Math.min(240, Math.max(18, Math.round((bottom - top) / 1.5)));
  const im = new THREE.InstancedMesh(ctx.lib.geo("cone"), ctx.lib.mat("perforation", false), count);
  im.userData["matKey"] = "perforation|0";
  const dummy = new THREE.Object3D();
  const up = new THREE.Vector3(0, 1, 0);
  const len = R * 0.7;
  for (let i = 0; i < count; i += 1) {
    const p = ctx.path.at(top + ((i + 0.5) / count) * (bottom - top));
    const t = new THREE.Vector3(...p.tangent);
    const ref = Math.abs(t.x) > 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
    const n = ref.sub(t.clone().multiplyScalar(ref.dot(t))).normalize();
    const b = new THREE.Vector3().crossVectors(t, n);
    const a = i * (Math.PI / 3);
    const d = n.multiplyScalar(Math.cos(a)).add(b.multiplyScalar(Math.sin(a)));
    dummy.position.set(p.position[0], p.position[1], p.position[2]).add(d.clone().multiplyScalar(R * 1.03 + len / 2));
    dummy.quaternion.setFromUnitVectors(up, d);
    dummy.scale.set(R * 0.1, len, R * 0.1);
    dummy.updateMatrix();
    im.setMatrixAt(i, dummy.matrix);
  }
  im.instanceMatrix.needsUpdate = true;
  group.add(im);
}

type AxialBuilder = (k: Kit, R: number, L: number) => void;

const AXIAL: Partial<Record<SceneElement["kind"], AxialBuilder>> = {
  packer,
  pump_esp: pumpEsp,
  bearing,
  plug,
  nipple,
  valve: valveDownhole,
  mandrel,
  wellhead: wellheadBody,
  christmas_tree: christmasTree,
  generic_block: genericBlock,
  separator,
  choke,
  manifold,
  tank,
  pump_surface: pumpSurface,
};

/**
 * Build the Three.js object of one element: a Group tagged with `userData.elementId`, placed in
 * render coordinates relative to the wellhead. Downhole equipment is built along its own axis and
 * oriented to the path tangent; casing/liner/tubing and perforations follow the survey polyline.
 */
export function buildElement(el: SceneElement, ctx: BuildContext): THREE.Group {
  const group = new THREE.Group();
  tag(group, el);
  const generic = el.representation === "generic_illustrative";
  if (el.zone === "downhole" && (el.kind === "casing" || el.kind === "liner" || el.kind === "tubing")) {
    casingTube(el, ctx, group, generic);
    return group;
  }
  if (el.zone === "downhole" && el.kind === "perforation_interval") {
    perforations(el, ctx, group, generic);
    return group;
  }
  const inner = new THREE.Group();
  const k = new Kit(inner, ctx.lib, generic);
  if (el.kind === "flowline") {
    const route = el.route ?? [
      [1.2, 0.6, 0],
      [1.2 + el.lengthM * 0.4, 0.6, 0],
      [1.2 + el.lengthM * 0.4, 0.6, -el.lengthM * 0.6],
    ];
    flowline(k, el.outerRadiusM, route as readonly (readonly [number, number, number])[]);
    // Route points are wellhead-relative; the group stays at the origin.
    const s = ctx.surfaceScale;
    inner.scale.setScalar(s);
    group.add(inner);
    return group;
  }
  const build = AXIAL[el.kind];
  if (build === undefined) {
    // Tube/perforation kinds placed in the tray: a short sample piece.
    if (el.kind === "perforation_interval") {
      k.cyl("steelDark", el.outerRadiusM, el.lengthM);
      for (let i = 0; i < 24; i += 1) {
        const a = i * (Math.PI / 3);
        k.cone("perforation", el.outerRadiusM * 0.1, el.outerRadiusM * 0.7, Math.cos(a) * el.outerRadiusM * 1.35, (i / 24 - 0.5) * el.lengthM, Math.sin(a) * el.outerRadiusM * 1.35).rotation.set(0, 0, -Math.cos(a) * HALF_PI);
      }
    } else {
      const hollow = el.innerRadiusM ?? el.outerRadiusM * 0.9;
      const mesh = new THREE.Mesh(
        ctx.lib.track(buildTubeGeometry([{ md: 0, position: [0, -el.lengthM / 2, 0], tangent: [0, 1, 0] }, { md: 1, position: [0, el.lengthM / 2, 0], tangent: [0, 1, 0] }], { outerRadius: el.outerRadiusM, innerRadius: hollow, cutaway: ctx.cutaway })),
        ctx.lib.mat(el.kind === "tubing" ? "steelBright" : "casing", generic),
      );
      mesh.userData["matKey"] = `${el.kind === "tubing" ? "steelBright" : "casing"}|${generic ? 1 : 0}`;
      inner.add(mesh);
    }
  } else {
    build(k, el.outerRadiusM, el.lengthM);
  }
  group.add(inner);
  if (el.zone === "downhole") {
    group.position.set(el.position[0], el.position[1], el.position[2]);
    group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), new THREE.Vector3(...el.tangent));
    // Surface-class items at top of hole use the surface scale; downhole equipment exaggerates radius only.
    if (el.scaleClass === "surface") {
      inner.scale.setScalar(ctx.surfaceScale);
      group.quaternion.identity();
      const box = new THREE.Box3().setFromObject(inner);
      group.position.set(el.position[0], el.baseOffsetM * ctx.surfaceScale - box.min.y, el.position[2]);
    } else {
      inner.scale.set(ctx.exaggeration, 1, ctx.exaggeration);
    }
  } else {
    inner.scale.setScalar(ctx.surfaceScale);
    const box = new THREE.Box3().setFromObject(inner);
    group.position.set(el.position[0], el.baseOffsetM * ctx.surfaceScale - box.min.y, el.position[2]);
  }
  return group;
}

/** Axis-aligned bounds of a built element in world space (render coordinates). */
export function elementBounds(group: THREE.Object3D): THREE.Box3 {
  group.updateWorldMatrix(true, true);
  return new THREE.Box3().setFromObject(group);
}
