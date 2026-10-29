import { useCallback, useEffect, useRef, useState } from "react";
import { DocumentList } from "./DocumentList";
import { JobStatus, isJobActive, jobStatusLabel } from "./JobStatus";
import { UploadForm } from "./UploadForm";
import { listRevisions, type SourceRevisionPage, type SourceRevisionSummary } from "./api";
import { formatTime } from "./format";
import { usePolled } from "./usePolled";

const REVISION_STATUS_LABEL: Record<SourceRevisionSummary["status"], string> = {
  staging: "Staging (import in progress, not final)",
  ready: "Ready (files stored; not extracted)",
  ready_with_issues: "Partial: ready with issues",
  failed: "Failed",
};

export const isRevisionActive = (r: SourceRevisionSummary): boolean =>
  r.status === "staging" || isJobActive(r.job_status ?? null);

const versionOf = (r: SourceRevisionSummary): string =>
  [r.status, r.job_status, r.member_count, r.stored_count, r.quarantined_count, r.pending_extraction_count, r.unsupported_count].join(":");

export function revisionWarnings(r: SourceRevisionSummary): string[] {
  const out: string[] = [];
  if (r.status === "ready_with_issues") {
    out.push(
      `Partial revision: ${r.quarantined_count} file(s) were quarantined. A partial revision still becomes the project's latest and may have displaced a previously good version of a file.`,
    );
  } else if (r.quarantined_count > 0) {
    out.push(`${r.quarantined_count} file(s) in this revision are quarantined.`);
  }
  if (r.status === "failed") {
    out.push("This revision failed. Earlier revisions were not changed by it.");
  }
  if (r.is_latest && r.status !== "ready" && r.status !== "staging" && r.parent_source_revision_id !== null) {
    out.push(
      `This revision is the project's latest although its status is “${r.status}”. Compare it with its parent revision ${r.parent_source_revision_id} to see whether a good version was displaced.`,
    );
  }
  return out;
}

interface Props {
  projectId: string;
  /** The project's latest source revision ID from the project record (expected parent of an upload). */
  latestRevisionId: string | null;
  /** Ask the project view to re-read the project (its latest-revision pointer may have changed). */
  onProjectChanged: () => void;
}

export function SourcesPanel({ projectId, latestRevisionId, onProjectChanged }: Props) {
  const { state, reload } = usePolled<SourceRevisionPage>(
    `revisions/${projectId}`,
    (signal) => listRevisions(projectId, signal),
    (page) => page.items.some(isRevisionActive),
  );
  const [picked, setPicked] = useState<string | null>(null);

  const items = state.kind === "ready" ? state.data.items : [];
  const flaggedLatest = items.find((r) => r.is_latest)?.source_revision_id ?? null;
  // Keep the project's latest pointer (the expected parent of the next upload) in sync.
  const asked = useRef<string | null>(null);
  useEffect(() => {
    if (state.kind !== "ready" || flaggedLatest === latestRevisionId) return;
    const marker = `${flaggedLatest}>${latestRevisionId}`;
    if (asked.current === marker) return;
    asked.current = marker;
    onProjectChanged();
  }, [state.kind, flaggedLatest, latestRevisionId, onProjectChanged]);

  const selected: SourceRevisionSummary | null =
    items.find((r) => r.source_revision_id === picked) ?? items.find((r) => r.is_latest) ?? items[0] ?? null;
  const stale = useCallback(() => {
    onProjectChanged();
    reload();
  }, [onProjectChanged, reload]);

  return (
    <div>
      <UploadForm
        projectId={projectId}
        expectedParentId={latestRevisionId}
        onImported={() => {
          reload();
          onProjectChanged();
        }}
        onStale={stale}
      />
      <section aria-labelledby={`sources-heading-${projectId}`}>
        <h5 id={`sources-heading-${projectId}`}>Source revisions</h5>
        <p>
          Statuses below are exactly what the API reports. “Stored” means the bytes were saved and hash-verified;
          nothing here has been extracted, parsed or engineering-validated.
        </p>
        {state.kind === "loading" && <p role="status">Loading source revisions…</p>}
        {state.kind === "error" && (
          <div role="alert">
            <p>Source revisions could not be loaded: {state.error.message}</p>
            {state.error.requestId !== null && <p>Request ID: {state.error.requestId}</p>}
            <button type="button" onClick={reload}>
              Retry loading source revisions
            </button>
          </div>
        )}
        {state.kind === "ready" && state.refreshError !== null && (
          <p role="alert">Refreshing source revisions failed: {state.refreshError.message}</p>
        )}
        {state.kind === "ready" && items.length === 0 && (
          <p>This project has no source files yet. Use the form above to upload the first import.</p>
        )}
        {state.kind === "ready" && items.some(isRevisionActive) && (
          <p role="status">An import is in progress; this list refreshes automatically.</p>
        )}
        {items.length > 0 && (
          <table>
            <caption>Source revisions, newest first</caption>
            <thead>
              <tr>
                <th scope="col">Revision</th>
                <th scope="col">Status</th>
                <th scope="col">Created</th>
                <th scope="col">Files</th>
                <th scope="col">Stored</th>
                <th scope="col">Quarantined</th>
                <th scope="col">Pending extraction</th>
                <th scope="col">Unsupported</th>
                <th scope="col">Job</th>
                <th scope="col">Parent revision</th>
                <th scope="col">Manifest hash</th>
                <th scope="col">Files view</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.source_revision_id}>
                  <th scope="row">
                    <code>{r.source_revision_id}</code> {r.is_latest ? "(latest)" : "(superseded)"}
                  </th>
                  <td>{REVISION_STATUS_LABEL[r.status]}</td>
                  <td>{formatTime(r.created_at)}</td>
                  <td>{r.member_count}</td>
                  <td>{r.stored_count}</td>
                  <td>{r.quarantined_count}</td>
                  <td>{r.pending_extraction_count}</td>
                  <td>{r.unsupported_count}</td>
                  <td>{r.job_status === null || r.job_status === undefined ? "No job" : jobStatusLabel(r.job_status)}</td>
                  <td>
                    {r.parent_source_revision_id === null || r.parent_source_revision_id === undefined ? (
                      "None (first revision)"
                    ) : (
                      <code>{r.parent_source_revision_id}</code>
                    )}
                  </td>
                  <td>
                    <code>{r.manifest_hash}</code>
                  </td>
                  <td>
                    <button
                      type="button"
                      aria-pressed={selected?.source_revision_id === r.source_revision_id}
                      onClick={() => setPicked(r.source_revision_id)}
                    >
                      Show files of revision {r.source_revision_id.slice(0, 8)}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {state.kind === "ready" && state.data.page.next_cursor !== null && state.data.page.next_cursor !== undefined && (
          <p>Only the {items.length} newest revisions are shown.</p>
        )}
        {items.some((r) => revisionWarnings(r).length > 0) && (
          <div aria-label="Revision warnings" className="warnings">
            <h6>Revision warnings</h6>
            <ul>
              {items.flatMap((r) =>
                revisionWarnings(r).map((w) => (
                  <li key={`${r.source_revision_id}:${w}`}>
                    <strong>Warning</strong> (revision {r.source_revision_id.slice(0, 8)}): {w}
                  </li>
                )),
              )}
            </ul>
          </div>
        )}
      </section>
      {selected !== null && (
        <section aria-label={`Files of revision ${selected.source_revision_id}`}>
          <h5>Files of revision {selected.source_revision_id.slice(0, 8)}</h5>
          {selected.job_id !== null && selected.job_id !== undefined && (
            <JobStatus projectId={projectId} jobId={selected.job_id} onChanged={reload} />
          )}
          <DocumentList
            key={selected.source_revision_id}
            projectId={projectId}
            revisionId={selected.source_revision_id}
            version={versionOf(selected)}
            polling={isRevisionActive(selected)}
          />
        </section>
      )}
    </div>
  );
}
