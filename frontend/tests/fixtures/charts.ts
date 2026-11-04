import type { components } from "../../src/api/generated";

type S = components["schemas"];
export type Spec = S["ChartSpec"];
export type Ser = S["ChartSeries"];

export const WB = "11111111-1111-4111-8111-111111111111";
export const OTHER_WB = "22222222-2222-4222-8222-222222222222";
export const PROJECT = "99999999-9999-4999-8999-999999999999";
export const DOC = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

export const boreScope = (id = WB): S["ChartSeriesScope"] => ({ scope: "wellbore", scope_label: "wellbore-level", wellbore_id: id, wellbore_label: "A-1", well_name: "Well A", ambiguity: null });
export const wellScope = (): S["ChartSeriesScope"] => ({ scope: "well", scope_label: "well-level", wellbore_id: null, wellbore_label: null, well_name: "Well A", ambiguity: null });
export const fieldScope = (): S["ChartSeriesScope"] => ({ scope: "field", scope_label: "field-level", wellbore_id: null, wellbore_label: null, well_name: null, ambiguity: null });

export const pdfEvidence = (page = 3): S["EvidenceLink"] => ({
  document_id: DOC,
  record_id: null,
  source_revision_id: null,
  locator: { kind: "pdf", document_id: DOC, source_revision_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", page, rect: null, cell_id: null, table_id: null },
});

export function series(over: Partial<Ser> & { points: S["ChartPoint"][] }): Ser {
  const valid = over.points.filter((p) => p.y !== null);
  const ys = valid.map((p) => p.y as number);
  const gaps = over.points.length - valid.length;
  return {
    series_key: "oil",
    name: "Oil rate",
    kind: null,
    axis_id: "y0",
    x_axis_id: "x",
    unit: "Sm3/d",
    unit_status: "stated",
    scope: boreScope(),
    gap_count: gaps,
    downsample: { applied: false, algorithm: null, max_points: 5000, source_points: over.points.length, returned_points: over.points.length, gap_markers_preserved: true, gaps_omitted: 0, extrema_preserved: true },
    aggregates: {
      basis: "full_resolution",
      count: over.points.length,
      valid_count: valid.length,
      null_count: gaps,
      minimum: ys.length ? Math.min(...ys) : null,
      maximum: ys.length ? Math.max(...ys) : null,
      mean: ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : null,
      total: null,
      first_valid_x: valid[0]?.x ?? null,
      last_valid_x: valid[valid.length - 1]?.x ?? null,
      last_value: ys.length ? ys[ys.length - 1]! : null,
      unit: over.unit === undefined ? "Sm3/d" : over.unit,
    },
    source_series_id: null,
    series_revision: "r1",
    stack_group: null,
    evidence: [],
    ...over,
  };
}

export const timeAxis = (): S["ChartAxis"] => ({ axis_id: "x", name: "Reporting date", kind: "time", position: "x", unit: null, unit_status: "stated", datum: null, inverted: false });
export const yAxis = (id: string, name: string, unit: string | null, position: S["ChartAxis"]["position"] = "y_left"): S["ChartAxis"] => ({
  axis_id: id,
  name,
  kind: "value",
  position,
  unit,
  unit_status: unit === null ? "missing" : "stated",
  datum: null,
  inverted: false,
});

export function chart(over: Partial<Spec> = {}): Spec {
  return {
    chart_id: "production_rates",
    key: "production_rates",
    title: "Production rates",
    kind: "line",
    scope: boreScope(),
    axes: [timeAxis(), yAxis("y0", "Rate [Sm3/d]", "Sm3/d")],
    series: [
      series({
        points: [
          { x: "2024-01-01", y: 10 },
          { x: "2024-02-01", y: null },
          { x: "2024-03-01", y: 12 },
        ],
        evidence: [pdfEvidence()],
      }),
    ],
    reference_lines: [],
    excluded_series: [],
    empty: null,
    window: null,
    as_of: "2024-03-31",
    cache_key: "k1",
    evidence: [],
    notes: [],
    ...over,
  };
}

export const emptyChart = (key: S["ChartKey"] = "pressure_tests", reason: S["ChartEmptyReason"] = "no_records"): Spec =>
  chart({ chart_id: key, key, title: "Pressure tests", series: [], axes: [], empty: { reason, message: "No pressure-test records exist for this wellbore." } });

export function wellboreSet(charts: Spec[], over: Partial<S["WellboreChartSet"]> = {}): S["WellboreChartSet"] {
  return { project_id: PROJECT, wellbore_id: WB, wellbore_label: "A-1", well_name: "Well A", as_of: null, window: null, charts, perforation_history: null, ambiguities: [], generated_from_revision: "rev1", cache_key: "ck", generated_at: null, ...over };
}

export function fieldSet(charts: Spec[], over: Partial<S["FieldChartSet"]> = {}): S["FieldChartSet"] {
  return { project_id: PROJECT, as_of: null, window: null, wellbore_ids: [WB], charts, excluded_series: [], reconciliation_note: null, generated_from_revision: "rev1", cache_key: "ck", generated_at: null, ...over };
}
