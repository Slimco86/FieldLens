import { toApiError } from "../../api/client";

/** Same-origin URL of the stored PDF (inline, `Range` capable); `#page=N` is read by the browser's PDF viewer. */
export function documentContentUrl(projectId: string, documentId: string, page?: number | null): string {
  const base = `/api/v1/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}/content`;
  return page !== undefined && page !== null && Number.isInteger(page) && page > 0 ? `${base}#page=${page}` : base;
}

/** PDF when the format family says so; without one, only a `.pdf` file name counts. Anything else is never offered to the viewer. */
export function isPdfSource(format: string | null | undefined, filename: string | null | undefined): boolean {
  if (format !== undefined && format !== null) return format.toLowerCase() === "pdf";
  return typeof filename === "string" && /\.pdf$/i.test(filename.trim());
}

const REASON: Record<string, string> = {
  missing: "the stored file is missing",
  size_mismatch: "the stored file does not match its recorded size",
  hash_mismatch: "the stored file does not match its recorded checksum",
};

/** Plain-language reason for a failed content request. */
export function contentFailureText(status: number, reason: unknown): string {
  if (status === 409) return `The file cannot be shown: ${typeof reason === "string" ? (REASON[reason] ?? reason) : "its stored copy failed verification"}.`;
  if (status === 415) return "Only PDF files can be shown here.";
  if (status === 404) return "The file was not found in this project.";
  if (status === 503) return "The file service is unavailable right now. Try again in a moment.";
  return `The file could not be loaded (HTTP ${status}).`;
}

/**
 * Checks the content route once (a one-byte range: the server verifies the stored file, remembers the result,
 * and no body is transferred) so a failure is shown with its reason; the iframe cannot report HTTP errors.
 */
export async function probeContent(projectId: string, documentId: string, signal: AbortSignal): Promise<string | null> {
  try {
    const res = await fetch(documentContentUrl(projectId, documentId), { headers: { range: "bytes=0-0" }, signal });
    if (res.ok) return null;
    const err = await toApiError(res);
    return contentFailureText(res.status, err.details?.["reason"]);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    return "The file could not be loaded (network error).";
  }
}
