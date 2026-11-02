import { ApiError, discardSessionToken, getJson, mutate, sendJson, sessionToken } from "../../api/client";
import type { components } from "../../api/generated";

export type ImportAccepted = components["schemas"]["ImportAccepted"];
export type ImportMetadata = components["schemas"]["ImportMetadata"];
export type SourceRevisionPage = components["schemas"]["SourceRevisionPage"];
export type SourceRevisionSummary = components["schemas"]["SourceRevisionSummary"];
export type DocumentPage = components["schemas"]["DocumentPage"];
export type SourceDocumentItem = components["schemas"]["SourceDocumentItem"];
export type DocumentCategory = components["schemas"]["DocumentCategory"];
export type ClassificationUpdate = components["schemas"]["ClassificationUpdate"];
export type Job = components["schemas"]["Job"];
export type ExtractionReport = components["schemas"]["ExtractionReport"];
export type ExtractedRecord = components["schemas"]["ExtractedRecord"];
export type ExtractedRecordPage = components["schemas"]["ExtractedRecordPage"];
export type ExtractionRequeue = components["schemas"]["ExtractionRequeue"];
export type StorageRetryResult = components["schemas"]["StorageRetryResult"];
export type EvidenceLink = components["schemas"]["EvidenceLink"];
export type ExtractionCandidate = components["schemas"]["ExtractionCandidate"];
export type ExtractionCandidatePage = components["schemas"]["ExtractionCandidatePage"];

export const MAX_FILE_BYTES = 128 * 1024 * 1024;
export const MAX_BATCH_BYTES = 512 * 1024 * 1024;
export const MAX_FILES = 200;
export const MAX_TAGS = 20;
export const MAX_TAG_LENGTH = 64;
export const REVISION_PAGE_LIMIT = 20;
export const DOCUMENT_PAGE_LIMIT = 50;

export const CATEGORIES: readonly DocumentCategory[] = [
  "trajectory",
  "completion_equipment",
  "perforation_history",
  "production_injection",
  "well_logs",
  "geology_reservoir",
  "terrain_bathymetry",
  "general_report",
];

const base = (projectId: string) => `/api/v1/projects/${projectId}`;

export function listRevisions(projectId: string, signal: AbortSignal): Promise<SourceRevisionPage> {
  return getJson<SourceRevisionPage>(`${base(projectId)}/source-revisions?limit=${REVISION_PAGE_LIMIT}`, signal);
}

export function listDocuments(
  projectId: string,
  revisionId: string,
  signal: AbortSignal,
  cursor?: string,
): Promise<DocumentPage> {
  const q = new URLSearchParams({ limit: String(DOCUMENT_PAGE_LIMIT), source_revision_id: revisionId });
  if (cursor !== undefined) q.set("cursor", cursor);
  return getJson<DocumentPage>(`${base(projectId)}/documents?${q.toString()}`, signal);
}

export const RECORD_PAGE_LIMIT = 25;

const extractionUrl = (projectId: string, documentId: string) =>
  `${base(projectId)}/documents/${documentId}/extraction`;

export function getExtraction(projectId: string, documentId: string, signal: AbortSignal): Promise<ExtractionReport> {
  return getJson<ExtractionReport>(extractionUrl(projectId, documentId), signal);
}

export function listExtractedRecords(
  projectId: string,
  documentId: string,
  signal: AbortSignal,
  cursor?: string,
): Promise<ExtractedRecordPage> {
  const q = new URLSearchParams({ limit: String(RECORD_PAGE_LIMIT) });
  if (cursor !== undefined) q.set("cursor", cursor);
  return getJson<ExtractedRecordPage>(`${extractionUrl(projectId, documentId)}/records?${q.toString()}`, signal);
}

export const CANDIDATE_PAGE_LIMIT = 25;

export function listCandidates(
  projectId: string,
  documentId: string,
  signal: AbortSignal,
  cursor?: string,
): Promise<ExtractionCandidatePage> {
  const q = new URLSearchParams({ limit: String(CANDIDATE_PAGE_LIMIT) });
  if (cursor !== undefined) q.set("cursor", cursor);
  return getJson<ExtractionCandidatePage>(
    `${base(projectId)}/documents/${documentId}/extraction-candidates?${q.toString()}`,
    signal,
  );
}

export async function requeueExtraction(
  projectId: string,
  documentId: string,
  signal: AbortSignal,
): Promise<ExtractionRequeue> {
  const res = await mutate(`${extractionUrl(projectId, documentId)}?retry=true`, { method: "POST", signal });
  return (await res.json()) as ExtractionRequeue;
}

export async function retryStorage(
  projectId: string,
  documentId: string,
  signal: AbortSignal,
): Promise<StorageRetryResult> {
  const res = await mutate(`${base(projectId)}/documents/${documentId}/storage/retry`, { method: "POST", signal });
  return (await res.json()) as StorageRetryResult;
}

export const STORAGE_ROOT_MISMATCH_MESSAGE =
  "The storage root does not match this database, so files cannot be verified or stored. See scripts/storage_root.py.";
export const REUPLOAD_MESSAGE = "The stored copy cannot be read. Re-upload this file with the upload control.";

/** Plain-language text for storage-related refusals; null when the error is not one of them. */
export function describeStorageError(err: unknown): string | null {
  if (!(err instanceof ApiError)) return null;
  const reason = err.details?.["reason"];
  if (err.status === 503 && reason === "storage_root_mismatch") return STORAGE_ROOT_MISMATCH_MESSAGE;
  if (err.status === 409 && (reason === "stored_copy_unreadable" || reason === "source_unreadable" || err.details?.["recovery"] === "re-upload")) {
    return /re-?upload/i.test(err.message) ? err.message : `${err.message} ${REUPLOAD_MESSAGE}`;
  }
  if (err.status === 409 && reason === "verification_pending") {
    return "Storage verification is still running for this file; try again shortly.";
  }
  return null;
}

export function getJob(projectId: string, jobId: string, signal: AbortSignal): Promise<Job> {
  return getJson<Job>(`${base(projectId)}/jobs/${jobId}`, signal);
}

export async function cancelJob(projectId: string, jobId: string, signal: AbortSignal): Promise<Job> {
  const res = await mutate(`${base(projectId)}/jobs/${jobId}/cancel`, { method: "POST", signal });
  return (await res.json()) as Job;
}

export function updateClassification(
  projectId: string,
  documentId: string,
  body: ClassificationUpdate,
  signal: AbortSignal,
): Promise<SourceDocumentItem> {
  return sendJson<SourceDocumentItem>(`${base(projectId)}/documents/${documentId}/classification`, "PATCH", body, signal);
}

export interface UploadResult {
  /** 202 = new import, 200 = idempotent replay / all-duplicate no-op. */
  httpStatus: number;
  accepted: ImportAccepted;
}

export interface UploadProgress {
  loaded: number;
  total: number | null;
}

/** A transport failure: the request may or may not have reached the server. */
export class NetworkUploadError extends Error {
  readonly timedOut: boolean;
  constructor(timedOut: boolean) {
    super(timedOut ? "The upload timed out." : "The connection to the local API failed.");
    this.name = "NetworkUploadError";
    this.timedOut = timedOut;
  }
}

/** The user aborted. `fullySent` means every byte left the browser, so the outcome is unknown. */
export class UploadAbortedError extends Error {
  readonly fullySent: boolean;
  constructor(fullySent: boolean) {
    super("The upload was aborted.");
    this.name = "UploadAbortedError";
    this.fullySent = fullySent;
  }
}

function parseError(xhr: XMLHttpRequest): ApiError {
  let code: string | null = null;
  let message = `Upload failed (${xhr.status})`;
  let requestId: string | null = xhr.getResponseHeader("x-request-id");
  let details: Record<string, unknown> | null = null;
  try {
    const body = JSON.parse(xhr.responseText) as {
      error?: { code?: string; message?: string; request_id?: string; details?: Record<string, unknown> | null };
    };
    code = body.error?.code ?? null;
    message = body.error?.message ?? message;
    requestId = body.error?.request_id ?? requestId;
    details = body.error?.details ?? null;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(xhr.status, code, message, requestId, details);
}

/**
 * Multipart upload over XHR (fetch has no upload progress). The `metadata` JSON part is appended
 * first and `files` parts follow in the same order as `metadata.files`.
 */
export async function uploadImport(
  projectId: string,
  metadata: ImportMetadata,
  files: readonly File[],
  opts: { signal: AbortSignal; onProgress: (p: UploadProgress) => void },
): Promise<UploadResult> {
  const csrf = await sessionToken();
  if (opts.signal.aborted) throw new UploadAbortedError(false);
  const form = new FormData();
  form.append("metadata", JSON.stringify(metadata));
  for (const file of files) form.append("files", file, file.name);

  return new Promise<UploadResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let fullySent = false;
    const onAbort = () => xhr.abort();
    opts.signal.addEventListener("abort", onAbort, { once: true });
    const done = () => opts.signal.removeEventListener("abort", onAbort);

    xhr.open("POST", `${base(projectId)}/imports`);
    xhr.setRequestHeader("x-fieldlens-token", csrf);
    xhr.setRequestHeader("accept", "application/json");
    xhr.upload.onprogress = (event) => {
      opts.onProgress({ loaded: event.loaded, total: event.lengthComputable ? event.total : null });
      if (event.lengthComputable && event.loaded >= event.total) fullySent = true;
    };
    xhr.upload.onload = () => {
      fullySent = true;
    };
    xhr.onload = () => {
      done();
      if (xhr.status === 200 || xhr.status === 202) {
        try {
          resolve({ httpStatus: xhr.status, accepted: JSON.parse(xhr.responseText) as ImportAccepted });
        } catch {
          reject(new ApiError(502, null, "The server answer could not be read.", null));
        }
        return;
      }
      const err = parseError(xhr);
      if (err.code === "SESSION_TOKEN_INVALID") discardSessionToken();
      reject(err);
    };
    xhr.onerror = () => {
      done();
      reject(new NetworkUploadError(false));
    };
    xhr.ontimeout = () => {
      done();
      reject(new NetworkUploadError(true));
    };
    xhr.onabort = () => {
      done();
      reject(new UploadAbortedError(fullySent));
    };
    xhr.send(form);
  });
}
