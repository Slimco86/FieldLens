import { useCallback, useEffect, useState } from "react";
import type { ExploreStageContext } from "../../app/shell/exploreStage";
import { getFieldCharts, getWellboreCharts, normalizeChart, type ChartSpec, type ExcludedSeries, type FieldChartSet, type WellboreChartSet } from "./api";

export interface ChartSetParams {
  projectId: string;
  context: ExploreStageContext;
  asOf?: string | null;
  from?: string | null;
  to?: string | null;
}

export type ChartSetState =
  | { status: "loading" }
  | { status: "error"; message: string; requestId: string | null }
  | {
      status: "ready";
      kind: "wellbore" | "field";
      charts: ChartSpec[];
      rejected: string[];
      ambiguities: string[];
      excluded: ExcludedSeries[];
      note: string | null;
      label: string;
    };

function requestKey(p: ChartSetParams, nonce: number): string {
  const who = p.context.kind === "wellbore" ? `w:${p.context.wellboreId}` : "field";
  return JSON.stringify([p.projectId, who, p.asOf ?? null, p.from ?? null, p.to ?? null, nonce]);
}

type Settled = { key: string; state: Exclude<ChartSetState, { status: "loading" }> };

/** Keeps only charts whose scope matches the view; anything else is reported, never drawn (XC-2). */
export function partitionCharts(ctx: ExploreStageContext, set: WellboreChartSet | FieldChartSet): { charts: ChartSpec[]; rejected: string[] } {
  const charts: ChartSpec[] = [];
  const rejected: string[] = [];
  for (const raw of set.charts ?? []) {
    const c = normalizeChart(raw);
    const s = c.scope;
    const ok =
      ctx.kind === "wellbore"
        ? s.scope === "well" || (s.scope === "wellbore" && s.wellbore_id === ctx.wellboreId)
        : s.scope === "field" || s.scope === "project" || s.scope === "unreconciled";
    if (ok) charts.push(c);
    else rejected.push(c.title);
  }
  return { charts, rejected };
}

/**
 * Loads the chart set of the current view. Changing wellbore/field, as-of or window aborts the previous request,
 * and a result is only exposed when its key equals the current key, so an out-of-order answer never paints under
 * the wrong label (XC-5). The response itself is also checked against what was asked for.
 */
export function useChartSet(params: ChartSetParams): { state: ChartSetState; reload: () => void } {
  const { projectId, context, asOf = null, from = null, to = null } = params;
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const wellboreId = context.kind === "wellbore" ? context.wellboreId : null;
  const key = requestKey({ projectId, context: wellboreId === null ? { kind: "field" } : { kind: "wellbore", wellboreId }, asOf, from, to }, nonce);

  useEffect(() => {
    const ctl = new AbortController();
    const q = { asOf, from, to };
    const ctx: ExploreStageContext = wellboreId === null ? { kind: "field" } : { kind: "wellbore", wellboreId };
    const work: Promise<WellboreChartSet | FieldChartSet> = wellboreId === null ? getFieldCharts(projectId, q, ctl.signal) : getWellboreCharts(projectId, wellboreId, q, ctl.signal);
    work
      .then((set) => {
        if (ctl.signal.aborted) return;
        if (set.project_id !== projectId || ("wellbore_id" in set && set.wellbore_id !== wellboreId)) {
          setSettled({ key, state: { status: "error", message: "The chart response belongs to a different project or wellbore and was rejected.", requestId: null } });
          return;
        }
        if (asOf && set.as_of !== asOf) {
          setSettled({ key, state: { status: "error", message: `The chart response is for ${set.as_of ?? "no date"}, not the selected as-of date ${asOf}; it was rejected.`, requestId: null } });
          return;
        }
        const { charts, rejected } = partitionCharts(ctx, set);
        const bore = "wellbore_id" in set ? set : null;
        setSettled({
          key,
          state: {
            status: "ready",
            kind: ctx.kind,
            charts,
            rejected,
            ambiguities: bore?.ambiguities ?? [],
            excluded: "excluded_series" in set ? (set.excluded_series ?? []) : [],
            note: "reconciliation_note" in set ? (set.reconciliation_note ?? null) : null,
            label: bore === null ? "" : [bore.wellbore_label, bore.well_name].filter(Boolean).join(" · "),
          },
        });
      })
      .catch((e: unknown) => {
        if (ctl.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) return;
        const err = e as { message?: string; requestId?: string | null };
        setSettled({ key, state: { status: "error", message: err.message ?? "Charts could not be loaded.", requestId: err.requestId ?? null } });
      });
    return () => ctl.abort();
  }, [key, projectId, wellboreId, asOf, from, to]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const state: ChartSetState = settled !== null && settled.key === key ? settled.state : { status: "loading" };
  return { state, reload };
}
