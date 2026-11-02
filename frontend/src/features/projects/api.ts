import { ApiError, getJson, mutate, sendJson } from "../../api/client";
import {
  PAGE_LIMIT,
  PROJECTS_PATH,
  type Project,
  type ProjectCreate,
  type ProjectDeletionPreview,
  type ProjectDeletionStatus,
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

export async function getDeletionPreview(projectId: string, signal: AbortSignal): Promise<ProjectDeletionPreview> {
  const preview = await getJson<ProjectDeletionPreview>(`${PROJECTS_PATH}/${projectId}/deletion-preview`, signal);
  if (preview.project_id !== projectId) {
    throw new ApiError(502, "CONTEXT_MISMATCH", "The server answered for a different project.", null);
  }
  return preview;
}

/** Requests irreversible deletion (202). Repeating it on a failed project is the retry. */
export async function requestProjectDeletion(
  projectId: string,
  confirmName: string,
  signal: AbortSignal,
): Promise<ProjectDeletionStatus> {
  const res = await mutate(`${PROJECTS_PATH}/${projectId}`, {
    method: "DELETE",
    body: { confirm_name: confirmName },
    signal,
  });
  return (await res.json()) as ProjectDeletionStatus;
}
