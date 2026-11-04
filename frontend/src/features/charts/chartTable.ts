import type { ChartSeries, ChartSpec } from "./api";
import { formatValue, seriesLabel, unitText } from "./chartOption";

/** Text/table alternatives for a chart (XC-6). Everything shown is a server aggregate or a supplied point. */

export function describeWindow(spec: Pick<ChartSpec, "window" | "as_of">): { asOf: string; window: string } {
  const w = spec.window;
  return {
    asOf: spec.as_of ? `As of ${spec.as_of}` : "As of: latest (no date selected)",
    window: w && (w.from || w.to) ? `Window ${w.from ?? "start"} to ${w.to ?? "end"}` : "Window: full record",
  };
}

export interface SeriesRow {
  key: string;
  name: string;
  scope: string;
  axis: string;
  unit: string;
  valid: number;
  gaps: number;
  min: string;
  max: string;
  last: string;
  range: string;
  displayed: string;
}

const num = (v: number | null | undefined): string => (v === null || v === undefined ? "n/a" : formatValue(v));
const nameCounts = (series: ChartSeries[]): Map<string, number> => {
  const m = new Map<string, number>();
  for (const s of series) m.set(s.name, (m.get(s.name) ?? 0) + 1);
  return m;
};

/** One row per series from the exact full-resolution aggregates (never recomputed from display points). */
export function seriesRows(spec: ChartSpec): SeriesRow[] {
  const counts = nameCounts(spec.series);
  const axisName = new Map(spec.axes.map((a) => [a.axis_id, a.name]));
  return spec.series.map((s) => {
    const a = s.aggregates;
    const d = s.downsample;
    return {
      key: s.series_key,
      name: seriesLabel(s, counts),
      scope: s.scope.scope_label,
      axis: axisName.get(s.axis_id) ?? s.axis_id,
      unit: unitText(s.unit, s.unit_status) || "dimensionless",
      valid: a.valid_count,
      gaps: s.gap_count,
      min: num(a.minimum),
      max: num(a.maximum),
      last: num(a.last_value),
      range: a.first_valid_x === null || a.last_valid_x === null ? "n/a" : `${a.first_valid_x} to ${a.last_valid_x}`,
      displayed: d.applied ? `${d.returned_points} of ${d.source_points} points (display-reduced)` : `${d.returned_points} points`,
    };
  });
}

/** Plain-text summary used as the chart's accessible name/description. */
export function summarizeChart(spec: ChartSpec): string {
  const { asOf, window } = describeWindow(spec);
  const head = `${spec.title}. ${spec.scope.scope_label}. ${asOf}. ${window}.`;
  if (spec.empty) return `${head} No chart drawn: ${spec.empty.message}`;
  const parts = seriesRows(spec).map((r) => `${r.name} (${r.unit}): ${r.valid} valid values, ${r.gaps} gaps, minimum ${r.min}, maximum ${r.max}, last ${r.last}`);
  return `${head} ${spec.series.length} series. ${parts.join("; ")}.`;
}

export interface PointRow {
  x: string;
  y: string;
}

/** A slice of one series' supplied points for the data table; null y is stated as a gap. */
export function pointRows(s: ChartSeries, offset: number, limit: number): PointRow[] {
  return s.points.slice(offset, offset + limit).map((p) => ({
    x: typeof p.x === "number" ? formatValue(p.x) : p.x,
    y: p.y === null ? "gap (no value)" : formatValue(p.y),
  }));
}
