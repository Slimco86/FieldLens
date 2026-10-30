import { useId, useRef, useState } from "react";
import {
  getExtraction,
  listExtractedRecords,
  requeueExtraction,
  type EvidenceLink,
  type ExtractedRecord,
  type ExtractedRecordPage,
  type ExtractionReport,
  type SourceDocumentItem,
} from "./api";
import { usePolled } from "./usePolled";
import { toFailure, type Failure } from "../projects/scope";

const STATUS_LABEL: Record<NonNullable<ExtractionReport["status"]>, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  partial: "Partial (not all content was extracted)",
  failed: "Failed (nothing is trusted)",
  interrupted: "Interrupted (will be retried; not a result)",
  unsupported: "Unsupported (no profile matches the content)",
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

function Records({ projectId, doc }: { projectId: string; doc: SourceDocumentItem }) {
  const { state } = usePolled<ExtractedRecordPage>(
    `records/${projectId}/${doc.document_id}`,
    (signal) => listExtractedRecords(projectId, doc.document_id, signal),
    () => false,
  );
  const [more, setMore] = useState<ExtractedRecord[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [moreError, setMoreError] = useState<Failure | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const ctl = useRef<AbortController | null>(null);

  if (state.kind === "loading") return <p role="status">Loading extracted records…</p>;
  if (state.kind === "error") {
    return <p role="alert">Extracted records could not be loaded: {state.error.message}</p>;
  }
  const page = state.data;
  const next = cursor === undefined ? (page.page.next_cursor ?? null) : cursor;
  const items = [...page.items, ...more];
  if (items.length === 0) return <p>No records were extracted from this file.</p>;

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
    <div>
      <p>
        Showing {items.length} of {page.total} records.
      </p>
      <ul aria-label={`Extracted records for ${doc.original_filename}`}>
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
            <ul>
              {r.attributes.map((a) => (
                <li key={a.key}>
                  {a.key}: {describeValue(a)}{" "}
                  <small>
                    evidence: <code>{describeLocator(a.evidence)}</code>; {a.validation_state}
                  </small>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      {next !== null && (
        <button type="button" disabled={loadingMore} onClick={() => void loadMore()}>
          Load more records
        </button>
      )}
      {moreError !== null && <p role="alert">More records could not be loaded: {moreError.message}</p>}
    </div>
  );
}

/** Source inspection: detected profile, parse status, coverage, data-quality findings, records. */
export function EvidencePanel({ projectId, doc }: { projectId: string; doc: SourceDocumentItem }) {
  const heading = useId();
  const [open, setOpen] = useState(false);
  return (
    <section aria-labelledby={heading} className="evidence">
      <h6 id={heading}>Extraction evidence for {doc.original_filename}</h6>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Inspect"} extraction for {doc.original_filename}
      </button>
      {open && <Inspection projectId={projectId} doc={doc} />}
    </section>
  );
}

function Inspection({ projectId, doc }: { projectId: string; doc: SourceDocumentItem }) {
  const { state, reload } = usePolled<ExtractionReport>(
    `extraction/${projectId}/${doc.document_id}`,
    (signal) => getExtraction(projectId, doc.document_id, signal),
    (r) => r.status !== null && ACTIVE.has(r.status),
  );
  const [requeueError, setRequeueError] = useState<Failure | null>(null);

  if (state.kind === "loading") return <p role="status">Loading extraction report…</p>;
  if (state.kind === "error") {
    return (
      <div role="alert">
        <p>The extraction report could not be loaded: {state.error.message}</p>
        {state.error.requestId !== null && <p>Request ID: {state.error.requestId}</p>}
        <button type="button" onClick={reload}>
          Retry loading extraction report
        </button>
      </div>
    );
  }
  const r = state.data;
  if (r.status === null) {
    return <p>No extraction has run for this file yet; it is waiting for the extraction worker.</p>;
  }
  const cov = r.coverage;
  async function retry() {
    setRequeueError(null);
    try {
      await requeueExtraction(projectId, doc.document_id, new AbortController().signal);
      reload();
    } catch (err) {
      setRequeueError(toFailure(err));
    }
  }
  const canRetry = r.stale || ["failed", "interrupted", "unsupported"].includes(r.status);
  return (
    <div>
      <dl>
        <dt>Parse status</dt>
        <dd>{STATUS_LABEL[r.status]}</dd>
        <dt>Detected profile</dt>
        <dd>
          {r.profile_name !== null
            ? `${r.profile_name} v${r.profile_version ?? "?"} (${r.method ?? "method not recorded"})`
            : "none matched the file content"}
          {r.stale && " — profile changed since this run; results are stale"}
        </dd>
        {cov !== null && (
          <>
            <dt>Coverage</dt>
            <dd>
              {cov.inspected ?? "?"} of {cov.total ?? "?"} {cov.unit ?? "items"} inspected ({cov.status})
              {(cov.missing_ranges ?? []).length > 0 && `; missing ${(cov.missing_ranges ?? []).join(", ")}`}
            </dd>
          </>
        )}
        <dt>Records</dt>
        <dd>
          {Object.entries(r.record_counts ?? {})
            .map(([k, n]) => `${k}: ${n}`)
            .join(", ") || "none"}
        </dd>
      </dl>
      {r.error !== null && (
        <p role="alert">
          Extraction error ({r.error.code}): {r.error.message}
        </p>
      )}
      {canRetry && (
        <button type="button" onClick={() => void retry()}>
          Re-run extraction
        </button>
      )}
      {requeueError !== null && <p role="alert">Re-run failed: {requeueError.message}</p>}
      <h6>Data-quality findings</h6>
      {(r.issues ?? []).length === 0 ? (
        <p>No data-quality findings were recorded for this file.</p>
      ) : (
        <ul aria-label="Data-quality findings">
          {(r.issues ?? []).map((i) => (
            <li key={i.issue_id}>
              <strong>{i.severity}</strong> {i.code}: {i.message}
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
      <h6>Extracted records</h6>
      <Records projectId={projectId} doc={doc} />
    </div>
  );
}
