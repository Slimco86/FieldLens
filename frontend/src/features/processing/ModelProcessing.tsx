import { useEffect, useRef, useState } from "react";
import { Button, TextInput, Title } from "@mantine/core";
import { Ban, CircleCheck, CircleX, Clock, LoaderCircle, TriangleAlert } from "lucide-react";
import { Callout, Chip, ErrorState, LoadingState } from "../../design";
import { toFailure, type Failure } from "../projects/scope";
import { usePolled } from "../uploads/usePolled";
import type { SourceDocumentItem } from "../uploads/api";
import {
  FAILURE_LABEL,
  FAILURE_TEXT,
  NO_NATIVE_PARSER_TEXT,
  confirmProcessingRun,
  getProcessingRun,
  listProcessingDocuments,
  requestProcessingEstimate,
  retryProcessingRun,
  type DocumentProcessingState,
  type ProcessingRun,
} from "./api";
import { ModelRead } from "./ModelRead";
import { ProcessEstimateDialog } from "./ProcessEstimateDialog";
import styles from "./Processing.module.css";

const STATUS_CHIP: Record<DocumentProcessingState["processing_status"], { spec: Parameters<typeof Chip>[0]["spec"]; label: string }> = {
  not_started: { spec: { tone: "neutral", icon: Clock }, label: "Not started" },
  queued: { spec: { tone: "info", icon: Clock }, label: "Queued" },
  running: { spec: { tone: "info", icon: LoaderCircle, spin: true }, label: "Running" },
  processed: { spec: { tone: "success", icon: CircleCheck }, label: "Processed" },
  failed: { spec: { tone: "danger", icon: CircleX }, label: "Failed" },
  cancelled: { spec: { tone: "neutral", icon: Ban }, label: "Cancelled" },
  interrupted: { spec: { tone: "warning", icon: TriangleAlert }, label: "Interrupted" },
};
const ACTIVE = new Set(["queued", "running"]);
const NOT_PROCESSABLE: Record<string, string> = {
  not_a_pdf: "only PDF files can be read by the model",
  not_stored: "the file is not stored and verified yet",
  unreadable_pdf: "the PDF could not be read",
  empty_pdf: "the PDF has no pages",
};

const MAX_RANGE = 500;

function parsePages(first: string, last: string, pageCount: number | null): { ok: true; value: { page_start: number; page_end: number } } | { ok: false; message: string } {
  const a = Number(first);
  const b = Number(last);
  if (!Number.isInteger(a) || !Number.isInteger(b) || a < 1 || b < a) return { ok: false, message: "Enter whole page numbers, first page at least 1 and last page not before it." };
  if (pageCount !== null && b > pageCount) return { ok: false, message: `The document has ${pageCount} pages.` };
  if (b - a + 1 > MAX_RANGE) return { ok: false, message: `Choose at most ${MAX_RANGE} pages.` };
  return { ok: true, value: { page_start: a, page_end: b } };
}

/**
 * Model processing of one document in the Sources evidence panel: state, the existing estimate -> confirm
 * flow (never a silent spend), per-document failures with retry, and the model-read result (a proposal).
 */
export function ModelProcessing({ projectId, doc }: { projectId: string; doc: SourceDocumentItem }) {
  const docs = usePolled(
    `procdocs/${projectId}`,
    (signal) => listProcessingDocuments(projectId, signal),
    (l) => l.items.some((i) => ACTIVE.has(i.processing_status)),
    // the native parse can settle after this panel opened: re-read when the row's extraction state changes
    doc.extraction_state ?? "",
  );
  const item = docs.state.kind === "ready" ? docs.state.data.items.find((i) => i.document_id === doc.document_id) : undefined;
  const runId = item?.last_run_id ?? null;
  const run = usePolled(
    runId === null ? null : `procrun/${projectId}/${runId}`,
    (signal) => getProcessingRun(projectId, runId ?? "", signal),
    (r) => r.status === "queued" || r.status === "running",
    item?.processing_status ?? "",
  );

  const [estimate, setEstimate] = useState<ProcessingRun | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [actionFailure, setActionFailure] = useState<Failure | null>(null);
  const [dialogFailure, setDialogFailure] = useState<Failure | null>(null);
  const [first, setFirst] = useState("1");
  const [last, setLast] = useState("5");
  const [rangeError, setRangeError] = useState<string | null>(null);
  const ctl = useRef<AbortController | null>(null);
  const statusRef = useRef<HTMLParagraphElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [focusStatus, setFocusStatus] = useState(false);

  useEffect(() => () => ctl.current?.abort(), []);
  useEffect(() => {
    if (focusStatus && statusRef.current !== null) {
      statusRef.current.focus();
      setFocusStatus(false);
    }
  }, [focusStatus, item?.processing_status]);

  if (docs.state.kind === "loading") return <LoadingState label="Loading model processing state…" status />;
  if (docs.state.kind === "error") {
    return (
      <ErrorState
        message={`Model processing state could not be loaded: ${docs.state.error.message}`}
        requestId={docs.state.error.requestId}
        onRetry={docs.reload}
        retryLabel="Retry loading model processing state"
      />
    );
  }
  if (item === undefined) return null;
  const read = item.model_read ?? null;
  if (!item.no_native_parser && item.processing_status === "not_started" && read === null) return null;

  const runData = run.state.kind === "ready" ? run.state.data : null;
  const runDoc = runData?.documents.find((d) => d.document_id === doc.document_id);
  const failureCode = runDoc?.failure_code ?? runData?.error_code ?? null;
  const chip = STATUS_CHIP[item.processing_status];
  const failedLike = ["failed", "cancelled", "interrupted"].includes(item.processing_status);
  const reason = item.not_processable_reason === null ? null : (NOT_PROCESSABLE[item.not_processable_reason] ?? item.not_processable_reason);

  const headline = !item.processable && item.not_processable_reason !== null
    ? `${item.no_native_parser ? "No native parser. " : ""}Model processing is not possible: ${reason}.`
    : item.processing_status === "not_started" && item.no_native_parser
      ? NO_NATIVE_PARSER_TEXT
      : item.state_text.charAt(0).toUpperCase() + item.state_text.slice(1);

  async function request(retry: boolean) {
    if (requesting || item === undefined) return;
    let pages = null;
    if (item.over_page_cap && !retry) {
      const p = parsePages(first, last, item.page_count);
      if (!p.ok) {
        setRangeError(p.message);
        return;
      }
      pages = p.value;
    }
    setRangeError(null);
    setActionFailure(null);
    setDialogFailure(null);
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setRequesting(true);
    try {
      const res = retry && item.last_run_id !== null ? await retryProcessingRun(projectId, item.last_run_id, c.signal) : await requestProcessingEstimate(projectId, doc.document_id, pages, c.signal);
      if (!c.signal.aborted) setEstimate(res);
    } catch (err) {
      if (!c.signal.aborted) setActionFailure(toFailure(err));
    } finally {
      if (!c.signal.aborted) setRequesting(false);
    }
  }

  async function confirm() {
    if (estimate === null || confirming) return;
    const c = new AbortController();
    ctl.current = c;
    setConfirming(true);
    setDialogFailure(null);
    try {
      await confirmProcessingRun(projectId, estimate.run_id, estimate.estimate.estimated_usd, c.signal);
      if (c.signal.aborted) return;
      setEstimate(null);
      setFocusStatus(true);
      docs.reload();
    } catch (err) {
      if (!c.signal.aborted) setDialogFailure(toFailure(err));
    } finally {
      if (!c.signal.aborted) setConfirming(false);
    }
  }

  const canProcess = item.processable && item.processing_status === "not_started";
  const canRetry = item.processable && failedLike && item.retryable && item.last_run_id !== null;

  return (
    <section className={styles.section} aria-label={`Model processing for ${doc.original_filename}`}>
      <Title order={6}>Model processing</Title>
      <div className={styles.row}>
        <Chip spec={chip.spec} label={chip.label} />
        <p role="status" tabIndex={-1} ref={statusRef} className={styles.status}>
          {headline}
        </p>
      </div>
      {docs.state.refreshError !== null && (
        <Callout tone="warning" role="status">
          <p>The latest refresh failed ({docs.state.refreshError.message}); this may be out of date.</p>
        </Callout>
      )}
      {item.processing_status === "processed" && read === null && (
        <p className={styles.muted}>This run stored no model-read result for this document.</p>
      )}
      {runDoc?.cache_hit === true && read === null && <p>Reused stored result, no model call.</p>}
      {failedLike && (runId === null || run.state.kind !== "loading") && (
        <Callout tone={item.processing_status === "failed" ? "danger" : "warning"} role="alert">
          <p>
            <strong>{failureCode !== null ? FAILURE_LABEL[failureCode] : chip.label}.</strong>{" "}
            {failureCode !== null ? FAILURE_TEXT[failureCode] : "The run did not finish."}
            {failureCode !== null && <> (<code>{failureCode}</code>)</>}
          </p>
          {runDoc?.failure_message != null && <p>{runDoc.failure_message}</p>}
          <p>{canRetry ? "This is retryable. A retry makes a new estimate that you confirm separately." : "No retry is offered for this failure."}</p>
        </Callout>
      )}
      {run.state.kind === "error" && runId !== null && (
        <Callout tone="warning" role="status">
          <p>The run details could not be loaded: {run.state.error.message}</p>
        </Callout>
      )}
      {read !== null && <ModelRead read={read} userLabels={item.user_labels ?? []} cacheHit={runDoc?.cache_hit === true} />}
      {item.over_page_cap && canProcess && (
        <div className={styles.pages}>
          <TextInput label="First page" value={first} onChange={(e) => setFirst(e.currentTarget.value)} inputMode="numeric" w={110} />
          <TextInput label="Last page" value={last} onChange={(e) => setLast(e.currentTarget.value)} inputMode="numeric" w={110} />
          <span className={styles.muted}>This document has {item.page_count} pages; choose the range to read (at most {MAX_RANGE}).</span>
        </div>
      )}
      {rangeError !== null && (
        <Callout tone="danger" role="alert">
          <p>{rangeError}</p>
        </Callout>
      )}
      {actionFailure !== null && (
        <Callout tone="danger" role="alert">
          <p>
            The estimate could not be created: {actionFailure.message}
            {actionFailure.code !== null && <> (<code>{actionFailure.code}</code>)</>}. Nothing was spent.
          </p>
          {actionFailure.requestId !== null && <p>Request ID: {actionFailure.requestId}</p>}
        </Callout>
      )}
      {(canProcess || canRetry) && (
        <div>
          <Button
            variant="default"
            size="xs"
            aria-label={`${canRetry ? "Retry model processing" : "Process with model"}: ${doc.original_filename}`}
            ref={triggerRef}
            aria-busy={requesting}
            onClick={() => void request(canRetry)}
          >
            {requesting ? "Requesting estimate…" : canRetry ? "Retry with a new estimate" : "Process with model…"}
          </Button>
        </div>
      )}
      {estimate !== null && (
        <ProcessEstimateDialog
          run={estimate}
          filename={doc.original_filename}
          confirming={confirming}
          failure={dialogFailure}
          onConfirm={() => void confirm()}
          onClose={() => {
            setEstimate(null);
            setDialogFailure(null);
            const el = triggerRef.current;
            if (el !== null) window.setTimeout(() => el.isConnected && el.focus(), 0);
          }}
        />
      )}
    </section>
  );
}
