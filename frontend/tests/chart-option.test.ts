import { describe, expect, it } from "vitest";
import { buildChartOption, formatTooltip, orientationOf } from "../src/features/charts/chartOption";
import { normalizeChart } from "../src/features/charts/api";
import { pointRows, seriesRows, summarizeChart } from "../src/features/charts/chartTable";
import { chart, emptyChart, series, timeAxis, yAxis, wellScope } from "./fixtures/charts";

const build = (c = chart()) => {
  const b = buildChartOption(normalizeChart(c));
  if (b === null) throw new Error("expected a build");
  return b;
};
type Opt = { series: Record<string, unknown>[]; yAxis: Record<string, unknown>[]; xAxis: Record<string, unknown>[]; dataZoom: Record<string, unknown>[]; grid: Record<string, number> };
const opt = (c = chart()) => build(c).option as unknown as Opt;

describe("buildChartOption", () => {
  it("returns null for an empty chart (the caller shows the reason)", () => {
    expect(buildChartOption(normalizeChart(emptyChart()))).toBeNull();
  });

  it("keeps gaps as null data and never connects them", () => {
    const o = opt();
    const s = o.series[0]!;
    expect(s.data).toEqual([["2024-01-01", 10], ["2024-02-01", null], ["2024-03-01", 12]]);
    expect(s.connectNulls).toBe(false);
    expect(JSON.stringify(o)).not.toContain('"sampling"');
  });

  it("draws every supplied point and does not filter data on zoom", () => {
    const pts = Array.from({ length: 5000 }, (_, i) => ({ x: Date.UTC(2020, 0, 1) + i * 86_400_000, y: i % 7 === 0 ? null : i }));
    const c = chart({ axes: [{ ...timeAxis(), kind: "value" }, yAxis("y0", "Rate", "Sm3/d")], series: [series({ points: pts })] });
    const o = opt(c);
    expect((o.series[0]!.data as unknown[]).length).toBe(5000);
    expect(o.dataZoom[0]).toMatchObject({ type: "inside", filterMode: "none" });
  });

  it("gives each unit its own labeled axis and never shares one", () => {
    const c = chart({
      axes: [timeAxis(), yAxis("y0", "Rate [Sm3/d]", "Sm3/d"), yAxis("y1", "Pressure", "bar", "y_right"), yAxis("y2", "Temperature", "degC", "y_extra")],
      series: [
        series({ series_key: "oil", points: [{ x: "2024-01-01", y: 1 }] }),
        series({ series_key: "p", name: "BHP", axis_id: "y1", unit: "bar", points: [{ x: "2024-01-01", y: 200 }] }),
        series({ series_key: "t", name: "BHT", axis_id: "y2", unit: "degC", points: [{ x: "2024-01-01", y: 90 }] }),
      ],
    });
    const o = opt(c);
    expect(o.yAxis).toHaveLength(3);
    expect(o.series.map((s) => s.yAxisIndex)).toEqual([0, 1, 2]);
    expect(o.yAxis.map((a) => a.name)).toEqual(["Rate [Sm3/d]", "Pressure [bar]", "Temperature [degC]"]);
    expect(o.yAxis[1]!.offset).toBe(0);
    expect(o.yAxis[2]!.offset).toBe(64); // second right-hand axis is offset, not overlapped
  });

  it("states a missing/mixed unit on the axis title", () => {
    const c = chart({ axes: [timeAxis(), yAxis("y0", "Flow", null)], series: [series({ unit: null, unit_status: "missing", points: [{ x: "2024-01-01", y: 1 }] })] });
    expect(opt(c).yAxis[0]!.name).toBe("Flow (unit not stated)");
  });

  it("stacks only within an axis and group", () => {
    const c = chart({
      kind: "stacked_bar",
      axes: [timeAxis(), yAxis("y0", "Rate", "Sm3/d"), yAxis("y1", "Rate", "Sm3/h", "y_right")],
      series: [
        series({ series_key: "a", name: "A", stack_group: "g", points: [{ x: "2024-01-01", y: 1 }] }),
        series({ series_key: "b", name: "B", stack_group: "g", points: [{ x: "2024-01-01", y: 1 }] }),
        series({ series_key: "c", name: "C", stack_group: "g", axis_id: "y1", unit: "Sm3/h", points: [{ x: "2024-01-01", y: 1 }] }),
      ],
    });
    const stacks = opt(c).series.map((s) => s.stack);
    expect(stacks[0]).toBe(stacks[1]);
    expect(stacks[2]).not.toBe(stacks[0]);
  });

  it("draws perforation history as a step series that holds until the next point", () => {
    const c = chart({ key: "perforated_length", kind: "step", series: [series({ name: "Perforated length", unit: "m", points: [{ x: "2024-01-01", y: 5 }, { x: "2024-06-01", y: 9 }] })], axes: [timeAxis(), yAxis("y0", "Perforated length", "m")] });
    expect(opt(c).series[0]).toMatchObject({ type: "line", step: "end" });
  });

  it("marks well-level series with a dashed line and disambiguates duplicate names by scope", () => {
    const c = chart({
      series: [
        series({ series_key: "a", points: [{ x: "2024-01-01", y: 1 }] }),
        series({ series_key: "b", scope: wellScope(), points: [{ x: "2024-01-01", y: 2 }] }),
      ],
    });
    const o = opt(c);
    expect(o.series[1]!.lineStyle).toEqual({ type: "dashed" });
    expect(o.series.map((s) => s.name)).toEqual(["Oil rate (wellbore-level)", "Oil rate (well-level)"]);
  });

  it("draws log tracks with depth vertical and formation tops as reference lines", () => {
    const c = chart({
      key: "log_tracks",
      kind: "log_track",
      axes: [{ axis_id: "x", name: "MD", kind: "depth_md", position: "x", unit: "m", unit_status: "stated", datum: "RKB", inverted: true }, yAxis("g", "Gamma ray", "gAPI")],
      series: [series({ axis_id: "g", unit: "gAPI", points: [{ x: 1000, y: 50 }, { x: 1001, y: null }, { x: 1002, y: 80 }] })],
      reference_lines: [{ label: "Top Brent", axis_id: "x", value: 1001.5, unit: "m", surface_key: null, pick_id: null, evidence: [] }],
    });
    const b = build(c);
    const o = b.option as unknown as Opt;
    expect(b.orientation).toBe("depth");
    expect(o.yAxis[0]).toMatchObject({ inverse: true });
    expect(o.series[0]!.data).toEqual([[50, 1000], [null, 1001], [80, 1002]]);
    const ref = o.series[1]!;
    expect((ref.markLine as { data: unknown[] }).data).toEqual([{ name: "Top Brent (1001.5 m)", yAxis: 1001.5 }]);
    expect(b.seriesMeta[1]!.reference).toBe(true);
    expect(b.zoomAxis).toBe("y");
  });

  it("falls back to a value x axis when a time axis carries numbers (never guesses a date)", () => {
    const c = chart({ series: [series({ points: [{ x: 19000, y: 1 }] })] });
    expect(build(c).timeAxis).toBe(false);
    expect(orientationOf(normalizeChart(c))).toBe("time");
    expect(opt(c).xAxis[0]!.type).toBe("value");
  });

  it("reports the numeric extent for zoom linking", () => {
    expect(build().extent).toEqual([Date.parse("2024-01-01"), Date.parse("2024-03-01")]);
  });
});

describe("formatTooltip", () => {
  it("shows value with unit, states gaps and escapes text", () => {
    const b = build(chart({ series: [series({ name: "<b>Oil</b>", points: [{ x: "2024-01-01", y: 10.123456789 }, { x: "2024-02-01", y: null }] })] }));
    const html = formatTooltip([{ seriesIndex: 0, value: ["2024-01-01", 10.123456789], axisValueLabel: "2024-01-01" }], b);
    expect(html).toContain("10.12346 Sm3/d");
    expect(html).toContain("&#60;b&#62;Oil");
    expect(html).not.toContain("<b>Oil");
    expect(formatTooltip({ seriesIndex: 0, value: ["2024-02-01", null] }, b)).toContain("no value (gap)");
  });
});

describe("table alternatives", () => {
  it("summarises from the exact aggregates, incl. scope, window and as-of", () => {
    const c = normalizeChart(chart({ window: { from: "2024-01-01", to: "2024-03-31" } }));
    const text = summarizeChart(c);
    expect(text).toContain("As of 2024-03-31");
    expect(text).toContain("Window 2024-01-01 to 2024-03-31");
    expect(text).toContain("1 gaps");
    expect(seriesRows(c)[0]).toMatchObject({ valid: 2, gaps: 1, min: "10", max: "12", last: "12" });
  });
  it("lists gaps as gaps, not zero", () => {
    expect(pointRows(normalizeChart(chart()).series[0]!, 0, 10).map((p) => p.y)).toEqual(["10", "gap (no value)", "12"]);
  });
  it("states the empty reason in the summary", () => {
    expect(summarizeChart(normalizeChart(emptyChart()))).toContain("No chart drawn: No pressure-test records");
  });
});
