// Centralized project/context identity. Request keys always include the project ID so a
// response can only ever be applied to the context that requested it.
import type { components } from "../../api/generated";

export type Project = components["schemas"]["Project"];
export type ProjectPage = components["schemas"]["ProjectPage"];
export type ProjectCreate = components["schemas"]["ProjectCreate"];
export type ProjectUpdate = components["schemas"]["ProjectUpdate"];

export const PROJECTS_PATH = "/api/v1/projects";
export const PAGE_LIMIT = 50;

export const projectKeys = {
  list: () => ["projects", "list", PAGE_LIMIT] as const,
  detail: (projectId: string) => ["projects", "detail", projectId] as const,
};

export type QueryKey = readonly (string | number)[];
export const keyString = (key: QueryKey): string => key.join("/");

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const isProjectId = (value: unknown): value is string =>
  typeof value === "string" && UUID.test(value);

export const SECTIONS = ["sources", "reconstruction", "explore"] as const;
export type Section = (typeof SECTIONS)[number];

// Only the selected project ID is persisted: no project content, geometry or arrays.
const STORAGE_KEY = "fieldlens.selectedProjectId";

export function loadSelectedProjectId(): string | null {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === null ? null : saved;
  } catch {
    return null;
  }
}

export function saveSelectedProjectId(projectId: string | null): void {
  try {
    if (projectId === null) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, projectId);
  } catch {
    /* storage unavailable: selection is then session-only */
  }
}
