import { useEffect, useRef, useState } from "react";
import { ActionIcon, Button, NavLink, Tooltip } from "@mantine/core";
import { FolderKanban, Plus, Trash2, X } from "lucide-react";
import { Callout, Chip, EmptyState, ErrorState, LoadingState } from "../../design";
import { navigate, useRoute } from "../../app/shell/route";
import { usePolled } from "../uploads/usePolled";
import { createProject, listProjects } from "./api";
import { bumpProjectList, useProjectListVersion } from "./listVersion";
import { ProjectForm } from "./ProjectForm";
import { DeleteProjectDialog } from "./DeleteProjectDialog";
import { clearSelectedProjectIdIf, keyString, projectKeys, type Project } from "./keys";
import { useActionScope, type Failure } from "./scope";
import styles from "./ProjectSidebar.module.css";

/** Left sidebar: project list, switch, create. (Edit lives in the project view; PW-1/PW-8.) */
export function ProjectSidebar() {
  const route = useRoute();
  const version = useProjectListVersion();
  const listKey = keyString(projectKeys.list());
  const { state, reload } = usePolled(
    listKey,
    (signal) => listProjects(signal),
    (page) => page.items.some((p) => p.deletion_state === "deleting"),
    String(version),
  );
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const labelRef = useRef<HTMLParagraphElement | null>(null);
  const deletingSeen = useRef<Set<string>>(new Set());
  const [removed, setRemoved] = useState<ReadonlySet<string>>(new Set());
  const [more, setMore] = useState<{ forKey: string; items: Project[]; next: string | null } | null>(null);
  const [moreError, setMoreError] = useState<Failure | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [createOpen, setCreateOpen] = useState(true);
  const runMore = useActionScope("projects:more");
  const runCreate = useActionScope("projects:create");

  const first = state.kind === "ready" ? state.data : null;
  const extra = first !== null && more !== null && more.forKey === first.items[0]?.project_id ? more : null;
  const items = (first ? [...first.items, ...(extra?.items ?? [])] : []).filter((p) => !removed.has(p.project_id));
  const next = extra ? extra.next : (first?.page.next_cursor ?? null);
  const empty = first !== null && items.length === 0;

  // Return focus to the invoking button; if it is gone (deleted project), to the list label.
  function restoreFocus() {
    window.requestAnimationFrame(() => {
      const el = trigger.current;
      (el !== null && el.isConnected ? el : labelRef.current)?.focus();
    });
  }

  function closeDialog() {
    setDeleteTarget(null);
    restoreFocus();
  }

  function onDeleted(projectId: string, fromDialog = true) {
    clearSelectedProjectIdIf(projectId);
    deletingSeen.current.delete(projectId);
    setRemoved((prev) => (prev.has(projectId) ? prev : new Set(prev).add(projectId)));
    if (fromDialog) setDeleteTarget(null);
    let navigated = false;
    if (openProjectId === projectId) {
      const another = items.find((p) => p.project_id !== projectId && p.deletion_state !== "deleting");
      if (another) navigate({ kind: "project", projectId: another.project_id, section: "sources" });
      else navigate({ kind: "home" });
      navigated = another !== undefined;
    }
    if (fromDialog && !navigated) restoreFocus();
    bumpProjectList();
  }

  // A deletion continued in the background finishes while the dialog is closed: the list refresh
  // no longer contains the project, so clean up selection exactly as the dialog would.
  const firstItems = first?.items ?? null;
  useEffect(() => {
    if (firstItems === null) return;
    const ids = new Set(firstItems.map((p) => p.project_id));
    for (const id of [...deletingSeen.current]) {
      if (!ids.has(id)) onDeleted(id, false);
    }
    for (const p of firstItems) if (p.deletion_state === "deleting") deletingSeen.current.add(p.project_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstItems]);

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
        <p className={styles.label} ref={labelRef} tabIndex={-1}>
          Projects
        </p>
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
            headingOrder={2}
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
                <Tooltip label={p.name} multiline withArrow position="right" openDelay={300} events={{ hover: true, focus: true, touch: false }}>
                  <NavLink
                    component="button"
                    type="button"
                    label={p.name}
                    aria-label={`Open project ${p.name}`}
                    title={p.name}
                    aria-current={active ? "page" : undefined}
                    active={active}
                    classNames={{ root: styles.navRoot, body: styles.navBody, label: styles.navLabel }}
                    leftSection={<FolderKanban size={16} aria-hidden="true" />}
                    onClick={() => navigate({ kind: "project", projectId: p.project_id, section: "sources" })}
                  />
                </Tooltip>
                {p.deletion_state === "deleting" && <Chip spec={{ tone: "warning", icon: Trash2 }} label="Deleting…" />}
                {p.deletion_state === "failed" && <Chip spec={{ tone: "danger", icon: Trash2 }} label="Deletion failed" />}
                <Tooltip label={(p.deletion_state ?? "none") === "none" ? "Delete project" : p.deletion_state === "deleting" ? "Deletion status" : "Retry deletion"} withArrow position="right">
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    className={styles.deleteButton}
                    aria-label={
                      p.deletion_state === "none"
                        ? `Delete project ${p.name}`
                        : p.deletion_state === "deleting"
                          ? `Deletion status of project ${p.name}`
                          : `Retry deleting project ${p.name}`
                    }
                    onClick={(e) => {
                      trigger.current = e.currentTarget;
                      setDeleteTarget(p);
                    }}
                  >
                    <Trash2 size={16} aria-hidden="true" />
                  </ActionIcon>
                </Tooltip>
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
      {deleteTarget !== null && (
        <DeleteProjectDialog
          key={deleteTarget.project_id}
          project={deleteTarget}
          onClose={closeDialog}
          onStateChange={bumpProjectList}
          onDeleted={(id) => onDeleted(id)}
        />
      )}
    </section>
  );
}
