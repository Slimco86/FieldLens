import { useCallback, useEffect, useRef } from "react";
import { Box, Title } from "@mantine/core";
import { Callout, EmptyState } from "../../design";
import { FolderOpen } from "lucide-react";
import { navigate, setHomeNotice, useHomeNotice, useRoute } from "../../app/shell/route";
import { ProjectView } from "./ProjectView";
import { isProjectId, loadSelectedProjectId, saveSelectedProjectId } from "./keys";

const INVALID_SAVED = "The previously open project is no longer valid. Choose a project from the sidebar.";

/** Main-region content: the home view or the open project, selected by the URL (UI-12). */
export function ProjectWorkspace() {
  const route = useRoute();
  const notice = useHomeNotice();

  // On first load an address without a project restores the saved selection (PW-8).
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    if (route.kind !== "home") return;
    const saved = loadSelectedProjectId();
    if (saved === null) return;
    if (!isProjectId(saved)) {
      saveSelectedProjectId(null);
      setHomeNotice(INVALID_SAVED);
      return;
    }
    navigate({ kind: "project", projectId: saved, section: "sources" }, { replace: true });
  }, [route.kind]);

  useEffect(() => {
    if (route.kind === "project") setHomeNotice(null);
  }, [route.kind]);

  const onMissing = useCallback((projectId: string) => {
    saveSelectedProjectId(null);
    setHomeNotice(
      `The previously open project (${projectId}) was not found. It may no longer exist; choose a project from the sidebar.`,
    );
    navigate({ kind: "home" }, { replace: true });
  }, []);

  if (route.kind === "project") {
    return (
      <ProjectView
        key={route.projectId}
        projectId={route.projectId}
        section={route.section}
        onSection={(section) => navigate({ kind: "project", projectId: route.projectId, section })}
        onBack={() => {
          saveSelectedProjectId(null);
          setHomeNotice(null);
          navigate({ kind: "home" });
        }}
        onMissing={onMissing}
      />
    );
  }

  const text = notice ?? (route.kind === "invalid" ? "The project ID in the address is not valid. Choose a project from the sidebar." : null);
  return (
    <section aria-labelledby="projects-title">
      <Title order={3} id="projects-title" tabIndex={-1} mb="md">
        Projects
      </Title>
      {text !== null && (
        <Box mb="md">
          <Callout tone="warning" role="status">
            <p>{text}</p>
          </Callout>
        </Box>
      )}
      <EmptyState title="Select or create a project" icon={<FolderOpen size={28} />}>
        <p>
          A project holds one set of source files and what is reconstructed from them. Choose a project in the sidebar to
          open its Sources, Reconstruction and Explore tabs.
        </p>
      </EmptyState>
    </section>
  );
}
