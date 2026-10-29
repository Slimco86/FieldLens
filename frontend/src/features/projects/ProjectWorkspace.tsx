import { useCallback, useState } from "react";
import { ProjectList } from "./ProjectList";
import { ProjectView } from "./ProjectView";
import { isProjectId, loadSelectedProjectId, saveSelectedProjectId, type Section } from "./keys";

type View = { kind: "list"; notice: string | null } | { kind: "project"; projectId: string; section: Section };

function initialView(): View {
  const saved = loadSelectedProjectId();
  if (saved === null) return { kind: "list", notice: null };
  if (!isProjectId(saved)) {
    saveSelectedProjectId(null);
    return { kind: "list", notice: "The previously open project is no longer valid. Choose a project from the list." };
  }
  return { kind: "project", projectId: saved, section: "sources" };
}

export function ProjectWorkspace() {
  const [view, setView] = useState<View>(initialView);

  const onMissing = useCallback((projectId: string) => {
    saveSelectedProjectId(null);
    setView((current) =>
      current.kind === "project" && current.projectId === projectId
        ? {
            kind: "list",
            notice: `The previously open project (${projectId}) was not found. It may no longer exist; choose a project from the list.`,
          }
        : current,
    );
  }, []);

  if (view.kind === "list") {
    return (
      <ProjectList
        notice={view.notice}
        onOpen={(projectId) => setView({ kind: "project", projectId, section: "sources" })}
      />
    );
  }
  return (
    <ProjectView
      key={view.projectId}
      projectId={view.projectId}
      section={view.section}
      onSection={(section) => setView({ ...view, section })}
      onBack={() => {
        saveSelectedProjectId(null);
        setView({ kind: "list", notice: null });
      }}
      onMissing={onMissing}
    />
  );
}
