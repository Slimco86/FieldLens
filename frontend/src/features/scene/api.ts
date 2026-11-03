import { getJson, sendJson } from "../../api/client";
import type { components } from "../../api/generated";

type S = components["schemas"];
export type VisualAssetSpecRecord = S["VisualAssetSpecRecord"];
export type AssetSpecGenerateRequest = S["AssetSpecGenerateRequest"];

const base = (projectId: string, wellboreId: string) => `/api/v1/projects/${projectId}/wellbores/${wellboreId}/asset-spec`;

/** The current spec of one wellbore. A 404 means none has been generated yet. */
export const getAssetSpec = (projectId: string, wellboreId: string, signal: AbortSignal) =>
  getJson<VisualAssetSpecRecord>(base(projectId, wellboreId), signal);

/** Stub designer (no model call): builds a spec from the wellbore's equipment candidates. */
export const generateAssetSpec = (projectId: string, wellboreId: string, body: Partial<AssetSpecGenerateRequest>, signal?: AbortSignal) =>
  sendJson<VisualAssetSpecRecord>(`${base(projectId, wellboreId)}/generate`, "POST", body, signal);
