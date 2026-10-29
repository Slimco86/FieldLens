import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  CATEGORIES,
  MAX_TAGS,
  MAX_TAG_LENGTH,
  listDocuments,
  updateClassification,
  type DocumentCategory,
  type DocumentPage,
  type SourceDocumentItem,
} from "./api";
import { categoryLabel, formatBytes } from "./format";
import { usePolled } from "./usePolled";
import { toFailure, type Failure } from "../projects/scope";

const STORAGE_LABEL: Record<SourceDocumentItem["storage_state"], string> = {
  pending_verification: "Pending verification",
  stored: "Stored (hash-verified)",
  quarantined: "Quarantined",
};
const EXTRACTION_LABEL: Record<SourceDocumentItem["extraction_state"], string> = {
  pending_extraction: "Pending extraction (not yet extracted)",
  unsupported: "Unsupported (no reader; not extracted)",
};
const ORIGIN_LABEL: Record<SourceDocumentItem["classification"]["categories_origin"], string> = {
  none: "no labels set",
  upload_hint: "from your upload hint",
  user_override: "set by you",
};

const joinCategories = (list: readonly DocumentCategory[]): string =>
  list.length === 0 ? "none" : list.map(categoryLabel).join(", ");

export function parseTags(raw: string): { tags: string[]; problem: string | null } {
  const tags = [
    ...new Set(
      raw
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t !== ""),
    ),
  ];
  if (tags.length > MAX_TAGS) return { tags, problem: `At most ${MAX_TAGS} tags are allowed.` };
  const long = tags.find((t) => t.length > MAX_TAG_LENGTH);
  if (long !== undefined) return { tags, problem: `A tag may have at most ${MAX_TAG_LENGTH} characters.` };
  return { tags, problem: null };
}

interface EditorProps {
  projectId: string;
  doc: SourceDocumentItem;
  onSaved: () => void;
  onClose: () => void;
}

function ClassificationEditor({ projectId, doc, onSaved, onClose }: EditorProps) {
  const ids = useId();
  const [selected, setSelected] = useState<ReadonlySet<DocumentCategory>>(new Set(doc.classification.user_categories));
  const [tagText, setTagText] = useState(doc.classification.tags.join(", "));
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [saving, setSaving] = useState(false);
  const ctl = useRef<AbortController | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const parsed = parseTags(tagText);
    if (parsed.problem !== null) {
      setProblem(parsed.problem);
      return;
    }
    setProblem(null);
    setFailure(null);
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setSaving(true);
    try {
      await updateClassification(
        projectId,
        doc.document_id,
        {
          categories: CATEGORIES.filter((k) => selected.has(k)),
          tags: parsed.tags,
          expected_metadata_version: doc.classification.metadata_version,
        },
        c.signal,
      );
      if (c.signal.aborted) return;
      onSaved();
    } catch (err) {
      if (c.signal.aborted) return;
      setFailure(toFailure(err));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(e) => void onSubmit(e)} aria-label={`Edit labels for ${doc.original_filename}`}>
      <p>Labels are your hints; they are never engineering evidence.</p>
      <fieldset>
        <legend>Categories for {doc.original_filename}</legend>
        {CATEGORIES.map((c) => (
          <label key={c} className="check">
            <input
              type="checkbox"
              checked={selected.has(c)}
              onChange={(e) => {
                const next = new Set(selected);
                if (e.target.checked) next.add(c);
                else next.delete(c);
                setSelected(next);
              }}
            />{" "}
            {categoryLabel(c)}
          </label>
        ))}
      </fieldset>
      <p>
        <label htmlFor={`${ids}-tags`}>Tags (comma separated)</label>{" "}
        <input id={`${ids}-tags`} value={tagText} onChange={(e) => setTagText(e.target.value)} />
      </p>
      {problem !== null && <p role="alert">{problem}</p>}
      {failure !== null && (
        <div role="alert">
          <p>
            {failure.status === 409
              ? "These labels were changed elsewhere since this list loaded. Nothing was saved; reload the list and edit again."
              : `Labels were not saved: ${failure.message}`}
          </p>
          {failure.requestId !== null && <p>Request ID: {failure.requestId}</p>}
        </div>
      )}
      <button type="submit" disabled={saving}>
        Save labels
      </button>{" "}
      <button type="button" onClick={onClose}>
        Cancel editing
      </button>
    </form>
  );
}

function DocumentRow({
  projectId,
  doc,
  onSaved,
}: {
  projectId: string;
  doc: SourceDocumentItem;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const c = doc.classification;
  const editId = `edit-${doc.document_id}`;
  const editButton = useRef<HTMLButtonElement | null>(null);
  const restoreFocus = useRef(false);
  useEffect(() => {
    if (!editing && restoreFocus.current) {
      restoreFocus.current = false;
      editButton.current?.focus();
    }
  }, [editing]);
  const close = () => {
    restoreFocus.current = true;
    setEditing(false);
  };
  return (
    <li className="document">
      <h6>{doc.original_filename}</h6>
      <dl>
        <dt>Storage</dt>
        <dd>{STORAGE_LABEL[doc.storage_state]}</dd>
        <dt>Extraction</dt>
        <dd>{EXTRACTION_LABEL[doc.extraction_state]}</dd>
        {doc.processing_detail !== null && doc.processing_detail !== undefined && (
          <>
            <dt>Processing detail</dt>
            <dd>{doc.processing_detail}</dd>
          </>
        )}
        <dt>Size</dt>
        <dd>{formatBytes(doc.size_bytes)}</dd>
        <dt>SHA-256</dt>
        <dd>
          <code>{doc.sha256}</code>
        </dd>
        <dt>Detected format</dt>
        <dd>
          {doc.format_family}
          {doc.detected_media_type !== null && doc.detected_media_type !== undefined && <> ({doc.detected_media_type})</>}{" "}
          — detected from file signature, not an engineering claim
        </dd>
        <dt>Your labels</dt>
        <dd>
          {joinCategories(c.user_categories)} ({ORIGIN_LABEL[c.categories_origin]}); tags:{" "}
          {c.tags.length === 0 ? "none" : c.tags.join(", ")}
        </dd>
        <dt>Suggested labels</dt>
        <dd>
          {joinCategories(c.suggested_categories)} (suggestion only, not confirmed; method {c.classification_method})
        </dd>
        {doc.replaces_document_id !== null && doc.replaces_document_id !== undefined && (
          <>
            <dt>Replaces</dt>
            <dd>
              This file explicitly replaces document <code>{doc.replaces_document_id}</code>.
            </dd>
          </>
        )}
      </dl>
      {editing ? (
        <ClassificationEditor
          projectId={projectId}
          doc={doc}
          onSaved={() => {
            onSaved();
            close();
          }}
          onClose={close}
        />
      ) : (
        <button type="button" id={editId} ref={editButton} onClick={() => setEditing(true)}>
          Edit labels for {doc.original_filename}
        </button>
      )}
    </li>
  );
}

interface ListProps {
  projectId: string;
  revisionId: string;
  /** Changes when the revision's status/counts change, forcing a silent refresh. */
  version: string;
  polling: boolean;
}

export function DocumentList({ projectId, revisionId, version, polling }: ListProps) {
  const { state, reload } = usePolled<DocumentPage>(
    `docs/${projectId}/${revisionId}`,
    (signal) => listDocuments(projectId, revisionId, signal),
    () => polling,
    version,
  );
  const [more, setMore] = useState<{ version: string; items: SourceDocumentItem[]; cursor: string | null } | null>(null);
  const [moreError, setMoreError] = useState<Failure | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const ctl = useRef<AbortController | null>(null);

  if (state.kind === "loading") return <p role="status">Loading files…</p>;
  if (state.kind === "error") {
    return (
      <div role="alert">
        <p>The file list could not be loaded: {state.error.message}</p>
        {state.error.requestId !== null && <p>Request ID: {state.error.requestId}</p>}
        <button type="button" onClick={reload}>
          Retry loading files
        </button>
      </div>
    );
  }
  const page = state.data;
  const extra = more !== null && more.version === version ? more : null;
  const items = [...page.items, ...(extra?.items ?? [])];
  const cursor = extra !== null ? extra.cursor : (page.page.next_cursor ?? null);

  async function loadMore() {
    if (cursor === null) return;
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const next = await listDocuments(projectId, revisionId, c.signal, cursor);
      if (c.signal.aborted) return;
      setMore({ version, items: [...(extra?.items ?? []), ...next.items], cursor: next.page.next_cursor ?? null });
    } catch (err) {
      if (!c.signal.aborted) setMoreError(toFailure(err));
    } finally {
      if (!c.signal.aborted) setLoadingMore(false);
    }
  }

  if (items.length === 0) {
    return <p>This revision has no files{polling ? " yet; it is still being processed" : ""}.</p>;
  }
  return (
    <div>
      {state.refreshError !== null && <p role="alert">Refreshing the file list failed: {state.refreshError.message}</p>}
      <ul className="documents" aria-label="Files in this source revision">
        {items.map((d) => (
          <DocumentRow key={d.document_id} projectId={projectId} doc={d} onSaved={reload} />
        ))}
      </ul>
      {cursor !== null && (
        <p>
          <button type="button" disabled={loadingMore} onClick={() => void loadMore()}>
            Load more files
          </button>
        </p>
      )}
      {moreError !== null && <p role="alert">More files could not be loaded: {moreError.message}</p>}
    </div>
  );
}
