import { useEffect, useState } from "react";
import { Button, NavLink } from "@mantine/core";
import { FolderKanban, Plus, X } from "lucide-react";
import { Callout, EmptyState, ErrorState, LoadingState } from "../../design";
import { navigate, useRoute } from "../../app/shell/route";
import { usePolled } from "../uploads/usePolled";
import { createProject, listProjects } from "./api";
import { bumpProjectList, useProjectListVersion } from "./listVersion";
import { ProjectForm } from "./ProjectForm";
import { keyString, projectKeys, type Project } from "./keys";
import { useActionScope, type Failure } from "./scope";
import styles from "./ProjectSidebar.module.css";

/** Left sidebar: project list, switch, create. (Edit lives in the project view; PW-1/PW-8.) */
export function ProjectSidebar() {
  const route = useRoute();
  const version = useProjectListVersion();
  const listKey = keyString(projectKeys.list());
  const { state, reload } = usePolled(listKey, (signal) => listProjects(signal), () => false, String(version));
  const [more, setMore] = useState<{ forKey: string; items: Project[]; next: string | null } | null>(null);
  const [moreError, setMoreError] = useState<Failure | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [createOpen, setCreateOpen] = useState(true);
  const runMore = useActionScope("projects:more");
  const runCreate = useActionScope("projects:create");

  const first = state.kind === "ready" ? state.data : null;
  const extra = first !== null && more !== null && more.forKey === first.items[0]?.project_id ? more : null;
  const items = first ? [...first.items, ...(extra?.items ?? [])] : [];
  const next = extra ? extra.next : (first?.page.next_cursor ?? null);
  const empty = first !== null && items.length === 0;

  // The create form is open on the home view; opening a project folds it away (one "Name" field at a time).
  const openProjectId = route.kind === "project" ? route.projectId : null;
  useEffect(() => {
    setCreateOpen(openProjectId === null);
  }, [openProjectId]);

  async function loadMore() {
    if (next === null || first === null) return;
    setLoadingMore(true);
    setMoreError(null);
    const outcome = await runMore((signal) => listProjects(signal, next));
    if (outcome.status === "stale") return;
    setLoadingMore(false);
    if (outcome.status === "error") {
      setMoreError(outcome.error);
      return;
    }
    const anchor = first.items[0]?.project_id ?? "";
    setMore({
      forKey: anchor,
      items: [...(extra?.items ?? []), ...outcome.value.items],
      next: outcome.value.page.next_cursor,
    });
  }

  const formOpen = createOpen;
  return (
    <section aria-label="Project management">
      <div className={styles.head}>
        <p className={styles.label}>Projects</p>
        <Button
          size="compact-sm"
          variant={formOpen ? "default" : "light"}
          leftSection={formOpen ? <X size={14} aria-hidden="true" /> : <Plus size={14} aria-hidden="true" />}
          aria-expanded={formOpen}
          onClick={() => setCreateOpen(!formOpen)}
        >
          {formOpen ? "Close form" : "New project"}
        </Button>
      </div>
      {formOpen && (
        <div className={styles.create}>
          <ProjectForm
            title="Create project"
            submitLabel="Create project"
            initial={{ name: "", description: "" }}
            resetOnSuccess
            submit={(values) => runCreate((signal) => createProject(values, signal))}
            onSaved={bumpProjectList}
          />
        </div>
      )}
      {state.kind === "loading" && <LoadingState label="Loading projects…" />}
      {state.kind === "error" && (
        <ErrorState
          message={`Projects could not be loaded: ${state.error.message}`}
          requestId={state.error.requestId}
          onRetry={reload}
          retryLabel="Retry loading projects"
        />
      )}
      {state.kind === "ready" && state.refreshError !== null && (
        <Callout tone="warning" role="alert">
          <p>Refreshing the project list failed: {state.refreshError.message}</p>
        </Callout>
      )}
      {empty && <EmptyState title="No projects yet.">Choose “New project” above to create the first one.</EmptyState>}
      {items.length > 0 && (
        <ul className={styles.list} aria-label="Projects">
          {items.map((p) => {
            const active = openProjectId === p.project_id;
            return (
              <li key={p.project_id} className={styles.item} data-active={active}>
                <NavLink
                  component="button"
                  type="button"
                  label={p.name}
                  aria-label={`Open project ${p.name}`}
                  aria-current={active ? "page" : undefined}
                  active={active}
                  leftSection={<FolderKanban size={16} aria-hidden="true" />}
                  onClick={() => navigate({ kind: "project", projectId: p.project_id, section: "sources" })}
                />
              </li>
            );
          })}
        </ul>
      )}
      {moreError && (
        <Callout tone="danger" role="alert">
          <p>More projects could not be loaded: {moreError.message}</p>
        </Callout>
      )}
      {next !== null && (
        <div className={styles.more}>
          <Button variant="default" size="xs" disabled={loadingMore} onClick={() => void loadMore()}>
            Load more projects
          </Button>
        </div>
      )}
    </section>
  );
}
