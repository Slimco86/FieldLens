import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Modal, TextInput } from "@mantine/core";
import { Trash2 } from "lucide-react";
import { ApiError } from "../../api/client";
import { Callout, ErrorState, KeyValue, KeyValueList, LoadingState } from "../../design";
import { getDeletionPreview, getProject, requestProjectDeletion } from "./api";
import { keyString, type Project } from "./keys";
import { toFailure, useScopedResource, type Failure } from "./scope";
import styles from "./DeleteProjectDialog.module.css";

export const DELETE_POLL_MS = 800;

interface Props {
  /** Snapshot of the project when the dialog opened (its name is the confirmation text). */
  project: Pick<Project, "project_id" | "name" | "deletion_state" | "deletion_error">;
  onClose: () => void;
  /** The deletion request was accepted or its state changed (lists should re-read). */
  onStateChange: () => void;
  /** The project no longer exists (poll answered 404). */
  onDeleted: (projectId: string) => void;
}

type Phase =
  | { kind: "confirm" }
  | { kind: "deleting" }
  | { kind: "failed"; error: string };

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let unit = -1;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]} (${bytes.toLocaleString("en-US")} bytes)`;
}

const COUNTS = [
  ["documents", "Documents"],
  ["source_revisions", "Source revisions"],
  ["wells", "Wells"],
  ["wellbores", "Wellbores"],
  ["extracted_records", "Extracted records"],
  ["evidence_chunks", "Evidence chunks"],
  ["processing_runs", "Processing runs"],
  ["reconstruction_runs", "Reconstruction runs"],
  ["agent_work_units", "Agent work units"],
] as const;

function initialPhase(project: Props["project"]): Phase {
  if (project.deletion_state === "deleting") return { kind: "deleting" };
  if (project.deletion_state === "failed") {
    return { kind: "failed", error: project.deletion_error ?? "The deletion failed." };
  }
  return { kind: "confirm" };
}

/** Typed-name confirmation, progress and retry for irreversible project deletion (TASK-071 AC-9). */
export function DeleteProjectDialog({ project, onClose, onStateChange, onDeleted }: Props) {
  const { project_id: projectId, name } = project;
  const [phase, setPhase] = useState<Phase>(() => initialPhase(project));
  const [typed, setTyped] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<Failure | null>(null);
  const [mismatch, setMismatch] = useState(false);
  const [pollNote, setPollNote] = useState<string | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  const submitCtl = useRef<AbortController | null>(null);
  const callbacks = useRef({ onStateChange, onDeleted });
  useEffect(() => {
    callbacks.current = { onStateChange, onDeleted };
  });
  useEffect(() => () => submitCtl.current?.abort(), []);

  const preview = useScopedResource(
    phase.kind === "confirm" ? keyString(["projects", "deletion-preview", projectId]) : null,
    (signal) => getDeletionPreview(projectId, signal),
  );

  // While deleting: poll the project. 404 = purge complete; failed = show the error.
  const deleting = phase.kind === "deleting";
  useEffect(() => {
    if (!deleting) return;
    const ctl = new AbortController();
    let timer: number | undefined;
    const tick = () => {
      getProject(projectId, ctl.signal).then(
        (p) => {
          if (ctl.signal.aborted) return;
          if (p.deletion_state === "failed") {
            setPollNote(null);
            setPhase({ kind: "failed", error: p.deletion_error ?? "The deletion failed." });
            callbacks.current.onStateChange();
          } else if (p.deletion_state === "none") {
            setPollNote(null);
            setPhase({ kind: "failed", error: "The project is no longer being deleted, but it still exists." });
            callbacks.current.onStateChange();
          } else {
            setPollNote(null);
            timer = window.setTimeout(tick, DELETE_POLL_MS);
          }
        },
        (err: unknown) => {
          if (ctl.signal.aborted) return;
          if (err instanceof ApiError && err.status === 404) {
            callbacks.current.onDeleted(projectId);
            return;
          }
          setPollNote(`Deletion status could not be read (${toFailure(err).message}). Trying again…`);
          timer = window.setTimeout(tick, DELETE_POLL_MS);
        },
      );
    };
    timer = window.setTimeout(tick, DELETE_POLL_MS);
    return () => {
      ctl.abort();
      window.clearTimeout(timer);
    };
  }, [deleting, projectId]);

  const matches = typed === name;

  async function submit(confirmName: string) {
    submitCtl.current?.abort();
    const ctl = new AbortController();
    submitCtl.current = ctl;
    setSubmitting(true);
    setFormError(null);
    setMismatch(false);
    try {
      await requestProjectDeletion(projectId, confirmName, ctl.signal);
      if (ctl.signal.aborted) return;
      setPhase({ kind: "deleting" });
      callbacks.current.onStateChange();
    } catch (err) {
      if (ctl.signal.aborted) return;
      if (err instanceof ApiError && err.status === 422 && err.details?.reason === "confirm_name_mismatch") {
        setMismatch(true);
        setPhase({ kind: "confirm" });
      } else {
        setFormError(toFailure(err));
      }
    } finally {
      if (!ctl.signal.aborted) setSubmitting(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (phase.kind === "confirm" && matches && !submitting) void submit(typed);
  }

  const title = `Delete project “${name}”`;
  return (
    <Modal.Root
      opened
      onClose={onClose}
      size="lg"
      transitionProps={{ duration: 0 }}
      trapFocus
      returnFocus
      closeOnEscape
      closeOnClickOutside
      aria-labelledby="delete-project-title"
      aria-describedby="delete-project-warning"
    >
      <Modal.Overlay />
      <Modal.Content>
        <div className={styles.head}>
          <Modal.Title id="delete-project-title">{title}</Modal.Title>
          <Modal.CloseButton aria-label="Close delete dialog" />
        </div>
        <Modal.Body>
          <div className={styles.stack}>
            <Callout tone="danger">
              <p id="delete-project-warning">
                <strong>This cannot be undone.</strong> Deleting this project permanently removes its source files, extracted
                data and results. Running work is cancelled first. The spend ledger is kept.
              </p>
            </Callout>

            {phase.kind === "confirm" && (
              <>
                {preview.state.kind === "loading" && <LoadingState label="Counting what will be deleted…" />}
                {preview.state.kind === "error" && (
                  <ErrorState
                    message={`The deletion preview could not be loaded: ${preview.state.error.message}`}
                    requestId={preview.state.error.requestId}
                    onRetry={preview.reload}
                    retryLabel="Retry preview"
                  />
                )}
                {preview.state.kind === "ready" && (
                  <section aria-label="What will be deleted">
                    <KeyValueList>
                      {COUNTS.map(([key, label]) => (
                        <KeyValue key={key} term={label}>
                          {preview.state.kind === "ready" ? preview.state.data[key].toLocaleString("en-US") : ""}
                        </KeyValue>
                      ))}
                      <KeyValue term="Stored files size">{formatBytes(preview.state.data.stored_bytes)}</KeyValue>
                      <KeyValue term="Active jobs to cancel">{preview.state.data.active_jobs.toLocaleString("en-US")}</KeyValue>
                    </KeyValueList>
                  </section>
                )}
                <form onSubmit={onSubmit} className={styles.stack} noValidate>
                  <TextInput
                    ref={input}
                    label={`Type the project name “${name}” to confirm`}
                    description="The name must match exactly, including capitalization and spaces."
                    value={typed}
                    onChange={(e) => {
                      setTyped(e.currentTarget.value);
                      setMismatch(false);
                    }}
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={120}
                    error={mismatch ? "The server did not accept this name. Check it matches the project name exactly." : undefined}
                    data-autofocus
                  />
                  {formError !== null && (
                    <Callout tone="danger" role="alert">
                      <p>Deletion was not started: {formError.message}</p>
                      {formError.requestId !== null && <p>Request ID: {formError.requestId}</p>}
                    </Callout>
                  )}
                  <div className={styles.actions}>
                    <Button type="button" variant="default" onClick={onClose}>
                      Cancel
                    </Button>
                    <Button
                      type="submit"
                      color="red"
                      leftSection={<Trash2 size={14} aria-hidden="true" />}
                      disabled={!matches || submitting}
                      loading={submitting}
                    >
                      Delete project
                    </Button>
                  </div>
                </form>
              </>
            )}

            {phase.kind === "deleting" && (
              <div role="status" aria-live="polite" className={styles.progress}>
                <LoadingState label="Deleting… cancelling work and removing files. This can take a while." />
                <p>
                  Closing this dialog does not stop the deletion. It keeps running; the project shows “Deleting…” in the
                  sidebar, where “Deletion status” reopens this view.
                </p>
                {pollNote !== null && <p>{pollNote}</p>}
                <div className={styles.actions}>
                  <Button type="button" variant="default" onClick={onClose}>
                    Continue in background
                  </Button>
                </div>
              </div>
            )}

            {phase.kind === "failed" && (
              <>
                <Callout tone="danger" role="alert" title="Deletion failed">
                  <p>{phase.error}</p>
                  <p>The deletion did not finish. Retry to continue; already-removed files stay removed.</p>
                </Callout>
                {formError !== null && (
                  <Callout tone="danger" role="alert">
                    <p>Retry was not accepted: {formError.message}</p>
                    {formError.requestId !== null && <p>Request ID: {formError.requestId}</p>}
                  </Callout>
                )}
                <div className={styles.actions}>
                  <Button type="button" variant="default" onClick={onClose}>
                    Close
                  </Button>
                  <Button type="button" color="red" loading={submitting} disabled={submitting} onClick={() => void submit(name)}>
                    Retry deletion
                  </Button>
                </div>
              </>
            )}
          </div>
        </Modal.Body>
      </Modal.Content>
    </Modal.Root>
  );
}
