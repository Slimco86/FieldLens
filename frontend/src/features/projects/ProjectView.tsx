import { useCallback, useEffect, useRef } from "react";
import { getProject, updateProject } from "./api";
import { SourcesPanel } from "../uploads/SourcesPanel";
import { ProjectForm } from "./ProjectForm";
import {
  SECTIONS,
  keyString,
  projectKeys,
  saveSelectedProjectId,
  type Project,
  type Section,
} from "./keys";
import { useActionScope, useScopedResource } from "./scope";

interface Props {
  projectId: string;
  section: Section;
  onSection: (section: Section) => void;
  onBack: () => void;
  onMissing: (projectId: string) => void;
}

const SECTION_LABEL: Record<Section, string> = {
  sources: "Sources",
  reconstruction: "Reconstruction",
  explore: "Explore",
};

/** What each section needs, derived only from the project's real revision pointers. */
function prerequisite(section: Section, project: Project): string {
  switch (section) {
    case "sources":
      return ""; // rendered by SourcesPanel
    case "reconstruction":
      return project.latest_source_revision_id === null
        ? "Reconstruction requires an imported source revision. This project has none."
        : "Reconstruction is not available in this build.";
    case "explore":
      return project.active_model_revision_id === null
        ? "Explore requires a published model revision. This project has none."
        : "Exploring a model is not available in this build.";
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toUTCString();
}

export function ProjectView({ projectId, section, onSection, onBack, onMissing }: Props) {
  const { state, reload, replace } = useScopedResource(
    keyString(projectKeys.detail(projectId)),
    (signal) => getProject(projectId, signal),
  );
  const run = useActionScope(`project:${projectId}`);
  const heading = useRef<HTMLHeadingElement | null>(null);
  const refresh = useRef<AbortController | null>(null);
  useEffect(() => () => refresh.current?.abort(), []);
  // Re-read the project (latest-revision pointer) without a loading flash; stale answers are dropped.
  const refreshProject = useCallback(() => {
    refresh.current?.abort();
    const ctl = new AbortController();
    refresh.current = ctl;
    getProject(projectId, ctl.signal).then(
      (project) => {
        if (!ctl.signal.aborted) replace(project);
      },
      () => undefined,
    );
  }, [projectId, replace]);

  const missing = state.kind === "error" && state.error.status === 404;
  useEffect(() => {
    if (state.kind === "ready") saveSelectedProjectId(projectId);
  }, [state.kind, projectId]);
  useEffect(() => {
    if (missing) onMissing(projectId);
  }, [missing, onMissing, projectId]);
  useEffect(() => {
    if (state.kind !== "loading") heading.current?.focus();
  }, [state.kind]);

  return (
    <section aria-labelledby="project-title" aria-busy={state.kind === "loading"}>
      <button type="button" onClick={onBack}>
        Back to all projects
      </button>
      {state.kind === "loading" && (
        <>
          <h3 id="project-title" ref={heading} tabIndex={-1}>
            Project
          </h3>
          <p aria-live="polite">Loading project…</p>
        </>
      )}
      {state.kind === "error" && !missing && (
        <>
          <h3 id="project-title" ref={heading} tabIndex={-1}>
            Project unavailable
          </h3>
          <div role="alert">
            <p>The project could not be loaded: {state.error.message}</p>
            {state.error.requestId && <p>Request ID: {state.error.requestId}</p>}
            <button type="button" onClick={reload}>
              Retry loading project
            </button>
          </div>
        </>
      )}
      {state.kind === "ready" && (
        <>
          <h3 id="project-title" ref={heading} tabIndex={-1}>
            {state.data.name}
          </h3>
          <dl>
            <dt>Description</dt>
            <dd>{state.data.description === "" ? "No description." : state.data.description}</dd>
            <dt>Created</dt>
            <dd>{formatTime(state.data.created_at)}</dd>
            <dt>Last updated</dt>
            <dd>{formatTime(state.data.updated_at)}</dd>
            <dt>Source revision</dt>
            <dd>{state.data.latest_source_revision_id ?? "None yet"}</dd>
            <dt>Model revision</dt>
            <dd>{state.data.active_model_revision_id ?? "None yet"}</dd>
          </dl>
          <ProjectForm
            key={state.data.project_id}
            title="Edit project details"
            submitLabel="Save changes"
            initial={{ name: state.data.name, description: state.data.description }}
            submit={(values) => run((signal) => updateProject(projectId, values, signal))}
            onSaved={replace}
          />
          <nav aria-label="Project sections">
            <ul className="tabs">
              {SECTIONS.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    aria-current={s === section ? "page" : undefined}
                    onClick={() => onSection(s)}
                  >
                    {SECTION_LABEL[s]}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <section aria-labelledby="section-title">
            <h4 id="section-title">{SECTION_LABEL[section]}</h4>
            {section === "sources" ? (
              <SourcesPanel
                projectId={projectId}
                latestRevisionId={state.data.latest_source_revision_id}
                onProjectChanged={refreshProject}
              />
            ) : (
              <p>{prerequisite(section, state.data)}</p>
            )}
          </section>
        </>
      )}
    </section>
  );
}
