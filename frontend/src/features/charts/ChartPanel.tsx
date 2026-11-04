import { useExploreStage, type ExploreStageContext } from "../../app/shell/exploreStage";
import { Callout, ErrorState, LoadingState } from "../../design";
import { ChartCard } from "./ChartCard";
import { useChartSet } from "./useChartSet";
import styles from "./Charts.module.css";

export interface ChartPanelProps {
  projectId: string;
  /** Wellbore or field; defaults to the Explore stage context, then to the field view. */
  context?: ExploreStageContext;
  /** Selected as-of date (ISO). Distinct from measurement dates inside the data. */
  asOf?: string | null;
  /** Optional time window (ISO dates). */
  from?: string | null;
  to?: string | null;
}

const FIELD: ExploreStageContext = { kind: "field" };

/**
 * Charts slot content for the Explore workspace. A wellbore view renders only that wellbore's chart set (plus
 * labeled well-level series); a field view renders only the global field set. Stale requests are aborted and
 * out-of-order answers are never painted (see useChartSet).
 */
export function ChartPanel({ projectId, context, asOf = null, from = null, to = null }: ChartPanelProps) {
  const stage = useExploreStage();
  const ctx = context ?? stage?.context ?? FIELD;
  const { state, reload } = useChartSet({ projectId, context: ctx, asOf, from, to });
  const heading = ctx.kind === "wellbore" ? "Wellbore charts" : "Field charts";
  const noticeCount = state.status === "ready" ? (state.note ? 1 : 0) + state.ambiguities.length + state.rejected.length + state.excluded.length : 0;
  const label = state.status === "ready" ? state.label : "";

  return (
    <div className={styles.panel} data-testid="chart-panel" data-context={ctx.kind} aria-busy={state.status === "loading"}>
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>
          {heading}
          {label !== "" && `: ${label}`}
        </h2>
      </div>
      {state.status === "loading" && <LoadingState label={ctx.kind === "wellbore" ? "Loading wellbore charts…" : "Loading field charts…"} status />}
      {state.status === "error" && <ErrorState message={`Charts could not be loaded: ${state.message}`} requestId={state.requestId} onRetry={reload} />}
      {state.status === "ready" && (
        <>
          {noticeCount > 0 && (
            <details className={styles.notices} data-testid="chart-notices">
              <summary>
                {[
                  state.note ? "1 note" : null,
                  state.ambiguities.length > 0 ? `${state.ambiguities.length} ambiguous association${state.ambiguities.length === 1 ? "" : "s"}` : null,
                  state.rejected.length > 0 ? `${state.rejected.length} chart${state.rejected.length === 1 ? "" : "s"} not shown` : null,
                  state.excluded.length > 0 ? `${state.excluded.length} series excluded from field totals` : null,
                ]
                  .filter((x): x is string => x !== null)
                  .join(" · ")}
              </summary>
              <div className={styles.noticeBody}>
          {state.note && (
            <Callout tone="info" role="status">
              {state.note}
            </Callout>
          )}
          {state.ambiguities.length > 0 && (
            <Callout tone="warning" role="status" title="Association is ambiguous">
              <ul>
                {state.ambiguities.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </Callout>
          )}
          {state.rejected.length > 0 && (
            <Callout tone="warning" role="status" title="Charts not shown">
              Out of scope for this view and not drawn: {state.rejected.join(", ")}.
            </Callout>
          )}
          {state.excluded.length > 0 && (
            <Callout tone="neutral" title="Series excluded from field totals">
              <ul>
                {state.excluded.map((x, i) => (
                  <li key={i}>
                    {x.name}: {x.reason}
                  </li>
                ))}
              </ul>
            </Callout>
          )}
              </div>
            </details>
          )}
          {state.charts.length === 0 ? (
            <Callout tone="info" role="status">
              No charts are available for this view.
            </Callout>
          ) : (
            <div className={styles.grid}>
              {state.charts.map((c) => (
                <ChartCard key={`${c.chart_id}:${c.cache_key}`} spec={c} wellboreId={ctx.kind === "wellbore" ? ctx.wellboreId : null} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
