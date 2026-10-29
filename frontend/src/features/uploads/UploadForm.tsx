import { useEffect, useId, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import {
  CATEGORIES,
  MAX_BATCH_BYTES,
  MAX_FILES,
  MAX_FILE_BYTES,
  NetworkUploadError,
  UploadAbortedError,
  uploadImport,
  type DocumentCategory,
  type ImportAccepted,
  type ImportMetadata,
  type UploadProgress,
} from "./api";
import { categoryLabel, formatBytes } from "./format";

interface Entry {
  id: number;
  file: File;
  category: DocumentCategory | "";
}

interface FailureView {
  message: string;
  requestId: string | null;
  detail: string | null;
}

type Phase =
  | { kind: "idle" }
  | { kind: "uploading"; progress: UploadProgress | null }
  | { kind: "done"; httpStatus: number; accepted: ImportAccepted }
  | ({ kind: "failed" } & FailureView);

interface Props {
  projectId: string;
  /** The project's latest source revision (null for a first import); sent as the expected parent. */
  expectedParentId: string | null;
  onImported: (accepted: ImportAccepted) => void;
  /** The server says our parent revision is stale: the caller should refresh project state. */
  onStale: () => void;
}

export function newIdempotencyKey(): string {
  const c: Crypto | undefined = typeof crypto === "undefined" ? undefined : crypto;
  if (c !== undefined && typeof c.randomUUID === "function") return c.randomUUID();
  return `fl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Client-side mirror of the server limits. The server stays authoritative. */
export function validateSelection(files: readonly File[]): string[] {
  const problems: string[] = [];
  if (files.length > MAX_FILES) {
    problems.push(`Too many files: ${files.length} selected, at most ${MAX_FILES} are allowed per import.`);
  }
  for (const f of files) {
    if (f.size > MAX_FILE_BYTES) {
      problems.push(`“${f.name}” is ${formatBytes(f.size)}; the limit is ${formatBytes(MAX_FILE_BYTES)} per file.`);
    }
  }
  const total = files.reduce((sum, f) => sum + f.size, 0);
  if (total > MAX_BATCH_BYTES) {
    problems.push(`The selection totals ${formatBytes(total)}; the limit is ${formatBytes(MAX_BATCH_BYTES)} per import.`);
  }
  return problems;
}

function reasonOf(err: ApiError): string | null {
  const reason = err.details?.["reason"];
  return typeof reason === "string" ? reason : null;
}

const RETRY_SAFE = "Submitting the same selection again is safe: it reuses the same idempotency key.";

export function describeUploadFailure(err: unknown): FailureView {
  if (err instanceof UploadAbortedError) {
    return {
      message: err.fullySent
        ? `Upload aborted after all bytes were sent. The server may still have accepted it; check the source list. ${RETRY_SAFE}`
        : "Upload aborted. The server discards an incomplete upload, so nothing was imported.",
      requestId: null,
      detail: null,
    };
  }
  if (err instanceof NetworkUploadError) {
    return {
      message: `${err.message} The import may or may not have been received; check the source list. ${RETRY_SAFE}`,
      requestId: null,
      detail: null,
    };
  }
  if (err instanceof ApiError) {
    const reason = reasonOf(err);
    const detail = reason === null ? null : `Reason: ${reason}`;
    const requestId = err.requestId;
    switch (err.status) {
      case 409:
        if (reason === "import_in_progress") {
          return {
            message:
              "Another import is still being processed for this project. Wait for it to finish, or cancel it, then upload again.",
            requestId,
            detail,
          };
        }
        if (reason === "stale_parent") {
          return {
            message: "The project's source revision changed since this page loaded. The view was refreshed; submit again.",
            requestId,
            detail,
          };
        }
        return { message: `Conflict: ${err.message}`, requestId, detail };
      case 413:
        return { message: `The server rejected the upload as too large: ${err.message}`, requestId, detail };
      case 415:
        return {
          message: `The server rejected an unsupported file type (for example a binary or executable): ${err.message} Remove it and try again.`,
          requestId,
          detail,
        };
      default:
        if (err.code === "client_disconnected") {
          return { message: "The server reports the upload was interrupted. Nothing was imported.", requestId, detail };
        }
        if (err.code === "SESSION_TOKEN_INVALID") {
          return { message: "Your local session was refreshed. Nothing was imported; submit again.", requestId, detail };
        }
        return { message: err.message, requestId, detail };
    }
  }
  return { message: "The upload failed for an unknown reason.", requestId: null, detail: null };
}

function successText(httpStatus: number, a: ImportAccepted): string {
  if (a.replayed) {
    return "This identical request was already accepted earlier (replay). No duplicate records were created.";
  }
  if (a.deduplicated) {
    return "Every file already belongs to the current source revision. Nothing new was stored.";
  }
  return httpStatus === 202
    ? `Import accepted: ${a.created_document_ids.length} new file(s) received. Storage verification runs in the background; this is not extraction or engineering validation.`
    : "Import accepted.";
}

let nextEntryId = 1;

export function UploadForm({ projectId, expectedParentId, onImported, onStale }: Props) {
  const ids = useId();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const idemKey = useRef<string | null>(null);
  const failedRegion = useRef<HTMLDivElement | null>(null);

  useEffect(() => () => controller.current?.abort(), []);
  // The Abort button unmounts when the upload ends; keep focus on a persistent element.
  useEffect(() => {
    if (phase.kind === "failed") failedRegion.current?.focus();
  }, [phase.kind]);

  const problems = validateSelection(entries.map((e) => e.file));
  const uploading = phase.kind === "uploading";

  function changed(next: Entry[]) {
    idemKey.current = null; // a different selection is a different request
    setEntries(next);
    if (phase.kind !== "uploading") setPhase({ kind: "idle" });
  }

  function addFiles(list: FileList | null) {
    if (list === null || list.length === 0) return;
    const added = Array.from(list).map((file): Entry => ({ id: nextEntryId++, file, category: "" }));
    changed([...entries, ...added]);
  }

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    addFiles(event.target.files);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (!uploading) addFiles(event.dataTransfer.files);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (entries.length === 0 || problems.length > 0 || uploading) return;
    idemKey.current ??= newIdempotencyKey();
    const metadata: ImportMetadata = {
      expected_parent_source_revision_id: expectedParentId,
      idempotency_key: idemKey.current,
      files: entries.map((e) => ({ categories: e.category === "" ? [] : [e.category],
        tags: [],
        replaces_document_id: null, // replacement is explicit only; never inferred from names
      })),
    };
    const ctl = new AbortController();
    controller.current = ctl;
    setPhase({ kind: "uploading", progress: null });
    try {
      const result = await uploadImport(
        projectId,
        metadata,
        entries.map((e) => e.file),
        {
          signal: ctl.signal,
          onProgress: (progress) => {
            if (!ctl.signal.aborted) setPhase({ kind: "uploading", progress });
          },
        },
      );
      setPhase({ kind: "done", httpStatus: result.httpStatus, accepted: result.accepted });
      setEntries([]);
      idemKey.current = null;
      onImported(result.accepted);
    } catch (err) {
      const reason = err instanceof ApiError ? reasonOf(err) : null;
      if (err instanceof ApiError && (reason === "stale_parent" || err.code === "SESSION_TOKEN_INVALID")) {
        idemKey.current = null;
        if (reason === "stale_parent") onStale();
      }
      setPhase({ kind: "failed", ...describeUploadFailure(err) });
    } finally {
      if (controller.current === ctl) controller.current = null;
    }
  }

  const progress = phase.kind === "uploading" ? phase.progress : null;
  const percent =
    progress !== null && progress.total !== null && progress.total > 0
      ? Math.min(100, Math.floor((progress.loaded / progress.total) * 100))
      : null;

  return (
    <section aria-labelledby={`${ids}-title`} className="upload">
      <h5 id={`${ids}-title`}>Upload source files</h5>
      <p id={`${ids}-note`}>
        Files are stored and hash-verified only. Filenames and category hints are your labels, not engineering evidence,
        and nothing is extracted or validated in this step. Limits: {MAX_FILES} files, {formatBytes(MAX_FILE_BYTES)} per
        file, {formatBytes(MAX_BATCH_BYTES)} per import (the server is authoritative).
      </p>
      <form onSubmit={onSubmit} aria-describedby={`${ids}-note`}>
        <div
          className={dragging ? "dropzone dragging" : "dropzone"}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <p>Drop files here, or choose them with the file picker.</p>
          <label htmlFor={`${ids}-files`}>Choose files</label>{" "}
          <input id={`${ids}-files`} type="file" multiple disabled={uploading} onChange={onPick} />
        </div>

        {entries.length > 0 && (
          <>
            <p aria-live="polite">
              {entries.length} file(s) selected, {formatBytes(entries.reduce((s, e) => s + e.file.size, 0))} total.
            </p>
            <ul className="selected-files" aria-label="Selected files">
              {entries.map((e) => (
                <li key={e.id}>
                  <span>
                    {e.file.name} ({formatBytes(e.file.size)})
                  </span>{" "}
                  <label>
                    Category hint for {e.file.name}{" "}
                    <select
                      value={e.category}
                      disabled={uploading}
                      onChange={(ev) =>
                        changed(
                          entries.map((x) =>
                            x.id === e.id ? { ...x, category: ev.target.value as DocumentCategory | "" } : x,
                          ),
                        )
                      }
                    >
                      <option value="">No hint</option>
                      {CATEGORIES.map((c) => (
                        <option key={c} value={c}>
                          {categoryLabel(c)}
                        </option>
                      ))}
                    </select>
                  </label>{" "}
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={() => changed(entries.filter((x) => x.id !== e.id))}
                  >
                    Remove {e.file.name}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}

        {problems.length > 0 && (
          <div role="alert">
            <p>This selection cannot be uploaded:</p>
            <ul>
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        )}

        <p>
          <button type="submit" disabled={entries.length === 0 || problems.length > 0 || uploading}>
            Upload {entries.length > 0 ? `${entries.length} file(s)` : "files"}
          </button>{" "}
          {uploading && (
            <button type="button" onClick={() => controller.current?.abort()}>
              Abort upload
            </button>
          )}
        </p>
      </form>

      {phase.kind === "uploading" && (
        <div role="status">
          <label htmlFor={`${ids}-progress`}>Upload progress</label>{" "}
          <progress
            id={`${ids}-progress`}
            max={100}
            value={percent ?? undefined}
            aria-valuetext={percent === null ? "Starting upload" : `${percent} percent sent`}
          />{" "}
          <span>
            {percent === null
              ? "Starting upload…"
              : percent >= 100
                ? "All bytes sent; waiting for the server to store and hash them…"
                : `${percent}% sent (${formatBytes(progress?.loaded ?? 0)} of ${formatBytes(progress?.total ?? 0)})`}
          </span>
        </div>
      )}
      {phase.kind === "done" && (
        <div role="status">
          <p>{successText(phase.httpStatus, phase.accepted)}</p>
          <p>
            Source revision {phase.accepted.source_revision_id}
            {phase.accepted.job_id !== null && <>, job {phase.accepted.job_id}</>}.
          </p>
        </div>
      )}
      {phase.kind === "failed" && (
        <div role="alert" tabIndex={-1} ref={failedRegion}>
          <p>{phase.message}</p>
          {phase.detail !== null && <p>{phase.detail}</p>}
          {phase.requestId !== null && <p>Request ID: {phase.requestId}</p>}
        </div>
      )}
    </section>
  );
}
