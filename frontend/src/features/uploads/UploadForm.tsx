import { useEffect, useId, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Button, Checkbox, NativeSelect, Title } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { CircleAlert, CloudUpload, Upload, X } from "lucide-react";
import { ApiError } from "../../api/client";
import { Callout, TruncatedText } from "../../design";
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
  describeStorageError,
} from "./api";
import { categoryLabel, formatBytes } from "./format";
import { matchRefusals, parseImportRefusal, type ParsedRefusal } from "./refusal";
import styles from "./shared.module.css";
import zone from "./UploadForm.module.css";

interface Entry {
  id: number;
  file: File;
  category: DocumentCategory | "";
  /** Part of the checked subset that a bulk category assignment targets. */
  checked: boolean;
}

interface FailureView {
  message: string;
  requestId: string | null;
  detail: string | null;
  /** Per-file refusal (IN-10) when the server's details were well-formed; null otherwise. */
  refusal?: ParsedRefusal | null;
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

/** Which file the server refused: only what the response or the selection really tells us. */
function offenderNote(err: ApiError, names: readonly string[]): string {
  const named = err.details?.["filename"] ?? err.details?.["file"];
  if (typeof named === "string") return ` The server named the file: “${named}”.`;
  const index = err.details?.["index"] ?? err.details?.["file_index"];
  if (typeof index === "number" && names[index] !== undefined) return ` The server pointed at file ${index + 1}: “${names[index]}”.`;
  if (names.length === 1) return ` The only selected file is “${names[0]}”.`;
  return " The server response does not say which of the selected files was refused; check each file's name, size and type.";
}

const sentence = (text: string): string => (/[.!?]$/.test(text.trim()) ? text.trim() : `${text.trim()}.`);

export function describeUploadFailure(err: unknown, names: readonly string[] = []): FailureView {
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
    const refusal = parseImportRefusal(err.details);
    if (refusal !== null) {
      return { message: `Upload refused. Nothing was stored. ${sentence(err.message)}`, requestId, detail, refusal };
    }
    const storage = describeStorageError(err);
    if (err.status === 503 && storage !== null) return { message: storage, requestId, detail };
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
        return { message: `Conflict: ${sentence(err.message)}`, requestId, detail };
      case 413:
        return { message: `The server rejected the upload as too large: ${sentence(err.message)}${offenderNote(err, names)}`, requestId, detail };
      case 415:
        return {
          message: `The server rejected an unsupported file type (for example a binary or executable): ${sentence(err.message)}${offenderNote(err, names)} Remove the refused file and try again.`,
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
  const repaired = a.repaired_document_ids?.length ?? 0;
  if (repaired > 0) {
    const fresh = a.created_document_ids.length;
    return `${repaired} file(s) were repaired: their stored copy was missing or damaged and the uploaded bytes replaced it${fresh > 0 ? `; ${fresh} new file(s) were also received` : ""}. Storage verification runs in the background.`;
  }
  if (a.deduplicated) {
    return "Every file already belongs to the current source revision. Nothing new was stored.";
  }
  return httpStatus === 202
    ? `Import accepted: ${a.created_document_ids.length} new file(s) received. Storage verification runs in the background; this is not extraction or engineering validation.`
    : "Import accepted.";
}

const DONE_VISIBLE_MS = 10_000;

let nextEntryId = 1;

export function UploadForm({ projectId, expectedParentId, onImported, onStale }: Props) {
  const ids = useId();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const controller = useRef<AbortController | null>(null);
  const idemKey = useRef<string | null>(null);
  const failedRegion = useRef<HTMLDivElement | null>(null);
  const pickerRef = useRef<HTMLInputElement | null>(null);
  const removeButtons = useRef(new Map<number, HTMLButtonElement>());
  // Id of the entry whose button should receive focus after a removal (null = the file picker).
  const focusAfterRemove = useRef<{ id: number | null } | null>(null);

  useEffect(() => {
    const target = focusAfterRemove.current;
    if (target === null) return;
    focusAfterRemove.current = null;
    const btn = target.id === null ? undefined : removeButtons.current.get(target.id);
    (btn ?? pickerRef.current)?.focus();
  }, [entries]);

  useEffect(() => () => controller.current?.abort(), []);
  // The Abort button unmounts when the upload ends; keep focus on a persistent element.
  useEffect(() => {
    if (phase.kind === "failed") failedRegion.current?.focus();
  }, [phase.kind]);

  // The "accepted" confirmation is transient; it clears itself (still announced while shown).
  useEffect(() => {
    if (phase.kind !== "done") return;
    const timer = window.setTimeout(() => setPhase((p) => (p.kind === "done" ? { kind: "idle" } : p)), DONE_VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [phase]);

  const problems = validateSelection(entries.map((e) => e.file));
  const uploading = phase.kind === "uploading";

  function changed(next: Entry[], keepFailure = false) {
    idemKey.current = null; // a different selection is a different request
    setEntries(next);
    if (phase.kind !== "uploading" && !(keepFailure && phase.kind === "failed")) setPhase({ kind: "idle" });
  }

  const checkedCount = entries.filter((e) => e.checked).length;
  const allChecked = entries.length > 0 && checkedCount === entries.length;
  const [bulkCategory, setBulkCategory] = useState<DocumentCategory | "">("");
  const [bulkNote, setBulkNote] = useState("");
  const targets = checkedCount > 0 ? entries.filter((e) => e.checked) : entries;

  function applyBulk() {
    const ids = new Set(targets.map((e) => e.id));
    changed(entries.map((e) => (ids.has(e.id) ? { ...e, category: bulkCategory } : e)), true);
    setBulkNote(
      bulkCategory === ""
        ? `Cleared the category hint on ${ids.size} file(s).`
        : `Set the category hint “${categoryLabel(bulkCategory)}” on ${ids.size} file(s).`,
    );
  }

  function addFiles(list: ArrayLike<File> | null) {
    if (list === null || list.length === 0) return;
    const added = Array.from(list).map((file): Entry => ({ id: nextEntryId++, file, category: "", checked: false }));
    changed([...entries, ...added]);
  }

  function removeEntry(id: number) {
    const index = entries.findIndex((x) => x.id === id);
    const next = entries.filter((x) => x.id !== id);
    const neighbour = next[index] ?? next[index - 1];
    focusAfterRemove.current = { id: neighbour === undefined ? null : neighbour.id };
    changed(next);
  }

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    addFiles(event.target.files);
    event.target.value = "";
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(entries);
  }

  function removeRefusedAndRetry(refusedIds: ReadonlySet<number>) {
    const kept = entries.filter((e) => !refusedIds.has(e.id));
    changed(kept);
    if (kept.length > 0) void send(kept);
  }

  async function send(list: Entry[]) {
    if (list.length === 0 || validateSelection(list.map((e) => e.file)).length > 0 || uploading) return;
    idemKey.current ??= newIdempotencyKey();
    const metadata: ImportMetadata = {
      expected_parent_source_revision_id: expectedParentId,
      idempotency_key: idemKey.current,
      files: list.map((e) => ({ categories: e.category === "" ? [] : [e.category],
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
        list.map((e) => e.file),
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
      setPhase({ kind: "failed", ...describeUploadFailure(err, list.map((e) => e.file.name)) });
    } finally {
      if (controller.current === ctl) controller.current = null;
    }
  }

  const refusal = phase.kind === "failed" ? (phase.refusal ?? null) : null;
  const matches = refusal === null ? null : matchRefusals(entries.map((e) => e.file.name), refusal.files);
  const refusedIds = new Set<number>();
  if (matches !== null) entries.forEach((e, i) => matches.byIndex.has(i) && refusedIds.add(e.id));
  const progress = phase.kind === "uploading" ? phase.progress : null;
  const percent =
    progress !== null && progress.total !== null && progress.total > 0
      ? Math.min(100, Math.floor((progress.loaded / progress.total) * 100))
      : null;

  return (
    <section aria-labelledby={`${ids}-title`} className={styles.card}>
      <div className={styles.cardHead}>
        <Title order={5} id={`${ids}-title`}>
          Upload source files
        </Title>
      </div>
      <p id={`${ids}-note`} className={styles.note}>
        Files are stored and hash-verified only. Filenames and category hints are your labels, not engineering evidence,
        and nothing is extracted or validated in this step. Limits: {MAX_FILES} files, {formatBytes(MAX_FILE_BYTES)} per
        file, {formatBytes(MAX_BATCH_BYTES)} per import (the server is authoritative).
      </p>
      <form onSubmit={onSubmit} aria-describedby={`${ids}-note`} className={styles.stack}>
        <Dropzone
          onDrop={(files) => {
            if (!uploading) addFiles(files);
          }}
          disabled={uploading}
          activateOnClick={false}
          activateOnKeyboard={false}
          multiple
          unstyled
          inputProps={{ "aria-hidden": true }}
          className={zone.zone}
        >
          <Dropzone.Accept>
            <Upload size={28} aria-hidden="true" />
          </Dropzone.Accept>
          <Dropzone.Idle>
            <CloudUpload size={28} aria-hidden="true" />
          </Dropzone.Idle>
          <p className={zone.zoneText}>Drop files here, or choose them with the file picker.</p>
          <div className={zone.pickerWrap}>
            <input
              ref={pickerRef}
              id={`${ids}-files`}
              className={zone.picker}
              type="file"
              multiple
              disabled={uploading}
              onChange={onPick}
            />
            <label htmlFor={`${ids}-files`} className={zone.pickerLabel}>
              Choose files
            </label>
          </div>
        </Dropzone>

        {entries.length > 0 && (
          <>
            <p aria-live="polite" className={styles.note}>
              {entries.length} file(s) selected, {formatBytes(entries.reduce((s, e) => s + e.file.size, 0))} total.
            </p>
            <fieldset className={zone.bulk} disabled={uploading}>
              <legend>Category hint for several files</legend>
              <Checkbox
                label="Select all files"
                checked={allChecked}
                indeterminate={checkedCount > 0 && !allChecked}
                onChange={(ev) => {
                  const on = ev.currentTarget.checked;
                  setEntries(entries.map((e) => ({ ...e, checked: on })));
                }}
              />
              <NativeSelect
                size="xs"
                aria-label="Category hint to apply"
                value={bulkCategory}
                data={[{ value: "", label: "No hint" }, ...CATEGORIES.map((c) => ({ value: c, label: categoryLabel(c) }))]}
                onChange={(ev) => setBulkCategory(ev.currentTarget.value as DocumentCategory | "")}
              />
              <Button type="button" size="compact-sm" variant="default" onClick={applyBulk}>
                {checkedCount > 0 ? `Apply to ${checkedCount} checked file(s)` : `Apply to all ${entries.length} file(s)`}
              </Button>
              <span className={styles.note} role="status">
                {bulkNote}
              </span>
            </fieldset>
            <ul className={zone.files} aria-label="Selected files">
              {entries.map((e, index) => {
                const hit = matches?.byIndex.get(index);
                return (
                <li key={e.id} className={hit === undefined ? zone.file : `${zone.file} ${zone.refused}`} data-refused={hit === undefined ? undefined : "true"}>
                  <Checkbox
                    aria-label={`Select ${e.file.name} for a bulk category hint`}
                    checked={e.checked}
                    disabled={uploading}
                    onChange={(ev) => {
                      const on = ev.currentTarget.checked;
                      setEntries(entries.map((x) => (x.id === e.id ? { ...x, checked: on } : x)));
                    }}
                  />
                  <span className={zone.fileName}>
                    <TruncatedText value={e.file.name} label="file name" maxCh={60} />
                  </span>
                  <span className={zone.fileSize}>({formatBytes(e.file.size)})</span>
                  {hit !== undefined && (
                    <span className={zone.refusedText}>
                      <CircleAlert size={14} aria-hidden="true" /> Refused: {hit.refusal.message} ({hit.refusal.reason}
                      {hit.refusal.statusCode !== null ? `, HTTP ${hit.refusal.statusCode}` : ""}).
                      {hit.byNameOnly && ` The server's position (file ${hit.refusal.position + 1}) differs from this file's; matched by file name.`}
                    </span>
                  )}
                  <NativeSelect
                    size="xs"
                    aria-label={`Category hint for ${e.file.name}`}
                    value={e.category}
                    disabled={uploading}
                    data={[{ value: "", label: "No hint" }, ...CATEGORIES.map((c) => ({ value: c, label: categoryLabel(c) }))]}
                    onChange={(ev) =>
                      changed(
                        entries.map((x) =>
                          x.id === e.id ? { ...x, category: ev.currentTarget.value as DocumentCategory | "" } : x,
                        ),
                        true,
                      )
                    }
                  />
                  <Button
                    size="compact-sm"
                    variant="subtle"
                    color="gray"
                    disabled={uploading}
                    leftSection={<X size={14} aria-hidden="true" />}
                    aria-label={`Remove ${e.file.name}`}
                    ref={(el) => {
                      if (el === null) removeButtons.current.delete(e.id);
                      else removeButtons.current.set(e.id, el);
                    }}
                    onClick={() => removeEntry(e.id)}
                  >
                    Remove
                  </Button>
                </li>
                );
              })}
            </ul>
          </>
        )}

        {problems.length > 0 && (
          <Callout tone="danger" role="alert">
            <p>This selection cannot be uploaded:</p>
            <ul className={styles.plainList}>
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </Callout>
        )}

        <div className={styles.row}>
          <Button type="submit" disabled={entries.length === 0 || problems.length > 0 || uploading}>
            Upload {entries.length > 0 ? `${entries.length} file(s)` : "files"}
          </Button>
          {uploading && (
            <Button type="button" variant="default" onClick={() => controller.current?.abort()}>
              Abort upload
            </Button>
          )}
        </div>
      </form>

      {phase.kind === "uploading" && (
        <div role="status" className={zone.progress}>
          <label htmlFor={`${ids}-progress`}>Upload progress</label>
          <progress
            id={`${ids}-progress`}
            max={100}
            value={percent ?? undefined}
            aria-valuetext={percent === null ? "Starting upload" : `${percent} percent sent`}
          />
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
        <Callout tone={phase.accepted.replayed || phase.accepted.deduplicated ? "info" : "success"} role="status">
          <p>{successText(phase.httpStatus, phase.accepted)}</p>
          <p>
            Source revision {phase.accepted.source_revision_id}
            {phase.accepted.job_id !== null && <>, job {phase.accepted.job_id}</>}.
          </p>
        </Callout>
      )}
      {phase.kind === "failed" && (
        <Callout
          tone="danger"
          role="alert"
          tabIndex={-1}
          elementRef={failedRegion}
          actions={
            refusal === null ? undefined : (
              <>
                {refusedIds.size > 0 && refusedIds.size < entries.length && (
                  <Button type="button" size="compact-sm" onClick={() => removeRefusedAndRetry(refusedIds)}>
                    Remove refused files and retry
                  </Button>
                )}
                {refusedIds.size > 0 && refusedIds.size === entries.length && (
                  <Button type="button" size="compact-sm" onClick={() => changed(entries.filter((e) => !refusedIds.has(e.id)))}>
                    Remove refused files
                  </Button>
                )}
                <Button type="button" size="compact-sm" variant="default" disabled={uploading} onClick={() => void send(entries)}>
                  Retry upload
                </Button>
              </>
            )
          }
        >
          <p>{phase.message}</p>
          {refusal !== null && (
            <>
              <p>
                {refusal.scope === "files"
                  ? `The server refused ${refusal.files.length} of ${refusal.fileCount ?? entries.length} file(s) and stored none of this batch.`
                  : "The whole batch was refused by a batch-level rule and none of it was stored."}{" "}
                {refusedIds.size > 0 && entries.length > refusedIds.size
                  ? "Every other selected file is still selected."
                  : ""}
              </p>
              {!refusal.complete && (
                <p>
                  This list may be incomplete: {refusal.scope === "batch" ? "intake stopped at a batch-level check" : "some refusals could not be read"},
                  so more files may be refused on retry.
                </p>
              )}
              {matches !== null && matches.unmatched.length > 0 && (
                <>
                  <p>The server also named files that are not in the current selection:</p>
                  <ul className={styles.plainList}>
                    {matches.unmatched.map((r) => (
                      <li key={`${r.position}-${r.filename}`}>
                        “{r.filename}” (position {r.position + 1}): {r.message} ({r.reason})
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
          {phase.detail !== null && <p>{phase.detail}</p>}
          {phase.requestId !== null && <p>Request ID: {phase.requestId}</p>}
        </Callout>
      )}
    </section>
  );
}
