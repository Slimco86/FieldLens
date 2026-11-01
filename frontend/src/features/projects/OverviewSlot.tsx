import { ProjectOverview } from "../overview/ProjectOverview";

/** The project Overview (UI-13, TASK-048): the first view of the Sources tab, from existing APIs only. */
export function ProjectOverviewSlot({ projectId, revisionId }: { projectId: string; revisionId: string | null }) {
  return <ProjectOverview projectId={projectId} revisionId={revisionId} />;
}
