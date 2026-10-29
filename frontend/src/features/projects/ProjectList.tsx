import { useState } from "react";
import { createProject, listProjects } from "./api";
import { ProjectForm } from "./ProjectForm";
import { keyString, projectKeys, type Project } from "./keys";
import { useActionScope, useScopedResource, type Failure } from "./scope";

interface Props {
  notice: string | null;
  onOpen: (projectId: string) => void;
}

export function ProjectList({ notice, onOpen }: Props) {
  const listKey = keyString(projectKeys.list());
  const { state, reload } = useScopedResource(listKey, (signal) => listProjects(signal));
  const [more, setMore] = useState<{ forKey: string; items: Project[]; next: string | null } | null>(null);
  const [moreError, setMoreError] = useState<Failure | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const runMore = useActionScope("projects:more");
  const runCreate = useActionScope("projects:create");

  const first = state.kind === "ready" ? state.data : null;
  const extra = first !== null && more !== null && more.forKey === first.items[0]?.project_id ? more : null;
  const items = first ? [...first.items, ...(extra?.items ?? [])] : [];
  const next = extra ? extra.next : (first?.page.next_cursor ?? null);

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

  return (
    <section aria-labelledby="projects-title">
      <h3 id="projects-title" tabIndex={-1}>
        Projects
      </h3>
      {notice && <p className="notice" role="status">{notice}</p>}
      {state.kind === "loading" && <p aria-live="polite">Loading projects…</p>}
      {state.kind === "error" && (
        <div role="alert">
          <p>Projects could not be loaded: {state.error.message}</p>
          {state.error.requestId && <p>Request ID: {state.error.requestId}</p>}
          <button type="button" onClick={reload}>
            Retry loading projects
          </button>
        </div>
      )}
      {state.kind === "ready" && items.length === 0 && (
        <p>No projects yet. Create the first project below.</p>
      )}
      {items.length > 0 && (
        <ul className="projects" aria-label="Projects">
          {items.map((p) => (
            <li key={p.project_id}>
              <strong>{p.name}</strong>
              <p>{p.description === "" ? "No description." : p.description}</p>
              <button type="button" onClick={() => onOpen(p.project_id)}>
                Open project {p.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {moreError && <p role="alert">More projects could not be loaded: {moreError.message}</p>}
      {next !== null && (
        <button type="button" disabled={loadingMore} onClick={() => void loadMore()}>
          Load more projects
        </button>
      )}
      <ProjectForm
        title="Create project"
        submitLabel="Create project"
        initial={{ name: "", description: "" }}
        resetOnSuccess
        submit={(values) => runCreate((signal) => createProject(values, signal))}
        onSaved={reload}
      />
    </section>
  );
}
