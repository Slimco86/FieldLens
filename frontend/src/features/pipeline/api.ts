import { getJson, sendJson } from "../../api/client";
import type { components } from "../../api/generated";

type S = components["schemas"];

export type StartGate = S["StartGate"];
export type ProjectExposure = S["ProjectExposure"];
export type DocumentProcessingState = S["DocumentProcessingState"];
export type DocumentProcessingStateList = S["DocumentProcessingStateList"];
export type ProcessingRun = S["ProcessingRun"];
export type ProcessingRunPage = S["ProcessingRunPage"];
export type ProcessingRunSummary = S["ProcessingRunSummary"];
export type ProcessingRunStatus = S["ProcessingRunStatus"];
export type ProcessingDocumentSelection = S["ProcessingDocumentSelection"];

const base = (projectId: string) => `/api/v1/projects/${projectId}`;
const runs = (projectId: string) => `${base(projectId)}/processing/runs`;

export const getStartGate = (projectId: string, signal: AbortSignal) =>
  getJson<StartGate>(`${base(projectId)}/identity/start-gate`, signal);

export const getExposure = (projectId: string, signal: AbortSignal) =>
  getJson<ProjectExposure>(`${base(projectId)}/identity/exposure`, signal);

export const getProcessingDocuments = (projectId: string, signal: AbortSignal) =>
  getJson<DocumentProcessingStateList>(`${base(projectId)}/processing/documents`, signal);

export const listRuns = (projectId: string, signal: AbortSignal) => getJson<ProcessingRunPage>(runs(projectId), signal);

export const getRun = (projectId: string, runId: string, signal: AbortSignal) =>
  getJson<ProcessingRun>(`${runs(projectId)}/${runId}`, signal);

export const requestEstimate = (
  projectId: string,
  documents: ProcessingDocumentSelection[],
  idempotencyKey: string,
  signal?: AbortSignal,
) =>
  sendJson<ProcessingRun>(
    `${runs(projectId)}/estimates`,
    "POST",
    { documents, idempotency_key: idempotencyKey },
    signal,
  );

/** Confirming is the only call that can spend; it echoes the estimate so a stale one is rejected. */
export const confirmRun = (projectId: string, runId: string, estimatedUsd: string, signal?: AbortSignal) =>
  sendJson<ProcessingRun>(`${runs(projectId)}/${runId}/confirm`, "POST", { estimated_usd: estimatedUsd }, signal);

export const cancelRun = (projectId: string, runId: string, signal?: AbortSignal) =>
  sendJson<ProcessingRun>(`${runs(projectId)}/${runId}/cancel`, "POST", undefined, signal);

export const retryRun = (projectId: string, runId: string, signal?: AbortSignal) =>
  sendJson<ProcessingRun>(`${runs(projectId)}/${runId}/retry`, "POST", undefined, signal);
