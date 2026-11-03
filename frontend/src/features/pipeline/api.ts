import { getJson, sendJson } from "../../api/client";
import type { components } from "../../api/generated";

type S = components["schemas"];

export type StartGate = S["StartGate"];
export type ProjectExposure = S["ProjectExposure"];

const base = (projectId: string) => `/api/v1/projects/${projectId}`;

export const getStartGate = (projectId: string, signal: AbortSignal) =>
  getJson<StartGate>(`${base(projectId)}/identity/start-gate`, signal);

export const getExposure = (projectId: string, signal: AbortSignal) =>
  getJson<ProjectExposure>(`${base(projectId)}/identity/exposure`, signal);

export type ReconstructionEstimate = S["ReconstructionEstimate"];
export type ReconstructionStageEstimate = S["ReconstructionStageEstimate"];
export type ReconstructionEstimateItem = S["ReconstructionEstimateItem"];
export type ReconstructionRun = S["ReconstructionRun"];
export type ReconstructionRunPage = S["ReconstructionRunPage"];
export type ReconstructionStage = S["ReconstructionStage"];
export type ReconstructionSummary = S["ReconstructionSummary"];
export type ReconstructionEvidenceRef = S["ReconstructionEvidenceRef"];

const runs = (projectId: string) => `${base(projectId)}/reconstruction-runs`;

export const listReconstructionRuns = (projectId: string, signal: AbortSignal) =>
  getJson<ReconstructionRunPage>(runs(projectId), signal);

/** Estimate only: nothing is queued or spent. `wellboreIds` for one wellbore, `null` for every ready wellbore. */
export const requestReconstructionEstimate = (projectId: string, wellboreIds: string[] | null, signal?: AbortSignal) =>
  sendJson<ReconstructionEstimate>(
    `${runs(projectId)}/estimates`,
    "POST",
    wellboreIds === null ? { all_ready: true } : { wellbore_ids: wellboreIds },
    signal,
  );

/** The separate explicit confirm; the total is echoed so a changed estimate is a conflict, not a silent spend. */
export const confirmReconstructionEstimate = (projectId: string, estimateId: string, estimatedUsd: string, signal?: AbortSignal) =>
  sendJson<ReconstructionRunPage>(`${runs(projectId)}/estimates/${estimateId}/confirm`, "POST", { estimated_usd: estimatedUsd }, signal);

export const cancelReconstructionRun = (projectId: string, runId: string, signal?: AbortSignal) =>
  sendJson<ReconstructionRun>(`${runs(projectId)}/${runId}/cancel`, "POST", undefined, signal);

/** A retry is a new estimate that needs its own confirm. */
export const retryReconstructionRun = (projectId: string, runId: string, signal?: AbortSignal) =>
  sendJson<ReconstructionEstimate>(`${runs(projectId)}/${runId}/retry`, "POST", undefined, signal);
