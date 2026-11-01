/**
 * Reserved place for the project Overview (UI-13, TASK-048): counts, wells/wellbores, series and
 * data-quality summary, built from existing project APIs only. It renders nothing until that
 * feature exists, so no empty or invented panel appears at the top of the Sources tab.
 */
export function ProjectOverviewSlot({ projectId }: { projectId: string }): null {
  void projectId; // the Overview will be keyed by project
  return null;
}
