import { useRef, useState, type ReactNode } from "react";
import { Button, Title } from "@mantine/core";
import { Callout, ErrorState, KeyValue, KeyValueList, LoadingState, StatusChip } from "../../design";
import {
  getExtraction,
  listExtractedRecords,
  requeueExtraction,
  describeStorageError,
  type EvidenceLink,
  type ExtractedRecord,
  type ExtractedRecordPage,
  type ExtractionReport,
  type SourceDocumentItem,
} from "./api";
import { CandidateList } from "./CandidateList";
import { ModelProcessing } from "../processing/ModelProcessing";
import { usePolled } from "./usePolled";
import { toFailure, type Failure } from "../projects/scope";
import styles from "./shared.module.css";

const STATUS_LABEL: Record<NonNullable<ExtractionReport["status"]>, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  partial: "Partial (not all content was extracted)",
  failed: "Failed (nothing is trusted)",
  interrupted: "Interrupted (will be retried; not a result)",
  unsupported: "No native parser (no profile matches the content)",
};
const ACTIVE = new Set(["queued", "running", "interrupted"]);

/** Human-readable evidence locator, e.g. "xlsx Daily Production Data!F2" or "pdf page 3". */
export function describeLocator(link: EvidenceLink): string {
  const loc = link.locator;
  switch (loc.kind) {
    case "xml":
      return `xml ${loc.element_path}`;
    case "xlsx":
      return `xlsx ${loc.sheet}!${loc.cell_range}`;
    case "pdf":
      return `pdf page ${loc.page}${loc.cell_id ? ` cell ${loc.cell_id}` : ""}`;
    case "text": {
      const where = [
        loc.las_section ? `section ${loc.las_section}` : null,
        loc.line_start != null ? `line ${loc.line_start}${loc.line_end != null && loc.line_end !== loc.line_start ? `-${loc.line_end}` : ""}` : null,
        loc.column_name ? `column ${loc.column_name}` : null,
      ].filter((p): p is string => p !== null);
      return `text ${where.join(", ")}`;
    }
    default:
      return loc.kind;
  }
}

function describeValue(a: ExtractedRecord["attributes"][number]): string {
  if (a.number === null && a.text === null) return `unknown (${a.unknown_reason ?? "no value in source"})`;
  const v = a.original_text ?? String(a.number ?? a.text);
  const unit = a.unit ?? (a.unit_status === "missing" ? "unit not stated" : "");
  return `${v}${unit ? ` ${unit}` : ""}${a.reference ? ` [${a.reference}]` : ""}`;
}

/**
 * `expected` is the record count the extraction report states. The report and the record list are two
 * reads; if the list is still shorter than the report says (records not readable yet) it is re-read
 * until they agree, and the mismatch is stated instead of showing a silently empty list.
 */
function Records({ projectId, doc, expected }: { projectId: string; doc: SourceDocumentItem; expected: number }) {
  const { state } = usePolled<ExtractedRecordPage>(
    `records/${projectId}/${doc.document_id}`,
    (signal) => listExtractedRecords(projectId, doc.document_id, signal),
    (page) => page.total < expected,
  );
  const [more, setMore] = useState<ExtractedRecord[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [moreError, setMoreError] = useState<Failure | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const ctl = useRef<AbortController | null>(null);

  if (state.kind === "loading") return <LoadingState label="Loading extracted records…" status />;
  if (state.kind === "error") {
    return (
      <Callout tone="danger" role="alert">
        <p>Extracted records could not be loaded: {state.error.message}</p>
      </Callout>
    );
  }
  const page = state.data;
  const next = cursor === undefined ? (page.page.next_cursor ?? null) : cursor;
  const items = [...page.items, ...more];
  const catchingUp = page.total < expected;
  if (items.length === 0) {
    return (
      <>
        {catchingUp && (
          <Callout tone="info" role="status">
            <p>The report lists {expected} records but none are readable yet; this list refreshes automatically.</p>
          </Callout>
        )}
        <p>No records were extracted from this file.</p>
      </>
    );
  }

  async function loadMore() {
    if (next === null) return;
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const res = await listExtractedRecords(projectId, doc.document_id, c.signal, next);
      if (c.signal.aborted) return;
      setMore((m) => [...m, ...res.items]);
      setCursor(res.page.next_cursor ?? null);
    } catch (err) {
      if (!c.signal.aborted) setMoreError(toFailure(err));
    } finally {
      if (!c.signal.aborted) setLoadingMore(false);
    }
  }

  return (
    <div className={styles.stack}>
      <p className={styles.muted}>
        Showing {items.length} of {page.total} records.
      </p>
      <ul aria-label={`Extracted records for ${doc.original_filename}`} className={styles.plainList}>
        {items.map((r) => (
          <li key={r.record_id}>
            <strong>{r.kind}</strong>{" "}
            {Object.entries(r.subject)
              .filter(([, v]) => v !== null)
              .map(([k, v]) => `${k}=${v}`)
              .join(", ")}
            {r.effective_time !== null && r.effective_time !== undefined && (
              <> — effective {r.effective_time.literal} ({r.effective_time.precision})</>
            )}
            <ul className={styles.plainList}>
              {r.attributes.map((a) => (
                <li key={a.key}>
                  {a.key}: {describeValue(a)}{" "}
                  <small>
                    evidence: <code>{describeLocator(a.evidence)}</code>;{" "}
                    <StatusChip kind="validation" value={a.validation_state} label={a.validation_state} />
                  </small>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      {next !== null && (
        <div>
          <Button variant="default" size="xs" disabled={loadingMore} onClick={() => void loadMore()}>
            Load more records
          </Button>
        </div>
      )}
      {moreError !== null && (
        <Callout tone="danger" role="alert">
          <p>More records could not be loaded: {moreError.message}</p>
        </Callout>
      )}
    </div>
  );
}

/** Toggle for the source inspection of one file (aria-expanded; the details render elsewhere). */
export function EvidenceToggle({
  doc,
  open,
  onToggle,
  icon,
}: {
  doc: SourceDocumentItem;
  open: boolean;
  onToggle: () => void;
  icon?: ReactNode;
}) {
  return (
    <Button
      size="compact-sm"
      variant="default"
      leftSection={icon}
      aria-expanded={open}
      aria-label={`${open ? "Hide" : "Inspect"} extraction for ${doc.original_filename}`}
      onClick={onToggle}
    >
      {open ? "Hide" : "Inspect"}
    </Button>
  );
}

/** Source inspection: detected profile, parse status, coverage, data-quality findings, records. */
export function EvidencePanel({ projectId, doc }: { projectId: string; doc: SourceDocumentItem }) {
  const [open, setOpen] = useState(false);
  return (
    <section aria-label={`Extraction evidence for ${doc.original_filename}`} className={styles.stack}>
      <EvidenceToggle doc={doc} open={open} onToggle={() => setOpen(!open)} />
      {open && <Inspection projectId={projectId} doc={doc} />}
    </section>
  );
}

export function Inspection({ projectId, doc }: { projectId: string; doc: SourceDocumentItem }) {
  const { state, reload } = usePolled<ExtractionReport>(
    `extraction/${projectId}/${doc.document_id}`,
    (signal) => getExtraction(projectId, doc.document_id, signal),
    (r) => r.status === null || ACTIVE.has(r.status),
  );
  const [requeueError, setRequeueError] = useState<string | null>(null);
  const [requeueNote, setRequeueNote] = useState<string | null>(null);

  if (state.kind === "loading") return <LoadingState label="Loading extraction report…" status />;
  if (state.kind === "error") {
    return (
      <ErrorState
        message={`The extraction report could not be loaded: ${state.error.message}`}
        requestId={state.error.requestId}
        onRetry={reload}
        retryLabel="Retry loading extraction report"
      />
    );
  }
  const r = state.data;
  async function startExtraction() {
    setRequeueError(null);
    setRequeueNote(null);
    try {
      const res = await requeueExtraction(projectId, doc.document_id, new AbortController().signal);
      setRequeueNote(
        res.outcome === "queued" ? "Extraction was queued." : "Nothing was queued: the server found no change that would alter the outcome.",
      );
      reload();
    } catch (err) {
      setRequeueError(describeStorageError(err) ?? `Start failed: ${toFailure(err).message}`);
    }
  }
  if (r.status === null) {
    const note =
      doc.storage_state === "stored"
        ? "Stored and verified, but no extraction run is recorded for this file."
        : doc.storage_state === "failed"
          ? "Storage failed for this file, so it cannot be extracted. Use Retry in the Storage column, or re-upload the file."
          : "Storage verification has not finished for this file; extraction starts after it is stored.";
    return (
      <div className={styles.stack}>
        <ModelProcessing projectId={projectId} doc={doc} />
        <Callout tone="info">
          <p>{note}</p>
        </Callout>
        {doc.storage_state === "stored" && (
          <div>
            <Button variant="default" size="xs" onClick={() => void startExtraction()}>
              Start extraction
            </Button>
          </div>
        )}
        {requeueNote !== null && (
          <p role="status" className={styles.muted}>
            {requeueNote}
          </p>
        )}
        {requeueError !== null && (
          <Callout tone="danger" role="alert">
            <p>{requeueError}</p>
          </Callout>
        )}
      </div>
    );
  }
  const cov = r.coverage;
  async function retry() {
    setRequeueError(null);
    try {
      await requeueExtraction(projectId, doc.document_id, new AbortController().signal);
      reload();
    } catch (err) {
      setRequeueError(describeStorageError(err) ?? `Re-run failed: ${toFailure(err).message}`);
    }
  }
  const canRetry = r.stale || ["failed", "interrupted", "unsupported"].includes(r.status);
  return (
    <div className={styles.stack}>
      <ModelProcessing projectId={projectId} doc={doc} />
      <KeyValueList compact>
        <KeyValue term="Parse status">
          <StatusChip kind="extractionRun" value={r.status} label={STATUS_LABEL[r.status]} />
        </KeyValue>
        <KeyValue term="Detected profile">
          {r.profile_name !== null
            ? `${r.profile_name} v${r.profile_version ?? "?"} (${r.method ?? "method not recorded"})`
            : "none matched the file content"}
          {r.stale && " — profile changed since this run; results are stale"}
        </KeyValue>
        {cov !== null && (
          <KeyValue term="Coverage">
            {cov.inspected ?? "?"} of {cov.total ?? "?"} {cov.unit ?? "items"} inspected ({cov.status})
            {(cov.missing_ranges ?? []).length > 0 && `; missing ${(cov.missing_ranges ?? []).join(", ")}`}
          </KeyValue>
        )}
        <KeyValue term="Records">
          {Object.entries(r.record_counts ?? {})
            .map(([k, n]) => `${k}: ${n}`)
            .join(", ") || "none"}
        </KeyValue>
      </KeyValueList>
      {(r.wellbore_identities ?? []).length > 0 && (
        <>
          <Title order={6}>Wellbores in this source</Title>
          <ul aria-label="Wellbores in this source" className={styles.plainList}>
            {(r.wellbore_identities ?? []).map((w) => (
              <li key={`${w.wellbore_label}|${w.well_key ?? ""}`}>
                Wellbore {w.wellbore_label}
                {w.well_key !== null && w.well_key !== undefined ? ` (well ${w.well_key})` : " (well not identified)"}
                {" — "}
                {(w.record_kinds ?? []).join(", ")}
              </li>
            ))}
          </ul>
        </>
      )}
      {(r.coverage_notes ?? []).length > 0 && (
        <ul aria-label="Coverage notes" className={styles.plainList}>
          {(r.coverage_notes ?? []).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      {r.error !== null && (
        <Callout tone="danger" role="alert">
          <p>
            Extraction error ({r.error.code}): {r.error.message}
          </p>
          {r.error.process !== null && r.error.process !== undefined && <p>Written by process: {r.error.process}</p>}
        </Callout>
      )}
      {canRetry && (
        <div>
          <Button variant="default" size="xs" onClick={() => void retry()}>
            Re-run extraction
          </Button>
        </div>
      )}
      {requeueError !== null && (
        <Callout tone="danger" role="alert">
          <p>{requeueError}</p>
        </Callout>
      )}
      <Title order={6}>Data-quality findings</Title>
      {(r.issues ?? []).length === 0 ? (
        <p>No data-quality findings were recorded for this file.</p>
      ) : (
        <ul aria-label="Data-quality findings" className={styles.plainList}>
          {(r.issues ?? []).map((i) => (
            <li key={i.issue_id}>
              <StatusChip kind="severity" value={i.severity} label={i.severity} /> {i.code}: {i.message}
              {(i.evidence_links ?? []).length > 0 && (
                <small>
                  {" "}
                  evidence:{" "}
                  {(i.evidence_links ?? []).slice(0, 3).map((l, n) => (
                    <code key={n}>{describeLocator(l)} </code>
                  ))}
                </small>
              )}
              {(i.blocked_operations ?? []).length > 0 && (
                <small> blocks: {(i.blocked_operations ?? []).map((b) => b.replace("_", " ")).join(", ")}</small>
              )}
            </li>
          ))}
        </ul>
      )}
      <Title order={6}>Extracted records</Title>
      <Records projectId={projectId} doc={doc} expected={Object.values(r.record_counts ?? {}).reduce((a, n) => a + n, 0)} />
      <CandidateList projectId={projectId} doc={doc} describeLocator={describeLocator} />
    </div>
  );
}
