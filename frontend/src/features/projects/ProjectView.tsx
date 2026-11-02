import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Title } from "@mantine/core";
import { ArrowLeft, Boxes, CircleCheck, Compass, Minus, Pencil } from "lucide-react";
import { Chip, EmptyState, ErrorState, KeyValue, KeyValueList, LoadingState, type ChipSpec } from "../../design";
import { ExploreWorkspace } from "../../app/shell/ExploreWorkspace";
import { ProjectTabs, SECTION_LABEL } from "../../app/shell/ProjectTabs";
import { SourcesPanel } from "../uploads/SourcesPanel";
import { getProject, updateProject } from "./api";
import { bumpProjectList } from "./listVersion";
import { PipelineSlot, ProjectOverviewSlot } from "./OverviewSlot";
import { ProjectForm } from "./ProjectForm";
import { keyString, projectKeys, saveSelectedProjectId, type Project, type Section } from "./keys";
import { useActionScope, useScopedResource } from "./scope";
import styles from "./ProjectView.module.css";

interface Props {
  projectId: string;
  section: Section;
  onSection: (section: Section) => void;
  onBack: () => void;
  onMissing: (projectId: string) => void;
}

/** What each section needs, derived only from the project's real revision pointers. */
export function prerequisite(section: Section, project: Project): string {
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

const ABSENT: ChipSpec = { tone: "neutral", icon: Minus };
const PRESENT: ChipSpec = { tone: "info", icon: CircleCheck };

function formatTime(iso: string): string {
  return new Date(iso).toUTCString();
}

function Unavailable({ section, project }: { section: Exclude<Section, "sources">; project: Project }) {
  const Icon = section === "explore" ? Compass : Boxes;
  return (
    <EmptyState title={`${SECTION_LABEL[section]} is unavailable`} icon={<Icon size={28} />}>
      <p>{prerequisite(section, project)}</p>
    </EmptyState>
  );
}

export function ProjectView({ projectId, section, onSection, onBack, onMissing }: Props) {
  const { state, reload, replace } = useScopedResource(
    keyString(projectKeys.detail(projectId)),
    (signal) => getProject(projectId, signal),
  );
  const run = useActionScope(`project:${projectId}`);
  const heading = useRef<HTMLHeadingElement | null>(null);
  const refresh = useRef<AbortController | null>(null);
  const [editing, setEditing] = useState(false);
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

  const back = (
    <Button
      variant="subtle"
      size="compact-sm"
      color="gray"
      leftSection={<ArrowLeft size={14} aria-hidden="true" />}
      aria-label="Back to all projects"
      onClick={onBack}
    >
      All projects
    </Button>
  );

  return (
    <section aria-labelledby="project-title" aria-busy={state.kind === "loading"}>
      {state.kind === "loading" && (
        <>
          <div className={styles.head}>
            <div className={styles.title}>
              {back}
              <Title order={3} id="project-title" ref={heading} tabIndex={-1}>
                Project
              </Title>
            </div>
          </div>
          <LoadingState label="Loading project…" />
        </>
      )}
      {state.kind === "error" && !missing && (
        <>
          <div className={styles.head}>
            <div className={styles.title}>
              {back}
              <Title order={3} id="project-title" ref={heading} tabIndex={-1}>
                Project unavailable
              </Title>
            </div>
          </div>
          <ErrorState
            message={`The project could not be loaded: ${state.error.message}`}
            requestId={state.error.requestId}
            onRetry={reload}
            retryLabel="Retry loading project"
          />
        </>
      )}
      {state.kind === "ready" && (
        <>
          <div className={styles.head}>
            <div className={styles.title}>
              {back}
              <Title order={3} id="project-title" ref={heading} tabIndex={-1}>
                {state.data.name}
              </Title>
              <div className={styles.chips}>
                <Chip
                  spec={state.data.latest_source_revision_id === null ? ABSENT : PRESENT}
                  label={state.data.latest_source_revision_id === null ? "No source revision" : "Source revision imported"}
                />
                <Chip
                  spec={state.data.active_model_revision_id === null ? ABSENT : PRESENT}
                  label={state.data.active_model_revision_id === null ? "No published model" : "Model revision published"}
                />
              </div>
            </div>
            <Button
              variant="default"
              size="xs"
              leftSection={<Pencil size={14} aria-hidden="true" />}
              aria-expanded={editing}
              onClick={() => setEditing(!editing)}
            >
              Edit project details
            </Button>
          </div>
          <div className={styles.card}>
            <KeyValueList>
              <KeyValue term="Description">
                {state.data.description === "" ? "No description." : state.data.description}
              </KeyValue>
              <KeyValue term="Created">{formatTime(state.data.created_at)}</KeyValue>
              <KeyValue term="Last updated">{formatTime(state.data.updated_at)}</KeyValue>
              <KeyValue term="Source revision">
                {state.data.latest_source_revision_id === null ? "None yet" : <code>{state.data.latest_source_revision_id}</code>}
              </KeyValue>
              <KeyValue term="Model revision">
                {state.data.active_model_revision_id === null ? "None yet" : <code>{state.data.active_model_revision_id}</code>}
              </KeyValue>
            </KeyValueList>
          </div>
          {editing && (
            <div className={styles.card}>
              <ProjectForm
                key={state.data.project_id}
                title="Edit project details"
                submitLabel="Save changes"
                initial={{ name: state.data.name, description: state.data.description }}
                submit={(values) => run((signal) => updateProject(projectId, values, signal))}
                onSaved={(project) => {
                  replace(project);
                  bumpProjectList();
                }}
              />
            </div>
          )}
          <ProjectTabs section={section} onSection={onSection} />
          <section aria-labelledby="section-title" className={styles.panel}>
            <Title order={4} id="section-title" className={styles.panelTitle}>
              {SECTION_LABEL[section]}
            </Title>
            {section === "sources" && (
              <>
                <ProjectOverviewSlot projectId={projectId} revisionId={state.data.latest_source_revision_id} />
                <PipelineSlot projectId={projectId} revisionId={state.data.latest_source_revision_id} />
                <SourcesPanel
                  projectId={projectId}
                  latestRevisionId={state.data.latest_source_revision_id}
                  onProjectChanged={refreshProject}
                />
              </>
            )}
            {section === "reconstruction" && <Unavailable section="reconstruction" project={state.data} />}
            {section === "explore" && (
              <ExploreWorkspace stage={<Unavailable section="explore" project={state.data} />} />
            )}
          </section>
        </>
      )}
    </section>
  );
}
