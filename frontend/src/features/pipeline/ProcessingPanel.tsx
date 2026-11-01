import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Checkbox, Table, Title } from "@mantine/core";
import { Ban, CircleCheck, CircleHelp, CircleX, Clock, Info, LoaderCircle, RefreshCw, TriangleAlert } from "lucide-react";
import { Callout, Chip, EmptyState, ErrorState, LoadingState, type ChipSpec } from "../../design";
import { keyString } from "../projects/keys";
import { toFailure, type Failure } from "../projects/scope";
import { usePolled } from "../uploads/usePolled";
import {
  cancelRun,
  confirmRun,
  getProcessingDocuments,
  getRun,
  listRuns,
  requestEstimate,
  retryRun,
  type DocumentProcessingState,
  type ProcessingDocumentSelection,
  type ProcessingRun,
  type ProcessingRunStatus,
} from "./api";
import styles from "./Pipeline.module.css";

export const PAGE_CAP = 500;
export const BUDGET_TOTAL_USD = "5";

export const RUN_STATUS: Record<ProcessingRunStatus, { spec: ChipSpec; label: string }> = {
  estimated: { spec: { tone: "info", icon: Clock }, label: "Estimated: not confirmed, nothing spent" },
  queued: { spec: { tone: "info", icon: Clock }, label: "Queued" },
  running: { spec: { tone: "info", icon: LoaderCircle, spin: true }, label: "Running" },
  succeeded: { spec: { tone: "success", icon: CircleCheck }, label: "Succeeded" },
  partial: { spec: { tone: "warning", icon: TriangleAlert }, label: "Partial: some documents did not finish" },
  failed: { spec: { tone: "danger", icon: CircleX }, label: "Failed" },
  cancelled: { spec: { tone: "neutral", icon: Ban }, label: "Cancelled" },
  interrupted: { spec: { tone: "warning", icon: TriangleAlert }, label: "Interrupted: not completed" },
};
const DOC_STATE: Record<DocumentProcessingState["processing_status"], { spec: ChipSpec; label: string }> = {
  not_started: { spec: { tone: "neutral", icon: Clock }, label: "Not started" },
  queued: RUN_STATUS.queued,
  running: RUN_STATUS.running,
  processed: { spec: { tone: "success", icon: CircleCheck }, label: "Processed" },
  failed: RUN_STATUS.failed,
  cancelled: RUN_STATUS.cancelled,
  interrupted: RUN_STATUS.interrupted,
};
const RUN_DOC_STATE: Record<ProcessingRun["documents"][number]["state"], { spec: ChipSpec; label: string }> = {
  estimated: { spec: { tone: "info", icon: Clock }, label: "Estimated" },
  pending: { spec: { tone: "info", icon: Clock }, label: "Pending" },
  running: RUN_STATUS.running,
  processed: DOC_STATE.processed,
  failed: RUN_STATUS.failed,
  cancelled: RUN_STATUS.cancelled,
  interrupted: RUN_STATUS.interrupted,
};
const UNKNOWN: { spec: ChipSpec; label: string } = { spec: { tone: "unknown", icon: CircleHelp }, label: "Unknown state" };

const isLive = (s: ProcessingRunStatus) => s === "queued" || s === "running";
const usd = (v: string) => `USD ${v}`;

/** One server-mutating action at a time, never replayed; its outcome is dropped after unmount. */
function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<Failure | null>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const run = async <T,>(name: string, fn: () => Promise<T>): Promise<T | null> => {
    setBusy(name);
    setError(null);
    try {
      const out = await fn();
      return alive.current ? out : null;
    } catch (err) {
      if (alive.current) setError(toFailure(err));
      return null;
    } finally {
      if (alive.current) setBusy(null);
    }
  };
  return { busy, error, run, clear: () => setError(null) };
}

function ActionError({ what, error }: { what: string; error: Failure }) {
  const stale = error.status === 409 || error.status === 422;
  return (
    <Callout tone="danger" role="alert">
      <p>
        {what} was rejected: {error.message}
        {error.code !== null && <> (<code>{error.code}</code>)</>}
      </p>
      {stale && <p>Nothing was started or spent. Refresh the run state or request a new estimate.</p>}
      {error.requestId !== null && <p>Request ID: {error.requestId}</p>}
    </Callout>
  );
}

export function RunDetail({
  projectId,
  runId,
  onOpen,
  onChanged,
}: {
  projectId: string;
  runId: string;
  onOpen: (runId: string) => void;
  onChanged: () => void;
}) {
  const { state, reload, replace } = usePolled(
    keyString(["pipeline", "run", projectId, runId]),
    (signal) => getRun(projectId, runId, signal),
    (r) => isLive(r.status),
  );
  const action = useAction();
  const run = state.kind === "ready" && state.data.project_id === projectId ? state.data : null;

  const apply = async (name: string, fn: () => Promise<ProcessingRun>, open = false) => {
    const out = await action.run(name, fn);
    if (out === null) {
      reload(); // a rejection may mean the run moved on; show the truth
      return;
    }
    if (open) onOpen(out.run_id);
    else replace(out);
    onChanged();
  };

  return (
    <section aria-labelledby="pl-run" className={styles.section}>
      <Title order={6} id="pl-run">
        Run detail
      </Title>
      {state.kind === "loading" && <LoadingState label="Loading run…" status />}
      {state.kind === "error" && (
        <ErrorState
          message={`The run could not be loaded: ${state.error.message}`}
          requestId={state.error.requestId}
          onRetry={reload}
          retryLabel="Retry loading run"
        />
      )}
      {state.kind === "ready" && state.refreshError !== null && (
        <Callout tone="warning" role="alert">
          <p>Refreshing the run failed: {state.refreshError.message}. The state below may be out of date.</p>
        </Callout>
      )}
      {run !== null && (
        <>
          <div className={styles.row} role="status" aria-label="Run status">
            <Chip spec={RUN_STATUS[run.status].spec} label={RUN_STATUS[run.status].label} />
            {run.estimate.provider === "stub" && (
              <Chip spec={{ tone: "neutral", icon: Info }} label="Stub provider: illustrative, no extracted data, no live spend" />
            )}
            {run.cancel_requested && isLive(run.status) && <span>Cancel requested; waiting for the worker to stop.</span>}
          </div>
          {run.step === "stub" && (
            <p className={styles.note}>The stub step only walks the pages; it produces no classification or extraction.</p>
          )}
          {(run.status === "failed" || run.status === "interrupted" || run.status === "partial" || run.status === "cancelled") && (
            <Callout tone="warning" role="status">
              <p>
                This run did not complete successfully.
                {run.error_code !== null && (
                  <>
                    {" "}
                    <code>{run.error_code}</code>
                  </>
                )}{" "}
                {run.error_message ?? ""} Documents that did not finish are not processed.
              </p>
            </Callout>
          )}
          <EstimateFacts run={run} />
          {run.status === "estimated" && (
            <div className={styles.confirm} role="group" aria-label="Confirm run">
              <Title order={6}>Confirm and start</Title>
              <p className={styles.note}>
                Nothing has been spent. Confirming starts this run for {usd(run.estimate.estimated_usd)} (estimated,
                provider {run.estimate.provider}). If real usage exceeds this estimate the run stops; it never
                restarts by itself.
              </p>
              {!run.estimate.fits_budget && (
                <Callout tone="danger" role="alert">
                  <p>
                    This estimate does not fit the remaining budget ({usd(run.estimate.remaining_budget_usd)} left of{" "}
                    {usd(run.estimate.total_cap_usd)}). It cannot be confirmed; select fewer documents.
                  </p>
                </Callout>
              )}
              <div className={styles.actions}>
                <Button
                  disabled={!run.estimate.confirmable || action.busy !== null}
                  loading={action.busy === "confirm"}
                  onClick={() => void apply("confirm", () => confirmRun(projectId, run.run_id, run.estimate.estimated_usd))}
                >
                  Confirm and start run ({usd(run.estimate.estimated_usd)})
                </Button>
              </div>
            </div>
          )}
          <RunDocuments run={run} />
          <div className={styles.actions}>
            {isLive(run.status) && (
              <Button
                variant="default"
                disabled={run.cancel_requested || action.busy !== null}
                loading={action.busy === "cancel"}
                onClick={() => void apply("cancel", () => cancelRun(projectId, run.run_id))}
              >
                Cancel run
              </Button>
            )}
            {!isLive(run.status) && run.status !== "estimated" && run.documents.some((d) => d.retryable) && (
              <Button
                variant="default"
                disabled={action.busy !== null}
                loading={action.busy === "retry"}
                onClick={() => void apply("retry", () => retryRun(projectId, run.run_id), true)}
              >
                Request retry estimate for {run.documents.filter((d) => d.retryable).length} document(s)
              </Button>
            )}
            <Button variant="subtle" size="xs" leftSection={<RefreshCw size={14} aria-hidden="true" />} onClick={reload}>
              Refresh run
            </Button>
          </div>
          {run.status !== "estimated" && run.documents.some((d) => d.retryable) && !isLive(run.status) && (
            <p className={styles.note}>A retry creates a new estimate and spends nothing until you confirm it.</p>
          )}
          {action.error !== null && <ActionError what="The action" error={action.error} />}
        </>
      )}
    </section>
  );
}

function EstimateFacts({ run }: { run: ProcessingRun }) {
  const e = run.estimate;
  return (
    <div role="group" aria-label="Estimate">
    <dl className={styles.list}>
      <div className={styles.row}>
        <dt>Pages</dt>
        <dd>{e.pages.toLocaleString("en-US")}</dd>
      </div>
      <div className={styles.row}>
        <dt>Route</dt>
        <dd>{e.route} (no OCR: scanned pages are read by the model route)</dd>
      </div>
      <div className={styles.row}>
        <dt>Estimated tokens</dt>
        <dd>
          {e.estimated_input_tokens.toLocaleString("en-US")} input, {e.estimated_output_tokens.toLocaleString("en-US")} output
        </dd>
      </div>
      <div className={styles.row}>
        <dt>Estimated cost</dt>
        <dd>
          {usd(e.estimated_usd)} ({e.pricing_source})
        </dd>
      </div>
      <div className={styles.row}>
        <dt>Remaining budget</dt>
        <dd>
          {usd(e.remaining_budget_usd)} of {usd(e.total_cap_usd)} total
        </dd>
      </div>
      <div className={styles.row}>
        <dt>Actual cost so far</dt>
        <dd>{usd(run.actual_usd)}</dd>
      </div>
    </dl>
    </div>
  );
}

function RunDocuments({ run }: { run: ProcessingRun }) {
  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- keyboard-scrollable region
    <div className={styles.scroll} role="region" aria-label="Run documents table" tabIndex={0}>
      <Table captionSide="top">
        <Table.Caption>Documents in this run</Table.Caption>
        <Table.Thead>
          <Table.Tr>
            <Table.Th scope="col">Document</Table.Th>
            <Table.Th scope="col">State</Table.Th>
            <Table.Th scope="col" className={styles.num}>Progress</Table.Th>
            <Table.Th scope="col" className={styles.num}>Estimated / actual</Table.Th>
            <Table.Th scope="col">Detail</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {run.documents.map((d) => {
            const st = RUN_DOC_STATE[d.state] ?? UNKNOWN;
            const total = d.pages.page_end - d.pages.page_start + 1;
            return (
              <Table.Tr key={d.document_id}>
                <Table.Th scope="row">{d.original_filename}</Table.Th>
                <Table.Td>
                  <Chip spec={st.spec} label={st.label} />
                </Table.Td>
                <Table.Td className={styles.num}>
                  {d.pages_done} / {total} pages
                  <progress className="sr-only" value={d.pages_done} max={Math.max(total, 1)} aria-label={`${d.original_filename} progress`} />
                </Table.Td>
                <Table.Td className={styles.num}>
                  {d.estimated_usd} / {d.actual_usd}
                </Table.Td>
                <Table.Td>
                  {d.pages.page_start !== 1 || d.pages.page_end !== d.page_count ? (
                    <div>
                      Pages {d.pages.page_start} to {d.pages.page_end} of {d.page_count}
                    </div>
                  ) : null}
                  {d.label_hints !== undefined && d.label_hints.length > 0 && <div>Label hints: {d.label_hints.join(", ")}</div>}
                  {d.failure_code !== null && (
                    <div>
                      <code>{d.failure_code}</code> {d.failure_message ?? ""}
                      {d.retryable ? " (retryable)" : ""}
                    </div>
                  )}
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </div>
  );
}

type Range = { start: string; end: string };

export function parseRange(r: Range | undefined, pageCount: number | null): { ok: true; pages: ProcessingDocumentSelection["pages"] } | { ok: false; reason: string } {
  if (r === undefined || r.start === "" || r.end === "") return { ok: false, reason: "enter both page numbers" };
  const s = Number(r.start);
  const e = Number(r.end);
  if (!Number.isInteger(s) || !Number.isInteger(e) || s < 1 || e < s) return { ok: false, reason: "use whole pages, start before end" };
  if (pageCount !== null && e > pageCount) return { ok: false, reason: `the document has ${pageCount} pages` };
  if (e - s + 1 > PAGE_CAP) return { ok: false, reason: `at most ${PAGE_CAP} pages per run` };
  return { ok: true, pages: { page_start: s, page_end: e } };
}

export function ProcessingPanel({ projectId, refreshKey, onChanged }: { projectId: string; refreshKey: number; onChanged: () => void }) {
  const docs = usePolled(
    keyString(["pipeline", "pdocs", projectId, refreshKey]),
    (signal) => getProcessingDocuments(projectId, signal),
    (l) => l.items.some((i) => i.processing_status === "queued" || i.processing_status === "running"),
  );
  const runs = usePolled(
    keyString(["pipeline", "runs", projectId, refreshKey]),
    (signal) => listRuns(projectId, signal),
    (p) => p.items.some((r) => isLive(r.status)),
  );
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const [ranges, setRanges] = useState<Record<string, Range>>({});
  const [viewRun, setViewRun] = useState<string | null>(null);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const action = useAction();

  const items = useMemo(() => (docs.state.kind === "ready" ? docs.state.data.items : []), [docs.state]);
  const ready = docs.state.kind === "ready" && docs.state.data.project_id === projectId;
  const idle = (d: DocumentProcessingState) => d.processing_status !== "queued" && d.processing_status !== "running";
  const effective = useMemo(() => {
    const base = picked ?? new Set(items.filter((d) => d.processable && d.no_native_parser && idle(d)).map((d) => d.document_id));
    return new Set(items.filter((d) => d.processable && idle(d) && base.has(d.document_id)).map((d) => d.document_id));
  }, [picked, items]);

  const runItems = useMemo(() => (runs.state.kind === "ready" ? runs.state.data.items : []), [runs.state]);
  const newest = useMemo(
    () => [...runItems].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]?.run_id ?? null,
    [runItems],
  );
  const shownRun = viewRun ?? newest;

  const toggle = (id: string, on: boolean) => {
    const next = new Set(effective);
    if (on) next.add(id);
    else next.delete(id);
    setPicked(next);
  };

  const onEstimate = async () => {
    const selection: ProcessingDocumentSelection[] = [];
    for (const d of items) {
      if (!effective.has(d.document_id)) continue;
      if (d.over_page_cap) {
        const r = parseRange(ranges[d.document_id], d.page_count);
        if (!r.ok) {
          setRangeError(`${d.original_filename}: ${r.reason}.`);
          return;
        }
        selection.push({ document_id: d.document_id, pages: r.pages });
      } else {
        selection.push({ document_id: d.document_id, pages: null });
      }
    }
    setRangeError(null);
    const key = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    const run = await action.run("estimate", () => requestEstimate(projectId, selection, key));
    if (run !== null) {
      setViewRun(run.run_id);
      runs.reload();
      onChanged();
    }
  };

  const refresh = () => {
    docs.reload();
    runs.reload();
  };

  return (
    <section aria-labelledby="pl-processing" className={styles.section}>
      <Title order={6} id="pl-processing">
        Document processing
      </Title>
      <p className={styles.note}>
        Documents without a native parser can be read by the model route. Labels are optional hints, never required and
        never evidence. There is no OCR in this build. Nothing is processed until you request an estimate and then
        confirm it. Merge review of duplicate wells or wellbores is not yet available.
      </p>
      {docs.state.kind === "loading" && <LoadingState label="Loading document processing states…" status />}
      {docs.state.kind === "error" && (
        <ErrorState
          message={`Document processing states could not be loaded: ${docs.state.error.message}`}
          requestId={docs.state.error.requestId}
          onRetry={docs.reload}
          retryLabel="Retry loading document processing states"
        />
      )}
      {docs.state.kind === "ready" && docs.state.refreshError !== null && (
        <Callout tone="warning" role="alert">
          <p>Refreshing document states failed: {docs.state.refreshError.message}.</p>
        </Callout>
      )}
      {docs.state.kind === "ready" && !ready && (
        <ErrorState message="The document answer belonged to another project and was dropped." requestId={null} onRetry={docs.reload} />
      )}
      {ready && items.length === 0 && (
        <EmptyState title="No documents to process">
          <p>The latest source revision has no documents. Upload files first.</p>
        </EmptyState>
      )}
      {ready && items.length > 0 && (
        <fieldset className={styles.confirm}>
          <legend>Select documents to estimate</legend>
          <ul className={styles.list}>
            {items.map((d) => {
              const st = DOC_STATE[d.processing_status] ?? UNKNOWN;
              const r = ranges[d.document_id];
              return (
                <li key={d.document_id} className={styles.row}>
                  <Checkbox
                    checked={effective.has(d.document_id)}
                    disabled={!d.processable || !idle(d)}
                    onChange={(e) => toggle(d.document_id, e.currentTarget.checked)}
                    label={d.original_filename}
                  />
                  <Chip spec={st.spec} label={st.label} />
                  <span>{d.state_text}</span>
                  {d.page_count !== null && <span>{d.page_count} pages</span>}
                  {d.user_labels !== undefined && d.user_labels.length > 0 && <span>Label hints: {d.user_labels.join(", ")}</span>}
                  {d.user_labels?.length === 0 && <span>No label (allowed)</span>}
                  {!d.processable && d.not_processable_reason !== null && <span>Not processable: {d.not_processable_reason}</span>}
                  {d.retryable && <span>Retryable from its last run</span>}
                  {d.over_page_cap && effective.has(d.document_id) && (
                    <span className={styles.range} role="group" aria-label={`Page range for ${d.original_filename}`}>
                      Over {PAGE_CAP} pages: pages
                      <input
                        aria-label={`First page of ${d.original_filename}`}
                        inputMode="numeric"
                        value={r?.start ?? ""}
                        onChange={(e) => setRanges({ ...ranges, [d.document_id]: { start: e.target.value, end: r?.end ?? "" } })}
                      />
                      to
                      <input
                        aria-label={`Last page of ${d.original_filename}`}
                        inputMode="numeric"
                        value={r?.end ?? ""}
                        onChange={(e) => setRanges({ ...ranges, [d.document_id]: { start: r?.start ?? "", end: e.target.value } })}
                      />
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
          {rangeError !== null && (
            <Callout tone="danger" role="alert">
              <p>{rangeError}</p>
            </Callout>
          )}
          <div className={styles.actions}>
            <Button disabled={effective.size === 0 || action.busy !== null} loading={action.busy === "estimate"} onClick={() => void onEstimate()}>
              Request estimate for {effective.size} document(s)
            </Button>
            <span className={styles.note}>An estimate is free and spends nothing; runs are limited to {PAGE_CAP} pages per document.</span>
          </div>
          {action.error !== null && <ActionError what="The estimate" error={action.error} />}
        </fieldset>
      )}

      <Title order={6} id="pl-runs">
        Runs
      </Title>
      {runs.state.kind === "loading" && <LoadingState label="Loading runs…" status />}
      {runs.state.kind === "error" && (
        <ErrorState
          message={`Runs could not be loaded: ${runs.state.error.message}`}
          requestId={runs.state.error.requestId}
          onRetry={runs.reload}
          retryLabel="Retry loading runs"
        />
      )}
      {runs.state.kind === "ready" && runItems.length === 0 && (
        <EmptyState title="No processing runs yet">
          <p>Request an estimate above to create the first run. Nothing has been processed.</p>
        </EmptyState>
      )}
      {runItems.length > 0 && (
        <ul className={styles.list} aria-label="Processing runs, newest first">
          {[...runItems]
            .sort((a, b) => b.created_at.localeCompare(a.created_at))
            .map((r) => (
              <li key={r.run_id} className={styles.row}>
                <Chip spec={RUN_STATUS[r.status].spec} label={RUN_STATUS[r.status].label} />
                <span>
                  {r.processed_count} of {r.document_count} document(s) processed; estimated {usd(r.estimated_usd)}, actual {usd(r.actual_usd)}
                  {r.provider === "stub" ? " (stub provider)" : ""}
                </span>
                <Button
                  size="compact-sm"
                  variant={shownRun === r.run_id ? "light" : "default"}
                  aria-pressed={shownRun === r.run_id}
                  onClick={() => setViewRun(r.run_id)}
                >
                  Show run {r.run_id.slice(0, 8)}
                </Button>
              </li>
            ))}
        </ul>
      )}
      {shownRun !== null && (
        <RunDetail
          key={shownRun}
          projectId={projectId}
          runId={shownRun}
          onOpen={(id) => {
            setViewRun(id);
            runs.reload();
          }}
          onChanged={() => {
            runs.reload();
            docs.reload();
            onChanged();
          }}
        />
      )}
      <div className={styles.actions}>
        <Button size="xs" variant="default" leftSection={<RefreshCw size={14} aria-hidden="true" />} onClick={refresh}>
          Refresh processing state
        </Button>
      </div>
    </section>
  );
}
