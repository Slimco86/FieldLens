import { createContext, useContext, useState, type ReactNode } from "react";
import { useExploreCommandBus } from "../scene/ExploreCommandsContext";
import type { AnswerBlock, ChartSpec, ChatAnswer, ChatTurn } from "./api";
import { citationToCommand, dispatchAppLink, dispatchCommand, type LinkResult } from "./links";
import { Markdown } from "./Markdown";
import styles from "./Assistant.module.css";

/** Narrow seam for the real ChartBlock (TASK-102); integration injects it, a table is the fallback. */
export type RenderChart = (spec: ChartSpec) => ReactNode;
const ChartRendererContext = createContext<RenderChart | null>(null);
export const AssistantChartRendererProvider = ChartRendererContext.Provider;

const GAP_LABEL: Record<string, string> = {
  no_data: "No data",
  out_of_scope: "Out of scope",
  refused: "Refused",
  unavailable: "Unavailable",
  draft_only: "Draft only",
};

export function FallbackChartTable({ spec }: { spec: ChartSpec }) {
  const series = spec.series ?? [];
  return (
    <div className={styles.chartFallback} data-testid="chart-fallback">
      {spec.empty !== null ? <p role="note">{spec.empty.message}</p> : null}
      <table aria-label={`${spec.title}: series summary`}>
        <caption>{spec.title}</caption>
        <thead>
          <tr>
            <th scope="col">Series</th>
            <th scope="col">Scope</th>
            <th scope="col">Unit</th>
            <th scope="col">Points</th>
            <th scope="col">Gaps</th>
          </tr>
        </thead>
        <tbody>
          {series.map((s) => (
            <tr key={s.series_key}>
              <th scope="row">{s.name}</th>
              <td>{s.scope.scope_label}</td>
              <td>{s.unit ?? (s.unit_status === "missing" ? "unit not stated" : s.unit_status)}</td>
              <td>{(s.points ?? []).length}</td>
              <td>{s.gap_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {spec.as_of !== null ? <p>As of {spec.as_of}</p> : null}
    </div>
  );
}

function ChartBlockView({ block, onOpen }: { block: Extract<AnswerBlock, { kind: "chart" }>; onOpen: (r: LinkResult) => void }) {
  const render = useContext(ChartRendererContext);
  const bus = useExploreCommandBus();
  const spec = block.spec;
  const link = block.open_in_charts;
  return (
    <figure className={styles.block} data-block="chart">
      {spec === null ? (
        <p role="note" className={styles.gap}>
          Chart not available: it was not materialized or failed to build. No values are shown.
        </p>
      ) : (
        <>
          <figcaption>{spec.title}</figcaption>
          {render !== null ? render(spec) : <FallbackChartTable spec={spec} />}
        </>
      )}
      {link !== null ? (
        <button type="button" className={styles.linkButton} onClick={() => onOpen(dispatchAppLink(bus, link))}>
          Open in Charts tab
        </button>
      ) : null}
    </figure>
  );
}

function Markers({ markers }: { markers: string[] | undefined }) {
  if (markers === undefined || markers.length === 0) return null;
  return <span className={styles.markers}>{markers.join(" ")}</span>;
}

export function BlockView({ block, onOpen }: { block: AnswerBlock; onOpen: (r: LinkResult) => void }) {
  const bus = useExploreCommandBus();
  switch (block.kind) {
    case "text":
      return (
        <div className={styles.block} data-block="text">
          <Markdown text={block.text} />
          <Markers markers={block.citation_markers} />
          {(block.unverified_numbers ?? []).length > 0 ? (
            <p role="note" className={styles.warn}>
              Unverified numbers: {(block.unverified_numbers ?? []).join(", ")}
            </p>
          ) : null}
        </div>
      );
    case "value":
      return (
        <dl className={styles.block} data-block="value">
          <dt>{block.label}</dt>
          <dd>
            {block.value !== null ? (
              <>
                <strong>{block.value}</strong> {block.unit}
                {block.reference !== null ? <span className={styles.ref}> ({block.reference})</span> : null}
              </>
            ) : (
              <span className={styles.gap}>Unknown{block.unknown_reason !== null ? `: ${block.unknown_reason}` : ""}</span>
            )}
            <Markers markers={block.citation_markers} />
          </dd>
        </dl>
      );
    case "chart":
      return <ChartBlockView block={block} onOpen={onOpen} />;
    case "gap":
      return (
        <p role="note" className={styles.gap} data-block="gap">
          <strong>Data not available ({GAP_LABEL[block.reason] ?? block.reason}).</strong> {block.text}
        </p>
      );
    case "link":
      return (
        <p className={styles.block} data-block="link">
          <button type="button" className={styles.linkButton} onClick={() => onOpen(dispatchAppLink(bus, block.link))}>
            {block.link.label}
          </button>
        </p>
      );
  }
}

/** The assistant's answer: blocks, citation chips, verification and an explicit link-outcome message. */
export function AnswerView({ answer }: { answer: ChatAnswer }) {
  const bus = useExploreCommandBus();
  const [result, setResult] = useState<LinkResult | null>(null);
  const citations = answer.citations ?? [];
  const dropped = answer.dropped_blocks ?? [];
  return (
    <div className={styles.answer} data-verification={answer.verification}>
      {answer.verification !== "verified" ? (
        <p role="note" className={styles.warn}>
          {answer.verification === "unverified" ? "Not verified against sources." : "Partially verified."}
        </p>
      ) : null}
      {citations.some((c) => c.draft) ? (
        <p role="note" className={styles.warn}>
          Includes draft, unpublished context that is not yet approved evidence.
        </p>
      ) : null}
      {(answer.blocks ?? []).map((b, i) => (
        <BlockView key={i} block={b} onOpen={setResult} />
      ))}
      {dropped.length > 0 ? (
        <p role="note" className={styles.warn}>
          {dropped.length} block{dropped.length === 1 ? "" : "s"} failed validation and {dropped.length === 1 ? "was" : "were"} not shown.
        </p>
      ) : null}
      {citations.length > 0 ? (
        <ul className={styles.citations} aria-label="Citations">
          {citations.map((c) => {
            const cmd = citationToCommand(c);
            const label = `${c.marker}${c.label !== null ? ` ${c.label}` : ""}`;
            return (
              <li key={c.marker}>
                <button
                  type="button"
                  className={styles.chip}
                  data-draft={c.draft ? "true" : undefined}
                  disabled={cmd === null}
                  title={cmd === null ? "No openable source for this citation" : "Open source"}
                  onClick={() => setResult(dispatchCommand(bus, cmd))}
                >
                  {label}
                  {c.draft ? <span className={styles.draftTag}> Draft, unpublished</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
      <p role="status" className={result?.ok === false ? styles.warn : styles.srOnly}>
        {result?.message ?? ""}
      </p>
    </div>
  );
}

export function TurnView({ turn }: { turn: ChatTurn }) {
  return <AnswerOrState turn={turn} />;
}

function AnswerOrState({ turn }: { turn: ChatTurn }) {
  const answer = turn.assistant_message?.answer ?? null;
  const text = turn.assistant_message?.text ?? null;
  const live = turn.state === "queued" || turn.state === "running";
  return (
    <div data-turn-state={turn.state}>
      {answer !== null ? <AnswerView answer={answer} /> : text !== null ? <Markdown text={text} /> : null}
      {live ? <p className={styles.state}>{turn.state === "queued" ? "Queued…" : "Working…"}</p> : null}
    </div>
  );
}
