import { getJson } from "../../api/client";
import type { components } from "../../api/generated";

type S = components["schemas"];

export type StartGate = S["StartGate"];
export type ProjectExposure = S["ProjectExposure"];

const base = (projectId: string) => `/api/v1/projects/${projectId}`;

export const getStartGate = (projectId: string, signal: AbortSignal) =>
  getJson<StartGate>(`${base(projectId)}/identity/start-gate`, signal);

export const getExposure = (projectId: string, signal: AbortSignal) =>
  getJson<ProjectExposure>(`${base(projectId)}/identity/exposure`, signal);
