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

/**
 * Derived, DISPLAY-ONLY segment from the wellhead (MD 0, origin) to the first surveyed station
 * (backend `tie_in`). MD along it is curve length. Never a survey station: it is only prepended
 * to the drawn path and used to place components whose MD lies above the first station.
 */
export interface TrajectoryTieInInput {
  kind: "vertical" | "arc";
  points: readonly TrajectoryStation[];
}

export interface TrajectoryInput {
  stations: readonly TrajectoryStation[];
  /** Derived display-only tie-in (null/absent: none was derived, nothing is invented). */
  tieIn?: TrajectoryTieInInput | null;
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

/** Maps the API `tie_in` (or null) to the viewer input; the single place that reads its fields. */
export function tieInInput(t: { kind: "vertical" | "arc"; points: readonly { md_m: number; tvd_m: number; east_m: number; north_m: number }[] } | null | undefined): TrajectoryTieInInput | null {
  if (t === null || t === undefined) return null;
  return { kind: t.kind, points: t.points.map((p) => ({ md_m: p.md_m, tvd_m: p.tvd_m, east_m: p.east_m, north_m: p.north_m })) };
}

const TIE_IN_TOL_M = 1e-3;

/** Why a tie-in is not usable with these stations (null = usable). A refused tie-in is ignored, never repaired. */
export function validateTieIn(tieIn: TrajectoryTieInInput, first: TrajectoryStation): string | null {
  const p = tieIn.points;
  if (p.length < 2) return "fewer than two tie-in points";
  for (let i = 0; i < p.length; i += 1) {
    const t = p[i]!;
    if (!finite(t.md_m) || !finite(t.tvd_m) || !finite(t.east_m ?? 0) || !finite(t.north_m ?? 0)) return `tie-in point ${i + 1} has a non-finite value`;
    if (i > 0 && t.md_m <= p[i - 1]!.md_m) return "tie-in measured depths are not strictly increasing";
  }
  const a = p[0]!;
  const z = p[p.length - 1]!;
  if (Math.abs(a.md_m) > TIE_IN_TOL_M || Math.abs(a.tvd_m) > TIE_IN_TOL_M || Math.abs(a.east_m ?? 0) > TIE_IN_TOL_M || Math.abs(a.north_m ?? 0) > TIE_IN_TOL_M) return "tie-in does not start at the wellhead";
  if (
    Math.abs(z.md_m - first.md_m) > TIE_IN_TOL_M ||
    Math.abs(z.tvd_m - first.tvd_m) > TIE_IN_TOL_M ||
    Math.abs((z.east_m ?? 0) - (first.east_m ?? 0)) > TIE_IN_TOL_M ||
    Math.abs((z.north_m ?? 0) - (first.north_m ?? 0)) > TIE_IN_TOL_M
  ) {
    return "tie-in does not end on the first surveyed station";
  }
  return null;
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
  /** First surveyed station MD; MD below it (down to 0) lies on the derived tie-in when `tieInKind` is set. */
  readonly firstStationMd: number;
  /** Kind of the prepended derived tie-in, or null (none supplied, refused or not needed). */
  readonly tieInKind: "vertical" | "arc" | null;
  /** Why a supplied tie-in was ignored (null otherwise). */
  readonly tieInIgnored: string | null;
  /** Number of real survey stations (the tie-in points are not stations). */
  readonly stationCount: number;
  private readonly md: Float64Array;
  private readonly pos: Float64Array;

  private constructor(
    md: Float64Array,
    pos: Float64Array,
    available: boolean,
    sourceLabel: string,
    horizontalKnown: boolean,
    tie: { firstStationMd: number; kind: "vertical" | "arc" | null; ignored: string | null; stationCount: number } = { firstStationMd: md[0]!, kind: null, ignored: null, stationCount: md.length },
  ) {
    this.md = md;
    this.pos = pos;
    this.available = available;
    this.mdMin = md[0]!;
    this.mdMax = md[md.length - 1]!;
    this.sourceLabel = sourceLabel;
    this.horizontalKnown = horizontalKnown;
    this.firstStationMd = tie.firstStationMd;
    this.tieInKind = tie.kind;
    this.tieInIgnored = tie.ignored;
    this.stationCount = tie.stationCount;
  }

  static fromTrajectory(input: TrajectoryInput | null | undefined, fallbackMdMax: number): WellPath {
    const problem = validateStations(input);
    if (problem !== null || input === null || input === undefined) return WellPath.unavailable(fallbackMdMax, problem ?? "no trajectory");
    const n = input.stations.length;
    const first = input.stations[0]!;
    // The tie-in applies only when the first station lies below the wellhead; its last point IS the
    // first station, so it is dropped here (no duplicate MD) and the survey stations are never altered.
    let lead: readonly TrajectoryStation[] = [];
    let kind: "vertical" | "arc" | null = null;
    let ignored: string | null = null;
    if (input.tieIn !== null && input.tieIn !== undefined && first.md_m > TIE_IN_TOL_M) {
      ignored = validateTieIn(input.tieIn, first);
      if (ignored === null) {
        lead = input.tieIn.points.slice(0, -1);
        kind = input.tieIn.kind;
      }
    }
    const total = lead.length + n;
    const md = new Float64Array(total);
    const pos = new Float64Array(total * 3);
    let horizontal = false;
    const put = (s: TrajectoryStation, i: number) => {
      md[i] = s.md_m;
      pos[i * 3] = s.east_m ?? 0;
      pos[i * 3 + 1] = -s.tvd_m;
      pos[i * 3 + 2] = -(s.north_m ?? 0);
    };
    lead.forEach((s, i) => put(s, i));
    input.stations.forEach((s, i) => {
      put(s, lead.length + i);
      if (s.east_m !== undefined || s.north_m !== undefined) horizontal = true;
    });
    return new WellPath(md, pos, true, input.source, horizontal, { firstStationMd: first.md_m, kind, ignored, stationCount: n });
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

  /** True when MD lies on the derived tie-in (above the first surveyed station), never on the survey. */
  onTieIn(md: number): boolean {
    return this.tieInKind !== null && md < this.firstStationMd - 1e-6;
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
