import { useId, useState } from "react";
import { Button, Title } from "@mantine/core";
import { Ban, CircleCheck, CircleX, Clock, Info, LoaderCircle, TriangleAlert } from "lucide-react";
import { Callout, Chip, EmptyState, ErrorState, LoadingState } from "../../design";
import type { Failure } from "../projects/scope";
import { FAILURE_LABEL, FAILURE_TEXT, STUB_TEXT, type ModelReplyRaw, type ModelRunEntry } from "./api";
import styles from "./Processing.module.css";

const RUN_CHIP: Record<ModelRunEntry["state"], { spec: Parameters<typeof Chip>[0]["spec"]; label: string }> = {
  estimated: { spec: { tone: "neutral", icon: Clock }, label: "Estimated, not confirmed" },
  pending: { spec: { tone: "info", icon: Clock }, label: "Queued" },
  running: { spec: { tone: "info", icon: LoaderCircle, spin: true }, label: "Running" },
  processed: { spec: { tone: "success", icon: CircleCheck }, label: "Processed" },
  failed: { spec: { tone: "danger", icon: CircleX }, label: "Failed" },
  cancelled: { spec: { tone: "neutral", icon: Ban }, label: "Cancelled" },
  interrupted: { spec: { tone: "warning", icon: TriangleAlert }, label: "Interrupted" },
};
const STUB_CHIP = { spec: { tone: "neutral", icon: Info }, label: "Stub run" } as const;

export const isStubRun = (r: Pick<ModelRunEntry, "provider" | "state">) => r.provider === "stub" && r.state === "processed";

/** The run's own message (stub honesty) plus the fixed wording, without repeating it. */
export function stubText(message: string | null | undefined): string {
  return message != null && message.includes("FIELDLENS_PROCESSING_PROVIDER") ? message : [message, STUB_TEXT].filter(Boolean).join(" ");
}

const fmtTime = (iso: string | null) => (iso === null ? "not recorded" : new Date(iso).toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z"));
const fmtNum = (n: number | null) => (n === null ? "not recorded" : n.toLocaleString("en-US"));

function Run({ run }: { run: ModelRunEntry }) {
  const stub = isStubRun(run);
  const chip = stub ? STUB_CHIP : RUN_CHIP[run.state];
  const warnings = run.warnings ?? [];
  const model = run.model ?? "model not recorded";
  return (
    <li className={styles.run} aria-label={`Run ${run.run_id}`}>
      <div className={styles.row}>
        <Chip spec={chip.spec} label={chip.label} />
        <strong>
          {run.provider} / {model}
        </strong>
        {run.forced && <span className={styles.marker}>Forced re-read</span>}
        {run.cache_hit && <span className={styles.marker}>Reused, no model call</span>}
      </div>
      <dl className={styles.facts}>
        <dt>Started</dt>
        <dd>{fmtTime(run.started_at)}</dd>
        <dt>Finished</dt>
        <dd>{fmtTime(run.finished_at)}</dd>
        <dt>Pages read</dt>
        <dd>
          {run.pages_read} (window {run.pages.page_start}-{run.pages.page_end})
        </dd>
        <dt>Tokens</dt>
        <dd>
          {fmtNum(run.input_tokens)} input, {fmtNum(run.output_tokens)} output
        </dd>
        <dt>Cost (actual)</dt>
        <dd>USD {run.usd_actual}</dd>
        <dt>Cache</dt>
        <dd>{run.cache_hit ? "Reused, no model call" : "No cache hit"}</dd>
      </dl>
      {stub && <p className={styles.muted}>{stubText(run.message)}</p>}
      {!stub && run.message !== null && <p className={styles.muted}>{run.message}</p>}
      {run.failure_code !== null && (
        <p>
          <strong>{FAILURE_LABEL[run.failure_code]}</strong> (<code>{run.failure_code}</code>): {FAILURE_TEXT[run.failure_code]}
          {run.failure_message !== null && <> {run.failure_message}</>}
        </p>
      )}
      {run.failure_code === null && run.failure_message !== null && <p>{run.failure_message}</p>}
      {warnings.length > 0 && (
        <ul className={styles.list} aria-label="Run warnings">
          {warnings.map((w) => (
            <li key={w.code}>
              <TriangleAlert size={14} aria-hidden="true" /> <strong>Warning</strong> <code>{w.code}</code>
              {w.count > 1 ? ` (${w.count}x)` : ""}: {w.message}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export type OutcomeView =
  | { kind: "loading" }
  | { kind: "error"; error: Failure }
  | { kind: "ready"; runs: ModelRunEntry[]; refreshError: Failure | null };

/** Newest-first run history of one document: what ran, with which model, what it cost and why it failed. */
export function ModelHistory({ view, onRetry }: { view: OutcomeView; onRetry: () => void }) {
  const headId = useId();
  return (
    <section className={styles.history} aria-labelledby={headId}>
      <Title order={6} id={headId}>
        Model processing history
      </Title>
      {view.kind === "loading" && <LoadingState label="Loading model processing history…" status />}
      {view.kind === "error" && (
        <ErrorState
          message={`The model processing history could not be loaded: ${view.error.message}`}
          requestId={view.error.requestId}
          onRetry={onRetry}
          retryLabel="Retry loading model processing history"
        />
      )}
      {view.kind === "ready" && (
        <>
          {view.refreshError !== null && (
            <Callout tone="warning" role="status">
              <p>The latest history refresh failed ({view.refreshError.message}); this may be out of date.</p>
            </Callout>
          )}
          {view.runs.length === 0 ? (
            <EmptyState title="No model runs yet">Nothing has been processed with a model for this document.</EmptyState>
          ) : (
            <ol className={styles.list} aria-label="Model runs, newest first">
              {view.runs.map((r) => (
                <Run key={r.run_id} run={r} />
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}

/** The provider's reply as stored: untrusted text, collapsed by default, rendered only as text (never HTML). */
export function RawReply({ reply }: { reply: ModelReplyRaw }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const kib = reply.max_bytes / 1024;
  return (
    <div className={styles.raw}>
      <Button
        variant="default"
        size="xs"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "Hide" : "Show"} model reply (raw)
      </Button>
      <div id={id} hidden={!open} role="region" aria-label="Model reply (raw)">
        {open && (
          <>
            <p className={styles.muted}>Untrusted model output, shown as plain text. It is not verified and is never interpreted.</p>
            {reply.truncated && (
              <p role="status">
                Truncated: only the first {kib} KiB ({reply.max_bytes.toLocaleString("en-US")} bytes) of the reply is stored and shown.
              </p>
            )}
            {/* a scrollable region must be keyboard-focusable (axe scrollable-region-focusable) */}
            {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
            <pre className={styles.pre} tabIndex={0} aria-label="Model reply text (untrusted)">{reply.text}</pre>
          </>
        )}
      </div>
    </div>
  );
}
