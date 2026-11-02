import { useEffect, useRef, useState } from "react";
import { Button, Title } from "@mantine/core";
import { Callout, KeyValue, KeyValueList, LoadingState, StatusChip, TruncatedText } from "../../design";
import { cancelJob, getJob, type Job } from "./api";
import { formatTime } from "./format";
import { usePolled } from "./usePolled";
import styles from "./shared.module.css";
import { toFailure, type Failure } from "../projects/scope";

const ACTIVE: ReadonlySet<string> = new Set(["queued", "running"]);
export const isJobActive = (status: string | null): boolean => status !== null && ACTIVE.has(status);

const JOB_STATUS_LABEL: Record<Job["status"], string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded (storage verification only)",
  partial: "Partial (some files failed storage verification)",
  failed: "Failed",
  cancelled: "Cancelled",
  interrupted: "Interrupted",
};
export const jobStatusLabel = (s: Job["status"]): string => JOB_STATUS_LABEL[s];

interface Props {
  projectId: string;
  jobId: string;
  /** Called when this job's status changes so the revision list can refresh. */
  onChanged: () => void;
}

/** "4 of 4 documents": the unit is pluralized unless it already is (or the count is 1). */
function progressText(processed: number, total: number | null | undefined, unit: string | null | undefined): string {
  const count = total === null || total === undefined ? `${processed}` : `${processed} of ${total}`;
  if (unit === null || unit === undefined || unit === "") return count;
  const n = total ?? processed;
  return `${count} ${n === 1 || unit.endsWith("s") ? unit : `${unit}s`}`;
}

export function JobStatus({ projectId, jobId, onChanged }: Props) {
  const { state, replace } = usePolled<Job>(
    `job/${projectId}/${jobId}`,
    (signal) => getJob(projectId, jobId, signal),
    (job) => isJobActive(job.status),
  );
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<Failure | null>(null);
  const [cancelNote, setCancelNote] = useState<string | null>(null);
  const ctl = useRef<AbortController | null>(null);
  useEffect(() => () => ctl.current?.abort(), []);

  const status = state.kind === "ready" ? state.data.status : null;
  const seen = useRef<string | null>(null);
  useEffect(() => {
    if (status === null) return;
    if (seen.current !== null && seen.current !== status) onChanged();
    seen.current = status;
  }, [status, onChanged]);

  async function onCancel() {
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setCancelling(true);
    setCancelError(null);
    setCancelNote(null);
    try {
      const job = await cancelJob(projectId, jobId, c.signal);
      if (c.signal.aborted) return;
      replace(job);
      setCancelNote("Cancellation was requested. The job stops at its next checkpoint; its status is shown above.");
      onChanged();
    } catch (err) {
      if (!c.signal.aborted) setCancelError(toFailure(err));
    } finally {
      if (!c.signal.aborted) setCancelling(false);
    }
  }

  if (state.kind === "loading") return <LoadingState label="Loading job status…" status />;
  if (state.kind === "error") {
    return (
      <Callout tone="danger" role="alert">
        <p>
          Job status could not be loaded: {state.error.message}
          {state.error.requestId !== null && <> (Request ID: {state.error.requestId})</>}
        </p>
      </Callout>
    );
  }
  const job = state.data;
  const active = isJobActive(job.status);
  // The job's own stage while it runs; once finished, the stage of its last attempt. Otherwise omitted.
  const lastAttempt = job.attempts[job.attempts.length - 1];
  const stage = job.stage ?? lastAttempt?.stage ?? null;
  return (
    <div className={`${styles.stack} ${styles.job}`}>
      <Title order={6}>Storage verification job</Title>
      <KeyValueList compact>
        <KeyValue term="Job">
          <TruncatedText value={job.job_id} label="job ID" maxCh={20}>
            <code>{job.job_id}</code>
          </TruncatedText>
        </KeyValue>
        <KeyValue term="Job status">
          <StatusChip kind="job" value={job.status} label={jobStatusLabel(job.status)} />{" "}
          <span className={styles.muted}>({job.status})</span>
          {job.cancel_requested && " — cancellation requested"}
        </KeyValue>
        {stage !== null && <KeyValue term="Stage">{stage}</KeyValue>}
        <KeyValue term="Progress">
          {job.progress.processed === null || job.progress.processed === undefined
            ? "Not reported"
            : progressText(job.progress.processed, job.progress.total, job.progress.unit)}
        </KeyValue>
        <KeyValue term="Updated">{formatTime(job.updated_at)}</KeyValue>
        {job.finished_at !== null && job.finished_at !== undefined && (
          <KeyValue term="Finished">{formatTime(job.finished_at)}</KeyValue>
        )}
      </KeyValueList>
      <Title order={6}>Attempts ({job.attempts.length}; a failed job is retried once automatically by the server)</Title>
      {job.attempts.length === 0 ? (
        <p>No attempt has started yet.</p>
      ) : (
        <ol className={styles.plainList}>
          {job.attempts.map((a) => (
            <li key={a.attempt_no}>
              Attempt {a.attempt_no}: {a.status}
              {a.stage !== null && a.stage !== undefined && <>, stage {a.stage}</>}
              {a.error_code !== null && a.error_code !== undefined && <>, error code {a.error_code}</>}; started{" "}
              {formatTime(a.started_at)}
              {a.ended_at !== null && a.ended_at !== undefined && <>, ended {formatTime(a.ended_at)}</>}
            </li>
          ))}
        </ol>
      )}
      {job.error !== null && job.error !== undefined && (
        <Callout tone="danger" role="alert">
          <p>
            Job error {job.error.code}: {job.error.message}
          </p>
        </Callout>
      )}
      {job.result !== null && job.result !== undefined && (
        <p>
          Result at job completion (the table below is live and may be newer): {job.result.documents} file(s): {job.result.stored} stored, {job.result.failed} failed,{" "}
          {job.result.pending_extraction} pending extraction, {job.result.unsupported} unsupported. Extraction performed:
          no (storage verification only).
        </p>
      )}
      {state.refreshError !== null && (
        <Callout tone="warning" role="alert">
          <p>Refreshing job status failed: {state.refreshError.message}</p>
        </Callout>
      )}
      {active && (
        <div>
          <Button variant="default" size="xs" disabled={cancelling || job.cancel_requested} onClick={() => void onCancel()}>
            Cancel import
          </Button>
        </div>
      )}
      {cancelNote !== null && (
        <Callout tone="info" role="status">
          <p>{cancelNote}</p>
        </Callout>
      )}
      {cancelError !== null && (
        <Callout tone="danger" role="alert">
          <p>Cancel failed: {cancelError.message}</p>
        </Callout>
      )}
    </div>
  );
}
