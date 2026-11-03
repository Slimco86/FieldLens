/**
 * Wellbore path for the viewer. Stations come from the deterministic minimum-curvature engine
 * (a later API replaces the prop; the interface below is the contract). The viewer only
 * interpolates between the given stations; it never smooths or re-derives MD/TVD.
 *
 * Render axes (Three.js, Y up), metres, origin = wellhead:  x = east,  y = -TVD (up positive),  z = -north.
 */
export interface TrajectoryStation {
  /** Measured depth along the hole, metres. */
  md_m: number;
  /** True vertical depth below the wellhead, metres. */
  tvd_m: number;
  /** Metres east of the wellhead; omitted when only a vertical section is known (treated as 0). */
  east_m?: number;
  /** Metres north of the wellhead; omitted when only a vertical section is known (treated as 0). */
  north_m?: number;
}

export interface TrajectoryInput {
  stations: readonly TrajectoryStation[];
  /** Short provenance text shown to the user, e.g. "minimum curvature, survey rev 4". */
  source: string;
}

export type Vec3 = readonly [number, number, number];

export interface PathPoint {
  md: number;
  position: Vec3;
  tangent: Vec3;
}

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

function normalize(v: [number, number, number]): Vec3 {
  const len = Math.hypot(v[0], v[1], v[2]);
  return len < 1e-12 ? [0, -1, 0] : [v[0] / len, v[1] / len, v[2] / len];
}

/** Why the survey input was refused (the viewer then falls back to the labelled vertical line). */
export function validateStations(input: TrajectoryInput | null | undefined): string | null {
  if (input === null || input === undefined) return "no trajectory was supplied";
  const s = input.stations;
  if (s.length < 2) return "fewer than two survey stations";
  for (let i = 0; i < s.length; i += 1) {
    const st = s[i]!;
    if (!finite(st.md_m) || !finite(st.tvd_m) || (st.east_m !== undefined && !finite(st.east_m)) || (st.north_m !== undefined && !finite(st.north_m))) {
      return `station ${i + 1} has a non-finite value`;
    }
    if (i > 0 && st.md_m <= s[i - 1]!.md_m) return "station measured depths are not strictly increasing";
  }
  return null;
}

/**
 * A polyline path indexed by MD. `available === false` is the labelled placeholder: a vertical line
 * whose depth equals MD. It is a drawing aid for orientation, never a survey.
 */
export class WellPath {
  readonly available: boolean;
  readonly mdMin: number;
  readonly mdMax: number;
  /** Text for the user: where the path comes from or why it is a placeholder. */
  readonly sourceLabel: string;
  /** True when the survey gave no east/north (vertical section only). */
  readonly horizontalKnown: boolean;
  private readonly md: Float64Array;
  private readonly pos: Float64Array;

  private constructor(md: Float64Array, pos: Float64Array, available: boolean, sourceLabel: string, horizontalKnown: boolean) {
    this.md = md;
    this.pos = pos;
    this.available = available;
    this.mdMin = md[0]!;
    this.mdMax = md[md.length - 1]!;
    this.sourceLabel = sourceLabel;
    this.horizontalKnown = horizontalKnown;
  }

  static fromTrajectory(input: TrajectoryInput | null | undefined, fallbackMdMax: number): WellPath {
    const problem = validateStations(input);
    if (problem !== null || input === null || input === undefined) return WellPath.unavailable(fallbackMdMax, problem ?? "no trajectory");
    const n = input.stations.length;
    const md = new Float64Array(n);
    const pos = new Float64Array(n * 3);
    let horizontal = false;
    input.stations.forEach((s, i) => {
      md[i] = s.md_m;
      pos[i * 3] = s.east_m ?? 0;
      pos[i * 3 + 1] = -s.tvd_m;
      pos[i * 3 + 2] = -(s.north_m ?? 0);
      if (s.east_m !== undefined || s.north_m !== undefined) horizontal = true;
    });
    return new WellPath(md, pos, true, input.source, horizontal);
  }

  /** Vertical placeholder `0..mdMax` (MD treated as depth), labelled as unavailable. */
  static unavailable(mdMax: number, reason: string): WellPath {
    const top = Math.max(mdMax, 10);
    return new WellPath(
      Float64Array.of(0, top),
      Float64Array.of(0, 0, 0, 0, -top, 0),
      false,
      `trajectory unavailable (${reason})`,
      false,
    );
  }

  /** True when MD lies on the path (tiny tolerance for float noise). */
  covers(md: number): boolean {
    return md >= this.mdMin - 1e-6 && md <= this.mdMax + 1e-6;
  }

  private segment(md: number): number {
    // Binary search for the segment [i, i+1] containing md (clamped).
    let lo = 0;
    let hi = this.md.length - 2;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (this.md[mid]! <= md) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }

  /** Linear interpolation of position and the tangent of the containing segment. */
  at(mdRaw: number): PathPoint {
    const md = Math.min(Math.max(mdRaw, this.mdMin), this.mdMax);
    const i = this.segment(md);
    const m0 = this.md[i]!;
    const m1 = this.md[i + 1]!;
    const t = (md - m0) / (m1 - m0);
    const a = i * 3;
    const b = a + 3;
    const p: [number, number, number] = [
      this.pos[a]! + (this.pos[b]! - this.pos[a]!) * t,
      this.pos[a + 1]! + (this.pos[b + 1]! - this.pos[a + 1]!) * t,
      this.pos[a + 2]! + (this.pos[b + 2]! - this.pos[a + 2]!) * t,
    ];
    return {
      md,
      position: p,
      tangent: normalize([this.pos[b]! - this.pos[a]!, this.pos[b + 1]! - this.pos[a + 1]!, this.pos[b + 2]! - this.pos[a + 2]!]),
    };
  }

  /**
   * Points along [mdTop, mdBottom]: the interval ends plus every survey station inside, so a
   * tube follows the survey exactly; long runs without stations are subdivided by `maxStep`.
   */
  slice(mdTop: number, mdBottom: number, maxStep = Number.POSITIVE_INFINITY, maxPoints = 400): PathPoint[] {
    const top = Math.max(mdTop, this.mdMin);
    const bottom = Math.min(mdBottom, this.mdMax);
    if (bottom <= top) return [this.at(top)];
    const mds: number[] = [top];
    for (let i = 0; i < this.md.length; i += 1) {
      const m = this.md[i]!;
      if (m > top + 1e-6 && m < bottom - 1e-6) mds.push(m);
    }
    mds.push(bottom);
    const dense: number[] = [mds[0]!];
    for (let i = 1; i < mds.length; i += 1) {
      const prev = mds[i - 1]!;
      const cur = mds[i]!;
      const parts = Math.max(1, Math.ceil((cur - prev) / maxStep));
      for (let k = 1; k <= parts; k += 1) dense.push(prev + ((cur - prev) * k) / parts);
    }
    // Decimate evenly when over budget (the interval ends are always kept).
    let out = dense;
    if (dense.length > maxPoints) {
      const stride = (dense.length - 1) / (maxPoints - 1);
      out = Array.from({ length: maxPoints }, (_, k) => dense[Math.round(k * stride)]!);
    }
    return out.map((m) => this.at(m));
  }

  /** Every stored polyline vertex (for the trajectory tube). */
  vertices(): PathPoint[] {
    return Array.from(this.md, (m) => this.at(m));
  }
}
