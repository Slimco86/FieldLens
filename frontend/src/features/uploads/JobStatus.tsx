import { useEffect, useRef, useState } from "react";
import { cancelJob, getJob, type Job } from "./api";
import { formatTime } from "./format";
import { usePolled } from "./usePolled";
import { toFailure, type Failure } from "../projects/scope";

const ACTIVE: ReadonlySet<string> = new Set(["queued", "running"]);
export const isJobActive = (status: string | null): boolean => status !== null && ACTIVE.has(status);

const JOB_STATUS_LABEL: Record<Job["status"], string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded (storage verification only)",
  partial: "Partial (some files quarantined)",
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

  if (state.kind === "loading") return <p role="status">Loading job status…</p>;
  if (state.kind === "error") {
    return (
      <p role="alert">
        Job status could not be loaded: {state.error.message}
        {state.error.requestId !== null && <> (Request ID: {state.error.requestId})</>}
      </p>
    );
  }
  const job = state.data;
  const active = isJobActive(job.status);
  return (
    <div className="job">
      <h6>Storage verification job</h6>
      <dl>
        <dt>Job</dt>
        <dd>{job.job_id}</dd>
        <dt>Job status</dt>
        <dd>
          {jobStatusLabel(job.status)} ({job.status}){job.cancel_requested && " — cancellation requested"}
        </dd>
        <dt>Stage</dt>
        <dd>{job.stage ?? "Not reported"}</dd>
        <dt>Progress</dt>
        <dd>
          {job.progress.processed === null || job.progress.processed === undefined
            ? "Not reported"
            : `${job.progress.processed}${job.progress.total === null || job.progress.total === undefined ? "" : ` of ${job.progress.total}`} ${job.progress.unit ?? ""}`.trim()}
        </dd>
        <dt>Updated</dt>
        <dd>{formatTime(job.updated_at)}</dd>
        {job.finished_at !== null && job.finished_at !== undefined && (
          <>
            <dt>Finished</dt>
            <dd>{formatTime(job.finished_at)}</dd>
          </>
        )}
      </dl>
      <h6>Attempts ({job.attempts.length}; a failed job is retried once automatically by the server)</h6>
      {job.attempts.length === 0 ? (
        <p>No attempt has started yet.</p>
      ) : (
        <ol>
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
        <p role="alert">
          Job error {job.error.code}: {job.error.message}
        </p>
      )}
      {job.result !== null && job.result !== undefined && (
        <p>
          Result: {job.result.documents} file(s): {job.result.stored} stored, {job.result.quarantined} quarantined,{" "}
          {job.result.pending_extraction} pending extraction, {job.result.unsupported} unsupported. Extraction performed:
          no (storage verification only).
        </p>
      )}
      {state.refreshError !== null && <p role="alert">Refreshing job status failed: {state.refreshError.message}</p>}
      {active && (
        <p>
          <button type="button" disabled={cancelling || job.cancel_requested} onClick={() => void onCancel()}>
            Cancel import
          </button>
        </p>
      )}
      {cancelNote !== null && <p role="status">{cancelNote}</p>}
      {cancelError !== null && <p role="alert">Cancel failed: {cancelError.message}</p>}
    </div>
  );
}
