import { ApiError, getJson, sendJson } from "../../api/client";
import {
  PAGE_LIMIT,
  PROJECTS_PATH,
  type Project,
  type ProjectCreate,
  type ProjectPage,
  type ProjectUpdate,
} from "./keys";

function checked(project: Project, requestedId?: string): Project {
  if (requestedId !== undefined && project.project_id !== requestedId) {
    throw new ApiError(502, "CONTEXT_MISMATCH", "The server answered for a different project.", null);
  }
  return project;
}

export function listProjects(signal: AbortSignal, cursor?: string): Promise<ProjectPage> {
  const query = new URLSearchParams({ limit: String(PAGE_LIMIT) });
  if (cursor !== undefined) query.set("cursor", cursor);
  return getJson<ProjectPage>(`${PROJECTS_PATH}?${query.toString()}`, signal);
}

export async function getProject(projectId: string, signal: AbortSignal): Promise<Project> {
  return checked(await getJson<Project>(`${PROJECTS_PATH}/${projectId}`, signal), projectId);
}

export function createProject(body: ProjectCreate, signal: AbortSignal): Promise<Project> {
  return sendJson<Project>(PROJECTS_PATH, "POST", body, signal);
}

export async function updateProject(
  projectId: string,
  body: ProjectUpdate,
  signal: AbortSignal,
): Promise<Project> {
  return checked(await sendJson<Project>(`${PROJECTS_PATH}/${projectId}`, "PATCH", body, signal), projectId);
}
