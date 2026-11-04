import type { EChartsCoreOption } from "echarts/core";
import type { ChartAxis, ChartSeries, ChartSpec } from "./api";

/**
 * Pure ChartSpec -> ECharts option builder (no DOM, no echarts runtime). Rules enforced here:
 *  - one value axis per spec axis; stacking is keyed per axis, so different units never share an axis;
 *  - a null `y` stays a null datum and `connectNulls` is off: lines break at gaps, nothing is interpolated;
 *  - points are drawn exactly as supplied (the server already limited them to <= 5,000 display points);
 *    no client sampling, no zoom data filtering (`filterMode: "none"`), no aggregate is computed here;
 *  - depth-first charts (x axis is a depth axis, or a log track) draw depth vertically.
 */

export type Orientation = "time" | "value" | "depth";

export interface SeriesMeta {
  name: string;
  unit: string | null;
  unitText: string;
  scopeLabel: string;
  /** Hidden carrier of reference lines; absent from the legend and the data table. */
  reference: boolean;
}

export interface ChartBuild {
  option: EChartsCoreOption;
  orientation: Orientation;
  /** True when x is a time axis (ISO strings); numeric x on a "time" axis falls back to a value axis. */
  timeAxis: boolean;
  /** Axis the inside-zoom acts on. */
  zoomAxis: "x" | "y";
  /** Numeric extent of the zoom axis over the supplied points (ms for time), or null without points. */
  extent: [number, number] | null;
  /** Aligned with `option.series`. */
  seriesMeta: SeriesMeta[];
  /** Index of the plotted value inside a datum (0 for depth charts, 1 otherwise). */
  valueIndex: 0 | 1;
}

const DEPTH_KINDS = new Set(["depth_md", "depth_tvd", "depth_tvdss"]);
const MAX_SYMBOL_POINTS = 500;
const AXIS_STEP = 64;

export function unitText(unit: string | null, status: string): string {
  if (status === "mixed") return "mixed units";
  if (status === "missing") return "unit not stated";
  return unit ?? "";
}

/** Axis title that always carries its unit state, even if the server label does not. */
export function axisTitle(axis: ChartAxis): string {
  let text = axis.name;
  if (axis.unit_status === "stated" && axis.unit && !text.includes(axis.unit)) text += ` [${axis.unit}]`;
  else if (axis.unit_status === "mixed" && !/mixed/i.test(text)) text += " (mixed units)";
  else if (axis.unit_status === "missing" && !/not stated/i.test(text)) text += " (unit not stated)";
  return text;
}

export function seriesLabel(s: ChartSeries, counts: Map<string, number>): string {
  return (counts.get(s.name) ?? 0) > 1 ? `${s.name} (${s.scope.scope_label})` : s.name;
}

export function toNumber(x: number | string): number {
  return typeof x === "number" ? x : Date.parse(x);
}

const isDepthAxis = (a: ChartAxis | undefined): boolean => a !== undefined && DEPTH_KINDS.has(a.kind);

export function orientationOf(spec: ChartSpec): Orientation {
  const x = spec.axes.find((a) => a.position === "x");
  if (spec.kind === "log_track" || isDepthAxis(x)) return "depth";
  return x?.kind === "time" ? "time" : "value";
}

function seriesBase(s: ChartSeries, kind: string, stackKey: string | undefined): Record<string, unknown> {
  const valid = s.points.reduce((n, p) => (p.y === null ? n : n + 1), 0);
  const line = {
    connectNulls: false,
    showSymbol: valid <= MAX_SYMBOL_POINTS,
    symbolSize: 5,
    lineStyle: s.scope.scope === "well" ? { type: "dashed" } : undefined,
    clip: true,
  };
  switch (kind) {
    case "step":
      return { type: "line", step: "end", ...line };
    case "bar":
    case "strip":
      return { type: "bar", stack: undefined };
    case "stacked_bar":
      return { type: "bar", stack: stackKey };
    case "stacked_area":
      return { type: "line", stack: stackKey, areaStyle: {}, ...line };
    case "scatter":
    case "timeline":
      return { type: "scatter", symbolSize: 8 };
    default: // line, log_track, correlation
      return { type: "line", ...line, showSymbol: kind === "correlation" ? true : line.showSymbol };
  }
}

/** Returns null for a chart without drawable series (empty state; the caller explains why). */
export function buildChartOption(spec: ChartSpec): ChartBuild | null {
  if (spec.series.length === 0) return null;
  const orientation = orientationOf(spec);
  const xAxisDef = spec.axes.find((a) => a.position === "x");
  const valueAxes = spec.axes.filter((a) => a.position !== "x");
  const axisIndex = new Map(valueAxes.map((a, i) => [a.axis_id, i]));
  const names = new Map<string, number>();
  for (const s of spec.series) names.set(s.name, (names.get(s.name) ?? 0) + 1);

  const allX = spec.series.flatMap((s) => s.points.map((p) => p.x));
  const timeAxis = orientation === "time" && allX.every((x) => typeof x === "string");
  const nums = allX.map(toNumber).filter(Number.isFinite);
  const extent: [number, number] | null =
    nums.length === 0 ? null : [nums.reduce((a, b) => Math.min(a, b), Infinity), nums.reduce((a, b) => Math.max(a, b), -Infinity)];
  const depth = orientation === "depth";

  const seriesMeta: SeriesMeta[] = [];
  const series: Record<string, unknown>[] = spec.series.map((s) => {
    const kind = s.kind ?? spec.kind;
    const ai = axisIndex.get(s.axis_id) ?? 0;
    const label = seriesLabel(s, names);
    seriesMeta.push({
      name: label,
      unit: s.unit,
      unitText: unitText(s.unit, s.unit_status),
      scopeLabel: s.scope.scope_label,
      reference: false,
    });
    return {
      name: label,
      ...seriesBase(s, kind, `${s.axis_id}:${s.stack_group ?? "stack"}`),
      // Null y stays null: ECharts breaks the line / leaves no bar there.
      data: s.points.map((p) => (depth ? [p.y, toNumber(p.x)] : [timeAxis ? p.x : toNumber(p.x), p.y])),
      ...(depth ? { xAxisIndex: ai, yAxisIndex: 0 } : { xAxisIndex: 0, yAxisIndex: ai }),
    };
  });

  // Reference lines ride on hidden carrier series bound to the referenced axis.
  const byAxis = new Map<string, Record<string, unknown>[]>();
  for (const r of spec.reference_lines) {
    const list = byAxis.get(r.axis_id) ?? [];
    const onX = r.axis_id === xAxisDef?.axis_id;
    const horizontal = depth ? onX : !onX; // draws a horizontal line (yAxis value)
    list.push({ name: r.unit ? `${r.label} (${r.value} ${r.unit})` : `${r.label} (${r.value})`, ...(horizontal ? { yAxis: r.value } : { xAxis: r.value }) });
    byAxis.set(r.axis_id, list);
  }
  for (const [axisId, data] of byAxis) {
    const ai = axisIndex.get(axisId);
    const onX = axisId === xAxisDef?.axis_id;
    if (!onX && ai === undefined) continue;
    const axisRef = depth ? (onX ? { xAxisIndex: 0, yAxisIndex: 0 } : { xAxisIndex: ai, yAxisIndex: 0 }) : onX ? { xAxisIndex: 0, yAxisIndex: 0 } : { xAxisIndex: 0, yAxisIndex: ai };
    seriesMeta.push({ name: `reference:${axisId}`, unit: null, unitText: "", scopeLabel: "", reference: true });
    series.push({
      name: `reference:${axisId}`,
      type: "line",
      data: [],
      silent: false,
      ...axisRef,
      markLine: { symbol: "none", animation: false, lineStyle: { type: "dashed" }, label: { formatter: "{b}", position: "insideEndTop" }, data },
    });
  }

  const sideOf = (a: ChartAxis) => (a.position === "y_left" ? "left" : "right");
  const perSide = { left: 0, right: 0 };
  const yAxes: Record<string, unknown>[] = [];
  const xAxes: Record<string, unknown>[] = [];
  let top = 64;
  let left = 12;
  let right = 12;

  if (depth) {
    const d = xAxisDef;
    yAxes.push({
      type: "value",
      name: d ? axisTitle(d) : "Depth",
      nameLocation: "end",
      inverse: d?.inverted ?? true,
      scale: true,
      position: "left",
    });
    left = 72;
    valueAxes.forEach((a, i) => {
      xAxes.push({ type: "value", name: axisTitle(a), nameLocation: "start", position: "top", offset: i * 34, scale: true, inverse: a.inverted, axisLine: { show: true } });
    });
    top = 64 + 34 * Math.max(0, valueAxes.length - 1);
    right = 24;
  } else {
    xAxes.push({
      type: timeAxis ? "time" : "value",
      name: xAxisDef ? axisTitle(xAxisDef) : "",
      nameLocation: "middle",
      nameGap: 30,
      scale: true,
      inverse: xAxisDef?.inverted ?? false,
    });
    const hasBars = spec.series.some((s) => ["bar", "strip", "stacked_bar", "stacked_area"].includes(s.kind ?? spec.kind));
    for (const a of valueAxes) {
      const side = sideOf(a);
      yAxes.push({
        type: "value",
        name: axisTitle(a),
        nameLocation: "end",
        nameTextStyle: { align: side },
        position: side,
        offset: perSide[side] * AXIS_STEP,
        scale: !hasBars,
        inverse: a.inverted,
        axisLine: { show: true },
        splitLine: { show: perSide.left === 0 && side === "left" },
      });
      perSide[side] += 1;
    }
    if (yAxes.length === 0) yAxes.push({ type: "value" });
    left = 12 + AXIS_STEP * Math.max(1, perSide.left);
    right = 12 + AXIS_STEP * perSide.right;
  }

  const legend = seriesMeta.flatMap((m) => (m.reference ? [] : [m.name]));
  const option: EChartsCoreOption = {
    animation: false, // honours reduced motion and keeps 5,000-point charts cheap
    grid: { left, right, top, bottom: 56, containLabel: false },
    legend: { type: "scroll", top: 0, data: legend },
    tooltip: { trigger: depth || spec.series.some((s) => (s.kind ?? spec.kind) === "timeline") ? "item" : "axis", confine: true },
    xAxis: xAxes,
    yAxis: yAxes,
    dataZoom: [{ type: "inside", [depth ? "yAxisIndex" : "xAxisIndex"]: 0, filterMode: "none" }],
    series,
  };

  const build: ChartBuild = { option, orientation, timeAxis, zoomAxis: depth ? "y" : "x", extent, seriesMeta, valueIndex: depth ? 0 : 1 };
  (option.tooltip as Record<string, unknown>).formatter = (p: TooltipParam | TooltipParam[]) => formatTooltip(p, build);
  return build;
}

const esc = (s: string): string => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export function formatValue(v: number): string {
  return Number(v.toPrecision(7)).toString();
}

interface TooltipParam {
  seriesIndex?: number;
  seriesName?: string;
  marker?: string;
  value?: unknown;
  axisValueLabel?: string;
  name?: string;
}

/** Tooltip body: every line is `series: value unit` (or `no value (gap)`); text is escaped. */
export function formatTooltip(params: TooltipParam | TooltipParam[], build: Pick<ChartBuild, "seriesMeta" | "valueIndex">): string {
  const list = Array.isArray(params) ? params : [params];
  const rows: string[] = [];
  let head = "";
  for (const p of list) {
    const meta = build.seriesMeta[p.seriesIndex ?? -1];
    if (meta === undefined || meta.reference) {
      if (p.name) rows.push(esc(p.name));
      continue;
    }
    const datum = Array.isArray(p.value) ? (p.value as unknown[]) : [];
    const v = datum[build.valueIndex];
    const xv = datum[build.valueIndex === 1 ? 0 : 1];
    if (head === "") head = p.axisValueLabel ?? (xv === undefined || xv === null ? "" : typeof xv === "number" ? formatValue(xv) : String(xv));
    const text = typeof v === "number" ? `${formatValue(v)}${meta.unitText ? ` ${meta.unitText}` : ""}` : "no value (gap)";
    rows.push(`${p.marker ?? ""}${esc(meta.name)}: <b>${esc(text)}</b> <i>${esc(meta.scopeLabel)}</i>`);
  }
  return [head === "" ? "" : `<div>${esc(head)}</div>`, ...rows].join("<br/>");
}
