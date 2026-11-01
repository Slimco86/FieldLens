import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Table, Title } from "@mantine/core";
import { Callout, Chip, EmptyState, ErrorState, LoadingState, StatusChip } from "../../design";
import { TruncatedText, chipVocabulary } from "../../design";
import { FileUp } from "lucide-react";
import { DocumentList } from "./DocumentList";
import { JobStatus, isJobActive, jobStatusLabel } from "./JobStatus";
import { UploadForm } from "./UploadForm";
import { listRevisions, type SourceRevisionPage, type SourceRevisionSummary } from "./api";
import { formatTime } from "./format";
import { usePolled } from "./usePolled";
import styles from "./shared.module.css";

const REVISION_STATUS_LABEL: Record<SourceRevisionSummary["status"], string> = {
  staging: "Staging (import in progress, not final)",
  ready: "Ready (files stored; not extracted)",
  ready_with_issues: "Partial: ready with issues",
  failed: "Failed",
};

/** A revision is "superseded" only if another listed revision names it as parent. */
export function revisionMarker(r: SourceRevisionSummary, all: readonly SourceRevisionSummary[]): string {
  if (r.is_latest) return "(latest)";
  return all.some((o) => o.parent_source_revision_id === r.source_revision_id) ? "(superseded)" : "(not current)";
}

export function revisionStatusLabel(r: SourceRevisionSummary): string {
  if (r.status === "failed" && r.job_status === "cancelled") return "Cancelled (import stopped; nothing was extracted)";
  return REVISION_STATUS_LABEL[r.status];
}

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
    out.push(
      r.job_status === "cancelled"
        ? "This import was cancelled. Earlier revisions were not changed by it."
        : "This revision failed. Earlier revisions were not changed by it.",
    );
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

function RevisionStatus({ r }: { r: SourceRevisionSummary }) {
  const cancelled = r.status === "failed" && r.job_status === "cancelled";
  return cancelled ? (
    <Chip spec={chipVocabulary.job.cancelled} label={revisionStatusLabel(r)} />
  ) : (
    <StatusChip kind="revision" value={r.status} label={revisionStatusLabel(r)} />
  );
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
    <div className={styles.stack}>
      <UploadForm
        projectId={projectId}
        expectedParentId={latestRevisionId}
        onImported={() => {
          reload();
          onProjectChanged();
        }}
        onStale={stale}
      />
      <section aria-labelledby={`sources-heading-${projectId}`} className={styles.card}>
        <div className={styles.cardHead}>
          <Title order={5} id={`sources-heading-${projectId}`}>
            Source revisions
          </Title>
        </div>
        <p className={styles.note}>
          Statuses below are exactly what the API reports. “Stored” means the bytes were saved and hash-verified;
          nothing here has been extracted, parsed or engineering-validated.
        </p>
        {state.kind === "loading" && <LoadingState label="Loading source revisions…" status />}
        {state.kind === "error" && (
          <ErrorState
            message={`Source revisions could not be loaded: ${state.error.message}`}
            requestId={state.error.requestId}
            onRetry={reload}
            retryLabel="Retry loading source revisions"
          />
        )}
        {state.kind === "ready" && state.refreshError !== null && (
          <Callout tone="warning" role="alert">
            <p>Refreshing source revisions failed: {state.refreshError.message}</p>
          </Callout>
        )}
        {state.kind === "ready" && items.length === 0 && (
          <EmptyState title="Nothing uploaded" icon={<FileUp size={28} />}>
            <p>This project has no source files yet. Use the form above to upload the first import.</p>
          </EmptyState>
        )}
        {state.kind === "ready" && items.some(isRevisionActive) && (
          <Callout tone="info" role="status">
            <p>An import is in progress; this list refreshes automatically.</p>
          </Callout>
        )}
        {items.length > 0 && (
          // Scrollable region must be keyboard focusable so keyboard users can scroll it.
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
          <div role="region" aria-label="Source revisions table" tabIndex={0} className={styles.scroll}>
            <Table captionSide="top">
              <Table.Caption className={styles.caption}>Source revisions, newest first</Table.Caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Revision</Table.Th>
                  <Table.Th scope="col">Status</Table.Th>
                  <Table.Th scope="col">Created</Table.Th>
                  <Table.Th scope="col" className={styles.num}>Files</Table.Th>
                  <Table.Th scope="col" className={styles.num}>Stored</Table.Th>
                  <Table.Th scope="col" className={styles.num}>Quarantined</Table.Th>
                  <Table.Th scope="col" className={styles.num}>Pending extraction</Table.Th>
                  <Table.Th scope="col" className={styles.num}>Unsupported</Table.Th>
                  <Table.Th scope="col">Job</Table.Th>
                  <Table.Th scope="col">Parent revision</Table.Th>
                  <Table.Th scope="col">Manifest hash</Table.Th>
                  <Table.Th scope="col">Files view</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {items.map((r) => (
                  <Table.Tr key={r.source_revision_id} className={selected?.source_revision_id === r.source_revision_id ? styles.selected : undefined}>
                    <Table.Th scope="row">
                      <TruncatedText value={r.source_revision_id} label="revision ID" maxCh={14}>
                        <code>{r.source_revision_id}</code>
                      </TruncatedText>{" "}
                      {revisionMarker(r, items)}
                    </Table.Th>
                    <Table.Td><RevisionStatus r={r} /></Table.Td>
                    <Table.Td>{formatTime(r.created_at)}</Table.Td>
                    <Table.Td className={styles.num}>{r.member_count}</Table.Td>
                    <Table.Td className={styles.num}>{r.stored_count}</Table.Td>
                    <Table.Td className={styles.num}>{r.quarantined_count}</Table.Td>
                    <Table.Td className={styles.num}>{r.pending_extraction_count}</Table.Td>
                    <Table.Td className={styles.num}>{r.unsupported_count}</Table.Td>
                    <Table.Td>
                      {r.job_status === null || r.job_status === undefined ? (
                        "No job"
                      ) : (
                        <StatusChip kind="job" value={r.job_status} label={jobStatusLabel(r.job_status)} />
                      )}
                    </Table.Td>
                    <Table.Td>
                      {r.parent_source_revision_id === null || r.parent_source_revision_id === undefined ? (
                        "None (first revision)"
                      ) : (
                        <TruncatedText value={r.parent_source_revision_id} label="parent revision ID" maxCh={14}>
                          <code>{r.parent_source_revision_id}</code>
                        </TruncatedText>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <TruncatedText value={r.manifest_hash} label="manifest hash" maxCh={16}>
                        <code>{r.manifest_hash}</code>
                      </TruncatedText>
                    </Table.Td>
                    <Table.Td>
                      <Button
                        size="compact-sm"
                        variant={selected?.source_revision_id === r.source_revision_id ? "light" : "default"}
                        aria-pressed={selected?.source_revision_id === r.source_revision_id}
                        onClick={() => setPicked(r.source_revision_id)}
                      >
                        Show files of revision {r.source_revision_id.slice(0, 8)}
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </div>
        )}
        {state.kind === "ready" && state.data.page.next_cursor !== null && state.data.page.next_cursor !== undefined && (
          <p className={styles.note}>Only the {items.length} newest revisions are shown.</p>
        )}
        {items.some((r) => revisionWarnings(r).length > 0) && (
          <Callout tone="warning" label="Revision warnings">
            <Title order={6}>Revision warnings</Title>
            <ul className={styles.plainList}>
              {items.flatMap((r) =>
                revisionWarnings(r).map((w) => (
                  <li key={`${r.source_revision_id}:${w}`}>
                    <strong>Warning</strong> (revision {r.source_revision_id.slice(0, 8)}): {w}
                  </li>
                )),
              )}
            </ul>
          </Callout>
        )}
      </section>
      {selected !== null && (
        <section aria-label={`Files of revision ${selected.source_revision_id}`} className={styles.card}>
          <div className={styles.cardHead}>
            <Title order={5}>Files of revision {selected.source_revision_id.slice(0, 8)}</Title>
          </div>
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
