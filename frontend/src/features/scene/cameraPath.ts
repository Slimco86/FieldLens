/**
 * Pure camera maths (TASK-096, CM-1/CM-2). No Three.js, no DOM: plain tuples in render coordinates
 * (metres, +y up), so every function is unit-testable without WebGL. Display-only: nothing here
 * reads or alters trajectory/engineering values, it only chooses where the camera looks from.
 */

export type V3 = readonly [number, number, number];

export const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const scale = (a: V3, k: number): V3 => [a[0] * k, a[1] * k, a[2] * k];
export const dot = (a: V3, b: V3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const length = (a: V3): number => Math.hypot(a[0], a[1], a[2]);
export const lerp3 = (a: V3, b: V3, t: number): V3 => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
export function normalize(a: V3, fallback: V3 = [0, 1, 0]): V3 {
  const l = length(a);
  return l < 1e-12 ? fallback : [a[0] / l, a[1] / l, a[2] / l];
}
export const clamp = (x: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, x));

export const MIN_FLIGHT_S = 0.6;
export const MAX_FLIGHT_S = 2.0;
/** Minimum angle between the viewing line and the trajectory tangent at arrival (CM-2). */
export const MIN_OFF_TANGENT_DEG = 35;
/** Preferred arrival angle when the current view is too close to the tangent. */
export const PREFERRED_OFF_TANGENT_DEG = 60;

/** Smooth ease in/out (smootherstep-like cubic); exact 0 and 1 at the ends. */
export function easeInOut(t: number): number {
  const x = clamp(t, 0, 1);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
}

/** A camera as the orbit controls see it: the look-at target plus a unit direction and range to the eye. */
export interface OrbitPose {
  target: V3;
  /** Unit vector from the target to the camera. */
  dir: V3;
  /** Distance target -> camera, > 0. */
  range: number;
}

export function poseFromPositions(position: V3, target: V3): OrbitPose {
  const d = sub(position, target);
  const range = Math.max(length(d), 1e-6);
  return { target, dir: normalize(d, [0, 0, 1]), range };
}

export const positionOf = (p: OrbitPose): V3 => add(p.target, scale(p.dir, p.range));

/** Duration 0.6-2.0 s growing with the hop length relative to the viewing ranges (CM-1). */
export function flightDuration(from: OrbitPose, to: OrbitPose): number {
  const hop = length(sub(to.target, from.target));
  const r = Math.max(Math.min(from.range, to.range), 1e-6);
  const zoom = Math.abs(Math.log(to.range / from.range));
  const turn = Math.acos(clamp(dot(from.dir, to.dir), -1, 1));
  const metric = Math.log1p(hop / r) * 0.28 + zoom * 0.18 + turn * 0.18;
  return clamp(MIN_FLIGHT_S + metric, MIN_FLIGHT_S, MAX_FLIGHT_S);
}

function slerpDir(a: V3, b: V3, t: number): V3 {
  const c = clamp(dot(a, b), -1, 1);
  const omega = Math.acos(c);
  if (omega < 1e-6) return normalize(lerp3(a, b, t), a);
  if (Math.PI - omega < 1e-4) {
    // Antipodal: pass through an arbitrary perpendicular so the path is defined.
    const perp = normalize(cross(a, Math.abs(a[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0]), [1, 0, 0]);
    return t < 0.5 ? slerpDir(a, perp, t * 2) : slerpDir(perp, b, (t - 0.5) * 2);
  }
  const s = Math.sin(omega);
  return normalize(add(scale(a, Math.sin((1 - t) * omega) / s), scale(b, Math.sin(t * omega) / s)), a);
}

/**
 * Zoom-pan flight in the spirit of van Wijk & Nuij: the target pans by an eased fraction while the
 * range follows a log-space interpolation that rises toward `peak` mid-flight on long hops (zoom
 * out, pan, zoom in), so source and destination are both seen along the way. Exact at u = 0 and 1.
 */
export interface Flight {
  from: OrbitPose;
  to: OrbitPose;
  durationS: number;
  /** Mid-flight range, never below the larger endpoint range. */
  peakRange: number;
}

export function planFlight(from: OrbitPose, to: OrbitPose, durationS?: number): Flight {
  const hop = length(sub(to.target, from.target));
  const peak = Math.max(from.range, to.range, hop * 0.6);
  // Short hops stay level: only apply the bump when the hop is long against the ranges.
  const wanted = hop > 1.2 * Math.max(from.range, to.range) ? peak : Math.max(from.range, to.range);
  return { from, to, durationS: durationS ?? flightDuration(from, to), peakRange: wanted };
}

/** Pose at progress `t` in 0..1 (time fraction; easing is applied here). */
export function samplePose(f: Flight, t: number): OrbitPose {
  if (t <= 0) return f.from;
  if (t >= 1) return f.to;
  const u = easeInOut(t);
  const base = Math.exp(Math.log(f.from.range) + (Math.log(f.to.range) - Math.log(f.from.range)) * u);
  const w = Math.sin(Math.PI * u) ** 2;
  const range = base * Math.exp(w * Math.max(0, Math.log(f.peakRange / Math.max(base, 1e-6))));
  return { target: lerp3(f.from.target, f.to.target, u), dir: slerpDir(f.from.dir, f.to.dir, u), range };
}

// ------------------------------------------------------------------ CM-2: arrival facing the trajectory

/** Angle in degrees between the viewing line and the (unsigned) tangent line, 0..90. */
export function offTangentDeg(dir: V3, tangent: V3): number {
  const c = Math.abs(dot(normalize(dir), normalize(tangent)));
  return (Math.acos(clamp(c, 0, 1)) * 180) / Math.PI;
}

/**
 * Keep `preferred` when it already looks >= `minDeg` off the trajectory line; otherwise rotate it
 * about the tangent-perpendicular plane to `PREFERRED_OFF_TANGENT_DEG`, staying on the same side
 * (and as close to the preferred azimuth) as possible. The result is always >= `minDeg`.
 */
export function offTangentDirection(preferred: V3, tangent: V3, minDeg = MIN_OFF_TANGENT_DEG): V3 {
  const t = normalize(tangent, [0, -1, 0]);
  const p = normalize(preferred, [1, 0.4, 1]);
  if (offTangentDeg(p, t) >= minDeg + 1e-6) return p;
  const along = dot(p, t);
  let perp = sub(p, scale(t, along));
  if (length(perp) < 1e-6) {
    // Looking straight along the tangent: pick a horizontal-ish perpendicular, deterministic.
    perp = cross(t, Math.abs(t[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0]);
  }
  const u = normalize(perp);
  const a = (Math.max(PREFERRED_OFF_TANGENT_DEG, minDeg + 5) * Math.PI) / 180;
  const side = along >= 0 ? 1 : -1;
  return normalize(add(scale(u, Math.sin(a)), scale(t, Math.cos(a) * side)));
}

export interface ViewParams {
  fovDeg: number;
  aspect: number;
}

/**
 * Smallest range at which every point is inside the frustum (with `margin` < 1 of the half-angles
 * left free) for a camera looking at `target` from direction `dir`. Closed form: for each point
 * the depth must exceed |lateral| / tan(half fov).
 */
export function rangeToFit(points: readonly V3[], target: V3, dir: V3, view: ViewParams, margin = 0.92): number {
  const forward = scale(dir, -1);
  const worldUp: V3 = Math.abs(forward[1]) > 0.999 ? [0, 0, 1] : [0, 1, 0];
  const right = normalize(cross(forward, worldUp), [1, 0, 0]);
  const up = normalize(cross(right, forward), [0, 1, 0]);
  const tanV = Math.tan((view.fovDeg * Math.PI) / 360) * margin;
  const tanH = tanV * Math.max(view.aspect, 1e-3);
  let range = 0;
  for (const p of points) {
    const r = sub(p, target);
    const need = dot(r, dir) + Math.max(Math.abs(dot(r, right)) / tanH, Math.abs(dot(r, up)) / tanV);
    if (need > range) range = need;
  }
  return range;
}

/** Projection test: is `p` inside the frustum of a camera at `target + dir*range` looking at `target`? */
export function inFrustum(p: V3, target: V3, dir: V3, range: number, view: ViewParams, near = 0.01): boolean {
  const forward = scale(dir, -1);
  const worldUp: V3 = Math.abs(forward[1]) > 0.999 ? [0, 0, 1] : [0, 1, 0];
  const right = normalize(cross(forward, worldUp), [1, 0, 0]);
  const up = normalize(cross(right, forward), [0, 1, 0]);
  const eye = add(target, scale(dir, range));
  const r = sub(p, eye);
  const z = dot(r, forward);
  if (z <= near) return false;
  const tanV = Math.tan((view.fovDeg * Math.PI) / 360);
  const tanH = tanV * view.aspect;
  return Math.abs(dot(r, right)) <= z * tanH && Math.abs(dot(r, up)) <= z * tanV;
}

export interface ArrivalInput {
  target: V3;
  /** Range that frames the element itself (from its bounding sphere). */
  fitRange: number;
  /** Direction the camera currently looks from (kept when it already faces the trajectory). */
  preferredDir: V3;
  /** Trajectory tangent at the target and trajectory samples around it (a window of the path). */
  tangent: V3 | null;
  window: readonly V3[];
  view: ViewParams;
}

/**
 * CM-2 arrival pose: viewing line >= 35 degrees off the tangent and the windowed trajectory samples
 * inside the frustum. Without a tangent (nothing to face) the preferred direction and fit range apply.
 */
export function arrivalPose(input: ArrivalInput): OrbitPose {
  const dir = input.tangent === null ? normalize(input.preferredDir) : offTangentDirection(input.preferredDir, input.tangent);
  const windowRange = input.window.length === 0 ? 0 : rangeToFit(input.window, input.target, dir, input.view);
  return { target: input.target, dir, range: Math.max(input.fitRange, windowRange) };
}
