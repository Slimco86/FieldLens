/**
 * Single-wellbore fly-over planner and player (TASK-096, CM-3/CM-4). Pure: no Three.js, no DOM.
 *
 * The plan is a display tour over an already-validated trajectory: stops are the located elements in
 * MD order (top to bottom), the camera rides a parallel-transport (rotation-minimising) frame along
 * the path so the view never rolls or flips, and the tour ends with a fit-all. It never alters or
 * resamples engineering data: positions are read from the path as given. Unlocated elements are
 * listed, never visited.
 */
import {
  add,
  clamp,
  cross,
  dot,
  lerp3,
  normalize,
  PREFERRED_OFF_TANGENT_DEG,
  rangeToFit,
  scale,
  sub,
  easeInOut,
  type OrbitPose,
  type V3,
  type ViewParams,
} from "./cameraPath";

export const MAX_TOUR_S = 60;
export const FIT_ALL_S = 2;
export const MIN_SPEED = 0.5;
export const MAX_SPEED = 4;
export const SPEEDS = [0.5, 1, 2, 4] as const;
const MAX_DWELL_S = 2.5;
const MAX_TRAVEL_S = 6;
const LONG_ELEMENT_M = 80;

export interface PathLike {
  mdMin: number;
  mdMax: number;
  at(md: number): { md: number; position: V3; tangent: V3 };
}

export interface PlanElement {
  id: string;
  label: string;
  zone: "downhole" | "surface" | "unlocated";
  mdTopM: number | null;
  mdBottomM: number | null;
  outerRadiusM: number;
}

export interface FlyStop {
  index: number;
  id: string;
  label: string;
  md: number;
  /** Arrival pose (view >= 35 degrees off the tangent by construction). */
  pose: OrbitPose;
  dwellS: number;
  travelS: number;
  /** Timeline (seconds at 1x): travel starts, camera arrives, stop ends. */
  startS: number;
  arriveS: number;
  endS: number;
}

export interface FlyOverPlan {
  stops: FlyStop[];
  unlocated: { id: string; label: string }[];
  /** Total at 1x including the closing fit-all; always <= MAX_TOUR_S. */
  durationS: number;
  /** Time at which the closing fit-all begins. */
  fitAllStartS: number;
  poseAtMd(md: number, range: number): OrbitPose;
  /** Pose at `timeS` (1x clock) while touring stops; stepped mode snaps to each stop pose. */
  poseAt(timeS: number, stepped?: boolean): { pose: OrbitPose; stopIndex: number; phase: "travel" | "dwell" | "fitall" };
}

// ------------------------------------------------------------------ parallel transport

export interface TransportFrame {
  md: number;
  position: V3;
  tangent: V3;
  /** Unit normal perpendicular to the tangent, carried without twist (roll only to keep the camera off the pole). */
  normal: V3;
}

function rotateAbout(v: V3, axis: V3, angle: number): V3 {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return add(add(scale(v, c), scale(cross(axis, v), s)), scale(axis, dot(axis, v) * (1 - c)));
}

/** Carry `normal` from tangent `a` to tangent `b` by the minimal rotation, re-orthogonalised. */
export function transportNormal(normal: V3, a: V3, b: V3): V3 {
  const axisRaw = cross(a, b);
  const sin = Math.hypot(axisRaw[0], axisRaw[1], axisRaw[2]);
  let n = normal;
  if (sin > 1e-9) n = rotateAbout(normal, scale(axisRaw, 1 / sin), Math.atan2(sin, dot(a, b)));
  // Remove any drift along the new tangent.
  n = sub(n, scale(b, dot(n, b)));
  const l = Math.hypot(n[0], n[1], n[2]);
  if (l < 1e-9) {
    const alt = cross(b, Math.abs(b[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0]);
    return normalize(alt, [1, 0, 0]);
  }
  return [n[0] / l, n[1] / l, n[2] / l];
}

/** Initial normal: world +x (else +z) made perpendicular to the first tangent. Deterministic. */
export function initialNormal(tangent: V3): V3 {
  const ref: V3 = Math.abs(tangent[0]) < 0.9 ? [1, 0, 0] : [0, 0, 1];
  return normalize(sub(ref, scale(tangent, dot(ref, tangent))), [1, 0, 0]);
}

export function buildFrames(path: PathLike, extraMds: readonly number[] = [], samples = 400): TransportFrame[] {
  const span = Math.max(path.mdMax - path.mdMin, 1e-6);
  const mds = new Set<number>();
  for (let i = 0; i <= samples; i += 1) mds.add(path.mdMin + (span * i) / samples);
  for (const m of extraMds) mds.add(clamp(m, path.mdMin, path.mdMax));
  const sorted = [...mds].sort((a, b) => a - b);
  const frames: TransportFrame[] = [];
  let prev: TransportFrame | null = null;
  for (const md of sorted) {
    const p = path.at(md);
    const tangent = normalize(p.tangent, [0, -1, 0]);
    const normal: V3 = capRoll(tangent, prev === null ? initialNormal(tangent) : transportNormal(prev.normal, prev.tangent, tangent));
    prev = { md: p.md, position: p.position, tangent, normal };
    frames.push(prev);
  }
  return frames;
}

export function frameAt(frames: readonly TransportFrame[], md: number): TransportFrame {
  let lo = 0;
  let hi = frames.length - 1;
  const m = clamp(md, frames[0]!.md, frames[hi]!.md);
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid]!.md <= m) lo = mid;
    else hi = mid - 1;
  }
  const a = frames[lo]!;
  const b = frames[Math.min(lo + 1, frames.length - 1)]!;
  if (b.md - a.md < 1e-9) return a;
  const t = (m - a.md) / (b.md - a.md);
  const tangent = normalize(lerp3(a.tangent, b.tangent, t), a.tangent);
  return { md: m, position: lerp3(a.position, b.position, t), tangent, normal: transportNormal(a.normal, a.tangent, tangent) };
}

/**
 * Viewing direction (target -> eye): `PREFERRED_OFF_TANGENT_DEG` off the tangent, from behind (up-hole).
 * The tangent-perpendicular normal comes from `buildFrames`, which keeps the elevation below
 * `MAX_ABS_Y` by rolling the carried normal about the tangent (see `capRoll`).
 */
export function viewDirection(frame: Pick<TransportFrame, "tangent" | "normal">, deg = PREFERRED_OFF_TANGENT_DEG): V3 {
  const a = (deg * Math.PI) / 180;
  return normalize(add(scale(frame.normal, Math.sin(a)), scale(frame.tangent, -Math.cos(a))));
}

/** Largest |y| of a viewing direction: keeps the world-up camera away from its pole (no spinning picture). */
export const MAX_ABS_Y = 0.95;

/**
 * Rotate `normal` about `tangent` by the smallest angle that brings the viewing direction's
 * elevation inside +-`MAX_ABS_Y`. Continuous along a path (a projection onto the feasible roll arc),
 * and a rotation about the tangent never changes the angle to it, so >= 35 degrees is preserved.
 */
export function capRoll(tangent: V3, normal: V3, deg = PREFERRED_OFF_TANGENT_DEG): V3 {
  const a = (deg * Math.PI) / 180;
  const b = cross(tangent, normal);
  const c0 = -Math.cos(a) * tangent[1];
  const R = Math.sin(a) * Math.hypot(normal[1], b[1]);
  const y0 = c0 + Math.sin(a) * normal[1];
  if (Math.abs(y0) <= MAX_ABS_Y || R < 1e-9) return normal;
  const phi0 = Math.atan2(b[1], normal[1]);
  const wanted = Math.sign(y0) * MAX_ABS_Y;
  const ratio = (wanted - c0) / R;
  const wrap = (x: number) => Math.atan2(Math.sin(x), Math.cos(x));
  let phi: number;
  if (Math.abs(ratio) >= 1) {
    phi = ratio > 0 ? phi0 : phi0 + Math.PI;
  } else {
    const d = Math.acos(ratio);
    const p1 = wrap(phi0 + d);
    const p2 = wrap(phi0 - d);
    phi = Math.abs(p1) <= Math.abs(p2) ? p1 : p2;
  }
  const n = add(scale(normal, Math.cos(phi)), scale(b, Math.sin(phi)));
  return normalize(n, normal);
}

// ------------------------------------------------------------------ planning

/** MD the camera looks at for an element: its centre, or a window below the top for long runs. */
export function stopMd(el: PlanElement, path: PathLike): number {
  if (el.zone === "surface" || el.mdTopM === null) return path.mdMin;
  const top = clamp(el.mdTopM, path.mdMin, path.mdMax);
  const bottom = clamp(el.mdBottomM ?? el.mdTopM, path.mdMin, path.mdMax);
  const len = Math.max(0, bottom - top);
  return len <= LONG_ELEMENT_M ? top + len / 2 : top + LONG_ELEMENT_M / 2;
}

export interface PlanOptions {
  view: ViewParams;
  /** Framing radius per element id (metres, bounding sphere incl. exaggeration); default from the element radius. */
  radii?: ReadonlyMap<string, number>;
}

export function buildFlyOverPlan(path: PathLike, elements: readonly PlanElement[], opts: PlanOptions): FlyOverPlan {
  const located = elements
    .map((el, order) => ({ el, order }))
    .filter(({ el }) => el.zone !== "unlocated")
    .map((x) => ({ ...x, md: stopMd(x.el, path), key: x.el.zone === "surface" || x.el.mdTopM === null ? path.mdMin : clamp(x.el.mdTopM, path.mdMin, path.mdMax) }))
    // MD order by the element top (surface first), ties by input order: stable and deterministic.
    .sort((a, b) => a.key - b.key || a.order - b.order);
  const unlocated = elements.filter((e) => e.zone === "unlocated").map((e) => ({ id: e.id, label: e.label }));
  const frames = buildFrames(path, [path.mdMin, path.mdMax, ...located.map((l) => l.md)]);
  const tanHalf = Math.tan((opts.view.fovDeg * Math.PI) / 360);

  const rangeAt = (md: number, radius: number): number => {
    const f = frameAt(frames, md);
    const dir = viewDirection(f);
    const w = Math.max(radius * 1.2, 10);
    const pts: V3[] = [];
    for (let k = -6; k <= 6; k += 1) pts.push(path.at(md + (w * k) / 6).position);
    const fit = (radius / Math.max(tanHalf, 1e-3)) * 1.15;
    return Math.max(fit, rangeToFit(pts, f.position, dir, opts.view), 2.5);
  };
  const poseAtMd = (md: number, range: number): OrbitPose => {
    const f = frameAt(frames, md);
    return { target: f.position, dir: viewDirection(f), range };
  };

  const n = located.length;
  const dwell = n === 0 ? 0 : Math.min(MAX_DWELL_S, 30 / n);
  const travelBudget = Math.max(0, MAX_TOUR_S - FIT_ALL_S - 0.5 - n * dwell);
  const gaps = located.map((l, i) => Math.abs(l.md - (i === 0 ? path.mdMin : located[i - 1]!.md)));
  const maxGap = Math.max(...gaps, 1e-6);
  const weights = gaps.map((g) => 0.5 + g / maxGap);
  const weightSum = weights.reduce((s, w) => s + w, 0) || 1;
  const ranges = located.map((l) => rangeAt(l.md, opts.radii?.get(l.el.id) ?? Math.max(l.el.outerRadiusM * 4, 12)));

  const stops: FlyStop[] = [];
  let clock = 0;
  located.forEach((l, i) => {
    const travel = n === 0 ? 0 : Math.min(MAX_TRAVEL_S, (travelBudget * weights[i]!) / weightSum);
    const stop: FlyStop = {
      index: i,
      id: l.el.id,
      label: l.el.label,
      md: l.md,
      pose: poseAtMd(l.md, ranges[i]!),
      dwellS: dwell,
      travelS: travel,
      startS: clock,
      arriveS: clock + travel,
      endS: clock + travel + dwell,
    };
    clock = stop.endS;
    stops.push(stop);
  });
  const fitAllStartS = clock;
  const durationS = clock + FIT_ALL_S;

  const startRange = stops.length > 0 ? stops[0]!.pose.range : 50;
  const poseAt: FlyOverPlan["poseAt"] = (timeS, stepped = false) => {
    if (stops.length === 0 || timeS >= fitAllStartS) {
      const last = stops[stops.length - 1];
      return { pose: last?.pose ?? poseAtMd(path.mdMin, startRange), stopIndex: stops.length - 1, phase: "fitall" };
    }
    let i = stops.findIndex((s) => timeS < s.endS);
    if (i < 0) i = stops.length - 1;
    const s = stops[i]!;
    if (timeS >= s.arriveS || stepped) return { pose: s.pose, stopIndex: i, phase: timeS >= s.arriveS ? "dwell" : "travel" };
    const prevMd = i === 0 ? path.mdMin : stops[i - 1]!.md;
    const prevRange = i === 0 ? s.pose.range : stops[i - 1]!.pose.range;
    const u = easeInOut(s.travelS <= 0 ? 1 : (timeS - s.startS) / s.travelS);
    const md = prevMd + (s.md - prevMd) * u;
    const range = Math.exp(Math.log(prevRange) + (Math.log(s.pose.range) - Math.log(prevRange)) * u);
    return { pose: poseAtMd(md, range), stopIndex: i, phase: "travel" };
  };

  return { stops, unlocated, durationS, fitAllStartS, poseAtMd, poseAt };
}

export function announceStop(plan: FlyOverPlan, index: number): string {
  const s = plan.stops[index];
  if (s === undefined) return "Fly-over complete: whole well in view.";
  return `Stop ${index + 1} of ${plan.stops.length}: ${s.label}, ${Math.round(s.md).toLocaleString("en-US")} m MD.`;
}

// ------------------------------------------------------------------ player

export type FlyOverState = "idle" | "playing" | "paused" | "finished";

export interface FlyOverStatus {
  state: FlyOverState;
  stopIndex: number;
  stopCount: number;
  stop: { id: string; label: string; md: number } | null;
  speed: number;
  announcement: string;
  unlocated: { id: string; label: string }[];
  totalS: number;
}

export interface PlayerFrame {
  pose: OrbitPose | null;
  stopIndex: number;
  phase: "travel" | "dwell" | "fitall" | "done";
  /** True on the frame the stop changed (announce/update UI only then). */
  stopChanged: boolean;
  /** True on the frame the closing fit-all starts: the caller flies to fit-all. */
  fitAllNow: boolean;
  finished: boolean;
}

export class FlyOverPlayer {
  state: FlyOverState = "idle";
  timeS = 0;
  speed = 1;
  stopIndex = -1;
  private fitAllFired = false;

  constructor(
    readonly plan: FlyOverPlan,
    private readonly stepped = false,
  ) {}

  setSpeed(x: number): void {
    this.speed = clamp(x, MIN_SPEED, MAX_SPEED);
  }

  play(): void {
    if (this.state === "paused") {
      this.state = "playing";
      return;
    }
    this.timeS = 0;
    this.stopIndex = -1;
    this.fitAllFired = false;
    this.state = this.plan.stops.length === 0 ? "idle" : "playing";
  }

  pause(): void {
    if (this.state === "playing") this.state = "paused";
  }

  stop(): void {
    this.state = "idle";
    this.stopIndex = -1;
    this.fitAllFired = false;
  }

  /** Jump to the arrival at stop `i` (clamped); returns that arrival pose. */
  seekStop(i: number): OrbitPose | null {
    if (this.plan.stops.length === 0) return null;
    const k = clamp(i, 0, this.plan.stops.length - 1);
    const s = this.plan.stops[k]!;
    this.timeS = s.arriveS;
    this.stopIndex = k;
    this.fitAllFired = false;
    if (this.state === "idle" || this.state === "finished") this.state = "paused";
    return s.pose;
  }

  next(): OrbitPose | null {
    return this.seekStop(Math.min(this.stopIndex + 1, this.plan.stops.length - 1));
  }

  prev(): OrbitPose | null {
    return this.seekStop(Math.max(this.stopIndex - 1, 0));
  }

  advance(dtS: number): PlayerFrame {
    if (this.state !== "playing") return { pose: null, stopIndex: this.stopIndex, phase: "done", stopChanged: false, fitAllNow: false, finished: false };
    this.timeS += Math.max(0, dtS) * this.speed;
    const at = this.plan.poseAt(Math.min(this.timeS, this.plan.fitAllStartS), this.stepped);
    const stopChanged = at.stopIndex !== this.stopIndex && at.phase !== "fitall";
    if (stopChanged) this.stopIndex = at.stopIndex;
    if (this.timeS >= this.plan.fitAllStartS) {
      const fitAllNow = !this.fitAllFired;
      this.fitAllFired = true;
      const finished = this.timeS >= this.plan.durationS;
      if (finished) this.state = "finished";
      return { pose: null, stopIndex: this.stopIndex, phase: "fitall", stopChanged: false, fitAllNow, finished };
    }
    return { pose: at.pose, stopIndex: this.stopIndex, phase: at.phase, stopChanged, fitAllNow: false, finished: false };
  }

  status(): FlyOverStatus {
    const s = this.plan.stops[this.stopIndex];
    const announcement =
      this.state === "idle"
        ? ""
        : this.state === "finished"
          ? announceStop(this.plan, -1)
          : s === undefined
            ? "Fly-over started."
            : announceStop(this.plan, this.stopIndex);
    return {
      state: this.state,
      stopIndex: this.stopIndex,
      stopCount: this.plan.stops.length,
      stop: s === undefined ? null : { id: s.id, label: s.label, md: s.md },
      speed: this.speed,
      announcement,
      unlocated: this.plan.unlocated,
      totalS: this.plan.durationS,
    };
  }
}

export const IDLE_FLY_STATUS: FlyOverStatus = { state: "idle", stopIndex: -1, stopCount: 0, stop: null, speed: 1, announcement: "", unlocated: [], totalS: 0 };
