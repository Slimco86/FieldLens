import { getJson } from "../../api/client";
import type { components } from "../../api/generated";

type S = components["schemas"];
export type ChartSpecWire = S["ChartSpec"];
export type ChartSeriesWire = S["ChartSeries"];
export type ChartAxis = S["ChartAxis"];
export type ChartPoint = S["ChartPoint"];
export type ChartSeriesScope = S["ChartSeriesScope"];
export type ChartReferenceLine = S["ChartReferenceLine"];
export type WellboreChartSet = S["WellboreChartSet"];
export type FieldChartSet = S["FieldChartSet"];
export type EvidenceLink = S["EvidenceLink"];
export type ExcludedSeries = S["ExcludedSeries"];

/** Series with the contract's defaulted lists made present (the OpenAPI types mark them optional). */
export type ChartSeries = Omit<ChartSeriesWire, "points" | "evidence"> & { points: ChartPoint[]; evidence: EvidenceLink[] };
export type ChartSpec = Omit<ChartSpecWire, "axes" | "series" | "reference_lines" | "excluded_series" | "evidence" | "notes"> & {
  axes: ChartAxis[];
  series: ChartSeries[];
  reference_lines: ChartReferenceLine[];
  excluded_series: ExcludedSeries[];
  evidence: EvidenceLink[];
  notes: string[];
};

/** Fills the defaulted lists once at the boundary so renderers never branch on `undefined`. */
export function normalizeChart(spec: ChartSpecWire | ChartSpec): ChartSpec {
  return {
    ...spec,
    axes: spec.axes ?? [],
    series: (spec.series ?? []).map((s) => ({ ...s, points: s.points ?? [], evidence: s.evidence ?? [] })),
    reference_lines: spec.reference_lines ?? [],
    excluded_series: spec.excluded_series ?? [],
    evidence: spec.evidence ?? [],
    notes: spec.notes ?? [],
  };
}

/** Optional view parameters; ISO dates on time charts. Omitted = the server's default (latest, full record). */
export interface ChartQuery {
  asOf?: string | null;
  from?: string | null;
  to?: string | null;
}

function query(q: ChartQuery): string {
  const p = new URLSearchParams();
  if (q.asOf) p.set("as_of", q.asOf);
  if (q.from) p.set("from", q.from);
  if (q.to) p.set("to", q.to);
  const s = p.toString();
  return s === "" ? "" : `?${s}`;
}

/** Charts of one wellbore only (XC-1/2). Aborting `signal` rejects with an AbortError. */
export const getWellboreCharts = (projectId: string, wellboreId: string, q: ChartQuery, signal: AbortSignal) =>
  getJson<WellboreChartSet>(`/api/v1/projects/${projectId}/wellbores/${wellboreId}/charts${query(q)}`, signal);

/** Global field charts, aggregated server-side on full-resolution data (XC-3). */
export const getFieldCharts = (projectId: string, q: ChartQuery, signal: AbortSignal) =>
  getJson<FieldChartSet>(`/api/v1/projects/${projectId}/charts/field${query(q)}`, signal);
