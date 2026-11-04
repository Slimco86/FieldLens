import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Callout, EmptyState } from "../../design";
import { useExploreCommandBus } from "../scene/ExploreCommandsContext";
import type { ExploreCommandBus, ExploreCommandOutcome } from "../scene/exploreCommands";
import { normalizeChart, type ChartSeriesScope, type ChartSpec, type ChartSpecWire } from "./api";
import { createChartCursorStore, useChartCursorStore, windowBoundToIsoDate, type CursorWindow } from "./chartCursor";
import { buildChartOption } from "./chartOption";
import { describeWindow, pointRows, seriesRows, summarizeChart } from "./chartTable";
import { evidenceLabel, openEvidence, OPEN_RESULT_MESSAGE, type OpenSourceResult } from "./evidence";
import { loadEcharts } from "./loadEcharts";
import type { ECharts } from "./echartsRuntime";
import styles from "./Charts.module.css";

const LEVEL: Record<ChartSeriesScope["scope"], string> = {
  wellbore: "Wellbore-level",
  well: "Well-level",
  field: "Field-level",
  project: "Project-level",
  unreconciled: "Unreconciled",
};

const EMPTY_TITLE: Record<string, string> = {
  no_records: "No records in project",
  no_data_in_window: "No data in the selected window",
  scope_ambiguous: "Scope is ambiguous",
  unit_mismatch: "Units do not match",
  not_applicable: "Not applicable here",
  source_unavailable: "Source unavailable",
  as_of_before_data: "As-of date is before the data starts",
};

const PAGE = 100;
const ZOOM_STEP = 0.5;

function ScopeBadge({ scope }: { scope: ChartSeriesScope }) {
  const label = scope.scope_label.toLowerCase() === LEVEL[scope.scope].toLowerCase() ? "" : ` (${scope.scope_label})`;
  const bore = scope.scope === "wellbore" && scope.wellbore_label ? ` ${scope.wellbore_label}` : "";
  return (
    <span className={styles.badge} data-scope={scope.scope} title={scope.well_name ?? undefined}>
      {LEVEL[scope.scope]}
      {bore}
      {label}
    </span>
  );
}

function distinctScopes(spec: ChartSpec): ChartSeriesScope[] {
  const seen = new Map<string, ChartSeriesScope>();
  for (const s of [spec.scope, ...spec.series.map((x) => x.scope)]) seen.set(`${s.scope}:${s.wellbore_id ?? ""}:${s.scope_label}`, s);
  return [...seen.values()];
}

export interface ChartBlockProps {
  spec: ChartSpecWire;
  /** Plot height in px (default 280). */
  height?: number;
  /** Heading level of the title (default 3). */
  headingLevel?: 2 | 3 | 4;
  /** Overrides the Explore command bus (tests, the assistant). Null = no viewer. */
  commandBus?: Pick<ExploreCommandBus, "dispatch"> | null;
  /** Wellbore a well-/field-level chart's formation tops are shown on in 3D (a wellbore-scoped chart uses its own). */
  wellboreId?: string | null;
}

const SHOW_RESULT: Record<ExploreCommandOutcome, string> = {
  handled: "Shown in 3D.",
  queued: "Waiting for the 3D view to be ready.",
  unhandled: "Could not show this formation in 3D: it is not drawn for this wellbore.",
  "no-subscriber": "The 3D view is not available here.",
};

/**
 * Renders one ChartSpec: ECharts plot (lazy chunk), scope badges, as-of/window, unit-separated axes, gaps kept,
 * evidence links, and a text/table alternative. Reusable by the assistant: it needs only a spec, and works without
 * any provider. The chart instance and its listeners are disposed on unmount; resizing follows a ResizeObserver
 * (so a chart revealed from a hidden Split/Charts pane redraws at its real size).
 */
export function ChartBlock({ spec: wire, height = 280, headingLevel = 3, commandBus, wellboreId = null }: ChartBlockProps) {
  const spec = useMemo(() => normalizeChart(wire), [wire]);
  const uid = useId();
  const build = useMemo(() => buildChartOption(spec), [spec]);
  const buildRef = useRef(build);
  buildRef.current = build;
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ECharts | null>(null);
  const range = useRef({ start: 0, end: 100 });
  const [engine, setEngine] = useState<"loading" | "ready" | "failed">("loading");
  const ownStore = useMemo(createChartCursorStore, []);
  const store = useChartCursorStore() ?? ownStore;
  const windowSel = useSyncExternalStore(store.subscribe, store.get, store.get);
  const busFromContext = useExploreCommandBus();
  const bus = commandBus === undefined ? busFromContext : commandBus;
  const [openMsg, setOpenMsg] = useState<OpenSourceResult | null>(null);
  const [tableOpen, setTableOpen] = useState(false);
  const [tableKey, setTableKey] = useState(spec.series[0]?.series_key ?? "");
  const [shown, setShown] = useState(PAGE);
  const hasBuild = build !== null;

  const cursorAxis = build?.timeAxis ? "time" : build?.orientation === "depth" ? "depth" : null;

  // Mount/unmount of the chart instance.
  useEffect(() => {
    if (!hasBuild) return;
    const host = hostRef.current;
    if (host === null) return;
    let cancelled = false;
    let chart: ECharts | null = null;
    let ro: ResizeObserver | null = null;
    let stopFollowing: (() => void) | null = null;
    let applying = false;
    loadEcharts()
      .then((rt) => {
        if (cancelled) return;
        chart = rt.init(host, undefined, { renderer: "canvas" });
        chartRef.current = chart;
        chart.setOption(buildRef.current?.option ?? {}, true);
        chart.on("datazoom", (e: unknown) => {
          const ev = e as { start?: number; end?: number; batch?: { start?: number; end?: number }[] };
          const z = ev.batch?.[0] ?? ev;
          const b = buildRef.current;
          if (applying || b === null || b.extent === null || z.start === undefined || z.end === undefined) return;
          range.current = { start: z.start, end: z.end };
          const axis = b.timeAxis ? "time" : b.orientation === "depth" ? "depth" : null;
          if (axis === null) return;
          const [lo, hi] = b.extent;
          const whole = z.start <= 0 && z.end >= 100;
          store.set(whole ? null : { axis, from: lo + ((hi - lo) * z.start) / 100, to: lo + ((hi - lo) * z.end) / 100 }, uid);
        });
        ro = new ResizeObserver(() => {
          if (host.clientWidth > 0 && host.clientHeight > 0) chart?.resize();
        });
        ro.observe(host);
        const unfollow = store.subscribe(() => {
          const b = buildRef.current;
          const w = store.get();
          if (chart === null || b === null || b.extent === null || store.origin() === uid) return;
          if (w !== null && w.axis !== (b.timeAxis ? "time" : b.orientation === "depth" ? "depth" : null)) return;
          const [lo, hi] = b.extent;
          const span = hi - lo || 1;
          const start = w === null ? 0 : Math.max(0, Math.min(100, ((w.from - lo) / span) * 100));
          const end = w === null ? 100 : Math.max(0, Math.min(100, ((w.to - lo) / span) * 100));
          range.current = { start, end };
          applying = true;
          try {
            chart.dispatchAction({ type: "dataZoom", dataZoomIndex: 0, start, end }, { silent: true });
          } finally {
            applying = false;
          }
        });
        stopFollowing = unfollow;
        setEngine("ready");
      })
      .catch(() => {
        if (!cancelled) setEngine("failed");
      });
    return () => {
      cancelled = true;
      stopFollowing?.();
      ro?.disconnect();
      chart?.off("datazoom");
      chart?.dispose();
      chartRef.current = null;
    };
  }, [hasBuild, store, uid]);

  // New spec on a live instance: replace, never merge (no stale series under a new label).
  useEffect(() => {
    const chart = chartRef.current;
    if (chart !== null && build !== null && engine === "ready") chart.setOption(build.option, true);
  }, [build, engine]);

  function zoomTo(start: number, end: number): void {
    const s = Math.max(0, Math.min(100, start));
    const e = Math.max(s, Math.min(100, end));
    range.current = { start: s, end: e };
    chartRef.current?.dispatchAction({ type: "dataZoom", dataZoomIndex: 0, start: s, end: e });
  }
  const zoomIn = () => {
    const { start, end } = range.current;
    const c = (start + end) / 2;
    const half = ((end - start) * ZOOM_STEP) / 2;
    zoomTo(c - half, c + half);
  };
  const zoomOut = () => {
    const { start, end } = range.current;
    const c = (start + end) / 2;
    const half = (end - start) / ZOOM_STEP / 2;
    zoomTo(c - half, c + half);
  };
  const pan = (dir: -1 | 1) => {
    const { start, end } = range.current;
    const d = ((end - start) / 4) * dir;
    const shift = Math.max(-start, Math.min(100 - end, d));
    zoomTo(start + shift, end + shift);
  };

  const Heading = `h${headingLevel}` as "h2" | "h3" | "h4";
  const { asOf, window: windowText } = describeWindow(spec);
  const summary = useMemo(() => summarizeChart(spec), [spec]);
  const rows = useMemo(() => seriesRows(spec), [spec]);
  const ambiguities = [spec.scope.ambiguity, ...spec.series.map((s) => s.scope.ambiguity)].filter((a, i, all): a is string => a !== null && all.indexOf(a) === i);
  const selected = spec.series.find((s) => s.series_key === tableKey) ?? spec.series[0];
  const zoomable = build !== null && build.extent !== null && cursorAxis !== null;
  const sel: CursorWindow | null = windowSel !== null && windowSel.axis === cursorAxis ? windowSel : null;
  const fmtBound = (n: number) => (cursorAxis === "time" ? windowBoundToIsoDate(n) : String(Math.round(n * 100) / 100));
  const sources = spec.series.flatMap((s) => s.evidence.map((ev, i) => ({ s, ev, key: `${s.series_key}:${i}` })));

  const [showMsg, setShowMsg] = useState<string | null>(null);
  const topWellbore = spec.scope.wellbore_id ?? spec.series.find((s) => s.scope.wellbore_id)?.scope.wellbore_id ?? wellboreId;
  // Only reference lines carry a formation reference (pick_id / surface_key); points and perforations carry none.
  const tops = spec.reference_lines.flatMap((r) => {
    const formationId = r.pick_id ?? r.surface_key;
    return formationId === null ? [] : [{ r, formationId }];
  });
  // Non-destructive link: an explicit action (not hover) because focusFormation moves the camera.
  function showIn3d(formationId: string, label: string) {
    if (bus === null || topWellbore === null) {
      setShowMsg(`${label}: ${SHOW_RESULT["no-subscriber"]}`);
      return;
    }
    setShowMsg(`${label}: ${SHOW_RESULT[bus.dispatch({ type: "focusFormation", wellboreId: topWellbore, formationId })]}`);
  }

  function open(link: Parameters<typeof openEvidence>[1]) {
    setOpenMsg(openEvidence(bus, link));
  }

  return (
    <section className={styles.block} aria-labelledby={`${uid}-t`} data-chart-key={spec.key} data-chart-id={spec.chart_id} data-testid={`chart-${spec.chart_id}`}>
      <header className={styles.head}>
        <Heading id={`${uid}-t`} className={styles.title}>
          {spec.title}
        </Heading>
        <span className={styles.badges}>
          {distinctScopes(spec).map((sc) => (
            <ScopeBadge key={`${sc.scope}:${sc.wellbore_id ?? ""}:${sc.scope_label}`} scope={sc} />
          ))}
        </span>
        <span className={styles.meta}>
          {asOf} · {windowText}
          {sel !== null && ` · Selected ${fmtBound(sel.from)} to ${fmtBound(sel.to)}`}
        </span>
      </header>

      {ambiguities.map((a) => (
        <Callout key={a} tone="warning" role="status" title="Association is ambiguous">
          {a}
        </Callout>
      ))}

      {spec.empty ? (
        <EmptyState title={EMPTY_TITLE[spec.empty.reason] ?? "No chart"}>{spec.empty.message}</EmptyState>
      ) : (
        <>
          {zoomable && (
            <div className={styles.toolbar} role="group" aria-label={`${spec.title} zoom`}>
              <button type="button" onClick={zoomIn}>Zoom in</button>
              <button type="button" onClick={zoomOut}>Zoom out</button>
              <button type="button" onClick={() => pan(-1)}>Pan back</button>
              <button type="button" onClick={() => pan(1)}>Pan forward</button>
              <button type="button" onClick={() => zoomTo(0, 100)}>Reset zoom</button>
            </div>
          )}
          <div className={styles.plotWrap} style={{ height }}>
            <div ref={hostRef} className={styles.plot} role="img" aria-label={summary} data-engine={engine} />
            {engine === "loading" && <p className={styles.overlay} role="status">Loading chart…</p>}
            {engine === "failed" && <p className={styles.overlay} role="alert">The chart renderer could not be loaded. The data table below still has every value.</p>}
          </div>
          <p className={styles.srOnly}>{summary}</p>

          {tops.length > 0 && (
            <ul className={styles.tops} aria-label={`${spec.title} formation tops`}>
              {tops.map(({ r, formationId }) => (
                <li key={`${r.axis_id}:${formationId}:${r.value}`}>
                  {r.label} ({r.value}
                  {r.unit ? ` ${r.unit}` : ""}){" "}
                  <button type="button" onClick={() => showIn3d(formationId, r.label)} aria-label={`Show ${r.label} in 3D`}>
                    Show in 3D
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className={styles.srOnly} role="status" aria-live="polite">{showMsg ?? ""}</p>
          {showMsg !== null && !showMsg.endsWith(SHOW_RESULT.handled) && <Callout tone="warning">{showMsg}</Callout>}

          <button type="button" className={styles.disclose} aria-expanded={tableOpen} aria-controls={`${uid}-tbl`} onClick={() => setTableOpen((o) => !o)}>
            {tableOpen ? "Hide data table" : "Show data table"}
          </button>
          {tableOpen && (
            <div id={`${uid}-tbl`} className={styles.tables}>
              <table className={styles.table}>
                <caption>Series summary for {spec.title} (exact values over the full record)</caption>
                <thead>
                  <tr>
                    <th scope="col">Series</th><th scope="col">Scope</th><th scope="col">Axis</th><th scope="col">Unit</th><th scope="col">Valid</th><th scope="col">Gaps</th>
                    <th scope="col">Min</th><th scope="col">Max</th><th scope="col">Last</th><th scope="col">Range</th><th scope="col">Displayed</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.key}>
                      <th scope="row">{r.name}</th><td>{r.scope}</td><td>{r.axis}</td><td>{r.unit}</td><td>{r.valid}</td><td>{r.gaps}</td>
                      <td>{r.min}</td><td>{r.max}</td><td>{r.last}</td><td>{r.range}</td><td>{r.displayed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {selected !== undefined && (
                <>
                  <label className={styles.pick}>
                    Points of series{" "}
                    <select value={selected.series_key} onChange={(e) => { setTableKey(e.target.value); setShown(PAGE); }}>
                      {spec.series.map((s, i) => (
                        <option key={s.series_key} value={s.series_key}>{rows[i]?.name ?? s.name}</option>
                      ))}
                    </select>
                  </label>
                  <table className={styles.table}>
                    <caption>
                      Supplied points of {selected.name} ({selected.points.length}); gaps are listed as gaps, not as zero
                    </caption>
                    <thead>
                      <tr><th scope="col">{spec.axes.find((a) => a.position === "x")?.name ?? "x"}</th><th scope="col">Value ({rows.find((r) => r.key === selected.series_key)?.unit})</th></tr>
                    </thead>
                    <tbody>
                      {pointRows(selected, 0, shown).map((p, i) => (
                        <tr key={i}><td>{p.x}</td><td>{p.y}</td></tr>
                      ))}
                    </tbody>
                  </table>
                  {shown < selected.points.length && (
                    <button type="button" onClick={() => setShown((n) => n + PAGE)}>Show {Math.min(PAGE, selected.points.length - shown)} more points</button>
                  )}
                </>
              )}
            </div>
          )}

          <details className={styles.sources}>
            <summary>Sources ({sources.length + spec.evidence.length})</summary>
            {sources.length + spec.evidence.length === 0 && <p>No source link is recorded for this chart.</p>}
            <ul>
              {sources.map(({ s, ev, key }) => (
                <li key={key}>
                  {s.name}:{" "}
                  <button type="button" onClick={() => open(ev)} aria-label={`Open source for ${s.name}: ${evidenceLabel(ev)}`}>
                    {evidenceLabel(ev)}
                  </button>
                </li>
              ))}
              {spec.evidence.map((ev, i) => (
                <li key={`c${i}`}>
                  Chart:{" "}
                  <button type="button" onClick={() => open(ev)} aria-label={`Open chart source: ${evidenceLabel(ev)}`}>
                    {evidenceLabel(ev)}
                  </button>
                </li>
              ))}
            </ul>
          </details>
          <p className={styles.srOnly} role="status" aria-live="polite">{openMsg === null ? "" : OPEN_RESULT_MESSAGE[openMsg]}</p>
          {openMsg !== null && openMsg !== "opened" && <Callout tone="warning">{OPEN_RESULT_MESSAGE[openMsg]}</Callout>}
        </>
      )}

      {spec.excluded_series.length > 0 && (
        <Callout tone="neutral" title="Left out of this chart">
          <ul>
            {spec.excluded_series.map((x, i) => (
              <li key={i}>{x.name}: {x.reason}</li>
            ))}
          </ul>
        </Callout>
      )}
      {spec.notes.length > 0 && (
        <ul className={styles.notes}>
          {spec.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
