import { ProjectOverview } from "../overview/ProjectOverview";
import { PipelinePanel } from "../pipeline/PipelinePanel";

/** The pipeline panel (UI-15, TASK-053): readiness, data exposure and explicit processing, beside the Overview. */
export function PipelineSlot({ projectId, revisionId }: { projectId: string; revisionId: string | null }) {
  return <PipelinePanel key={projectId} projectId={projectId} revisionId={revisionId} />;
}

/** The project Overview (UI-13, TASK-048): the first view of the Sources tab, from existing APIs only. */
export function ProjectOverviewSlot({ projectId, revisionId }: { projectId: string; revisionId: string | null }) {
  return <ProjectOverview projectId={projectId} revisionId={revisionId} />;
}
