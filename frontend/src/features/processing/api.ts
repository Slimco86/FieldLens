import { ApiError, getJson, sendJson } from "../../api/client";
import type { components } from "../../api/generated";

type S = components["schemas"];

export type DocumentProcessingState = S["DocumentProcessingState"];
export type DocumentProcessingStateList = S["DocumentProcessingStateList"];
export type DocumentModelRead = S["DocumentModelRead"];
export type DocumentIdentityProposal = S["DocumentIdentityProposal"];
export type ModelReadWarning = S["ModelReadWarning"];
export type ProcessingRun = S["ProcessingRun"];
export type ProcessingRunDocument = S["ProcessingRunDocument"];
export type ProcessingFailureCode = S["ProcessingFailureCode"];
export type ProcessingProviderInfo = S["ProcessingProviderInfo"];
export type DocumentModelOutcome = S["DocumentModelOutcome"];
export type ModelRunEntry = S["ModelRunEntry"];
export type ModelReplyRaw = S["ModelReplyRaw"];

const base = (projectId: string) => `/api/v1/projects/${projectId}/processing`;

export const listProcessingDocuments = (projectId: string, signal: AbortSignal) =>
  getJson<DocumentProcessingStateList>(`${base(projectId)}/documents`, signal);

export const getModelOutcome = (projectId: string, documentId: string, signal: AbortSignal) =>
  getJson<DocumentModelOutcome>(`${base(projectId)}/documents/${documentId}/outcome`, signal);

export const getProcessingRun = (projectId: string, runId: string, signal: AbortSignal) =>
  getJson<ProcessingRun>(`${base(projectId)}/runs/${runId}`, signal);

/** Estimate only: nothing is queued or spent. */
export const requestProcessingEstimate = (
  projectId: string,
  documentId: string,
  pages: { page_start: number; page_end: number } | null,
  force: boolean,
  signal?: AbortSignal,
) =>
  sendJson<ProcessingRun>(
    `${base(projectId)}/runs/estimates`,
    "POST",
    { documents: [pages === null ? { document_id: documentId } : { document_id: documentId, pages }], force },
    signal,
  );

/** The separate explicit confirm; the estimate is echoed so a changed estimate is a conflict, not a silent spend. */
export const confirmProcessingRun = (projectId: string, runId: string, estimatedUsd: string, signal?: AbortSignal) =>
  sendJson<ProcessingRun>(`${base(projectId)}/runs/${runId}/confirm`, "POST", { estimated_usd: estimatedUsd }, signal);

/** A retry is a new estimate that needs its own confirm. */
export const retryProcessingRun = (projectId: string, runId: string, signal?: AbortSignal) =>
  sendJson<ProcessingRun>(`${base(projectId)}/runs/${runId}/retry`, "POST", undefined, signal);

export const NO_NATIVE_PARSER_TEXT = "No native parser; model processing available";

export const FAILURE_TEXT: Record<ProcessingFailureCode, string> = {
  provider_refused: "The model refused to read this document. Nothing was stored.",
  provider_truncated: "The model's answer was cut off. Nothing was stored.",
  provider_malformed: "The model returned output that was not in the expected format. Nothing was stored.",
  provider_error: "The model provider returned an error. Nothing was stored.",
  budget_stop: "The run stopped because the budget would be exceeded. Nothing was marked successful.",
  confirmed_estimate_exceeded: "The run stopped because it would exceed the confirmed estimate. Nothing was marked successful.",
  document_unavailable: "The document could not be read. Nothing was stored.",
  page_count_changed: "The document's page count changed after the estimate. Nothing was stored.",
  interrupted: "The run was interrupted and did not finish. Nothing was stored.",
  cancelled: "The run was cancelled before it finished.",
};

export const FAILURE_LABEL: Record<ProcessingFailureCode, string> = {
  provider_refused: "Model refusal",
  provider_truncated: "Truncated output",
  provider_malformed: "Malformed output",
  provider_error: "Provider error",
  budget_stop: "Budget exceeded",
  confirmed_estimate_exceeded: "Estimate exceeded",
  document_unavailable: "Document unavailable",
  page_count_changed: "Page count changed",
  interrupted: "Interrupted",
  cancelled: "Cancelled",
};

export const STUB_TEXT =
  "Stub provider: no model was called and no data is extracted. Set FIELDLENS_PROCESSING_PROVIDER=meta to use the live model.";

/** The typed 409 for a requested-but-incomplete live provider: the missing setting NAMES, never values. */
export function misconfiguredMissing(err: unknown): string[] | null {
  if (!(err instanceof ApiError) || err.status !== 409 || err.details === null || err.details["reason"] !== "provider_misconfigured") return null;
  const m = err.details["missing"];
  return Array.isArray(m) ? m.filter((x): x is string => typeof x === "string") : [];
}

export function misconfiguredText(missing: string[]): string {
  return `The live model provider is requested but not fully configured${missing.length > 0 ? `: missing ${missing.join(", ")}` : ""}. Nothing was started and nothing was spent.`;
}
