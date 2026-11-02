import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Checkbox, Fieldset, Table, TextInput } from "@mantine/core";
import { ChevronDown, ChevronUp, Info, Lightbulb, Pencil, UserCheck } from "lucide-react";
import { Callout, ErrorState, LoadingState, StatusChip, EmptyState, TruncatedText, KeyValueList, KeyValue } from "../../design";
import { BulkLabels } from "./BulkLabels";
import {
  CATEGORIES,
  MAX_TAGS,
  MAX_TAG_LENGTH,
  listDocuments,
  retryStorage,
  describeStorageError,
  updateClassification,
  type DocumentCategory,
  type DocumentPage,
  type SourceDocumentItem,
} from "./api";
import { categoryLabel, formatBytes } from "./format";
import { EvidenceToggle, Inspection } from "./EvidencePanel";
import styles from "./shared.module.css";
import { usePolled } from "./usePolled";
import { toFailure, type Failure } from "../projects/scope";

const STORAGE_LABEL: Record<SourceDocumentItem["storage_state"], string> = {
  pending_verification: "Pending verification",
  stored: "Stored (hash-verified)",
  failed: "Failed",
};
const EXTRACTION_LABEL: Record<SourceDocumentItem["extraction_state"], string> = {
  pending_extraction: "Pending extraction (not yet extracted)",
  unsupported: "Unsupported (no reader; not extracted)",
  extracted: "Extracted",
  extracted_with_issues: "Extracted with data-quality findings",
  extraction_failed: "Extraction failed (nothing was extracted)",
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
  const [selected, setSelected] = useState<ReadonlySet<DocumentCategory>>(new Set(doc.classification.user_categories));
  const [tagText, setTagText] = useState(doc.classification.tags.join(", "));
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [saving, setSaving] = useState(false);
  const ctl = useRef<AbortController | null>(null);
  const firstControl = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    firstControl.current?.focus();
  }, []);

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
    <form
      onSubmit={(e) => void onSubmit(e)}
      aria-label={`Edit labels for ${doc.original_filename}`}
      className={styles.stack}
    >
      <p className={styles.note}>Labels are your hints; they are never engineering evidence.</p>
      <Fieldset legend={`Categories for ${doc.original_filename}`}>
        <div className={styles.row}>
          {CATEGORIES.map((c, i) => (
            <Checkbox
              key={c}
              ref={i === 0 ? firstControl : undefined}
              label={categoryLabel(c)}
              checked={selected.has(c)}
              onChange={(e) => {
                const next = new Set(selected);
                if (e.currentTarget.checked) next.add(c);
                else next.delete(c);
                setSelected(next);
              }}
            />
          ))}
        </div>
      </Fieldset>
      <TextInput label="Tags (comma separated)" value={tagText} onChange={(e) => setTagText(e.currentTarget.value)} />
      {problem !== null && (
        <Callout tone="danger" role="alert">
          <p>{problem}</p>
        </Callout>
      )}
      {failure !== null && (
        <Callout tone="danger" role="alert">
          <p>
            {failure.status === 409
              ? "These labels were changed elsewhere since this list loaded. Nothing was saved; reload the list and edit again."
              : `Labels were not saved: ${failure.message}`}
          </p>
          {failure.requestId !== null && <p>Request ID: {failure.requestId}</p>}
        </Callout>
      )}
      <div className={styles.row}>
        <Button type="submit" disabled={saving}>
          Save labels
        </Button>
        <Button type="button" variant="default" onClick={onClose}>
          Cancel editing
        </Button>
      </div>
    </form>
  );
}

const FAILED_DEFAULT = "Failed: stored copy missing or damaged.";

/** Failed storage: the server's message, a Retry that re-verifies the stored bytes, and the re-upload route. */
type RetryOutcome = { ok: boolean; text: string };
function StorageRecovery({
  projectId,
  doc,
  onChanged,
  outcome,
  setOutcome,
}: {
  projectId: string;
  doc: SourceDocumentItem;
  onChanged: () => void;
  outcome: RetryOutcome | null;
  setOutcome: (o: RetryOutcome | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const failed = doc.storage_state === "failed";
  const ctl = useRef<AbortController | null>(null);
  useEffect(() => () => ctl.current?.abort(), []);
  async function retry() {
    ctl.current?.abort();
    const c = new AbortController();
    ctl.current = c;
    setBusy(true);
    setOutcome(null);
    try {
      const res = await retryStorage(projectId, doc.document_id, c.signal);
      if (c.signal.aborted) return;
      setOutcome({ ok: true, text: res.message });
      onChanged();
    } catch (err) {
      if (c.signal.aborted) return;
      setOutcome({ ok: false, text: describeStorageError(err) ?? `Retry failed: ${toFailure(err).message}` });
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  return (
    <div className={`${styles.stack} ${styles.wrapText}`}>
      {failed && (
        <>
          <div className={styles.small}>{doc.storage_message ?? FAILED_DEFAULT}</div>
          <div>
            <Button
              size="compact-sm"
              variant="default"
              disabled={busy}
              aria-label={`Retry storage verification for ${doc.original_filename}`}
              onClick={() => void retry()}
            >
              Retry
            </Button>
          </div>
          <div className={`${styles.small} ${styles.muted}`}>If Retry cannot restore it, re-upload this file with the upload control.</div>
        </>
      )}
      {outcome !== null && (
        <div role={outcome.ok ? "status" : "alert"} className={styles.small}>
          {outcome.text}
        </div>
      )}
    </div>
  );
}

function DocumentRow({
  projectId,
  doc,
  onSaved,
  selected,
  onToggle,
  highlighted,
}: {
  projectId: string;
  doc: SourceDocumentItem;
  onSaved: () => void;
  highlighted: boolean;
  selected: boolean;
  onToggle: (on: boolean) => void;
}) {
  const [retryOutcome, setRetryOutcome] = useState<RetryOutcome | null>(null);
  useEffect(() => {
    if (doc.storage_state !== "failed") setRetryOutcome((o) => (o !== null && !o.ok ? null : o));
  }, [doc.storage_state]);
  const [editing, setEditing] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const detailId = `details-${doc.document_id}`;
  const [inspecting, setInspecting] = useState(false);
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
    <>
      <Table.Tr
        id={`source-file-${doc.document_id}`}
        tabIndex={highlighted ? -1 : undefined}
        className={selected || highlighted ? styles.selected : undefined}
      >
        <Table.Td>
          <Checkbox
            aria-label={`Select ${doc.original_filename}`}
            checked={selected}
            onChange={(e) => onToggle(e.currentTarget.checked)}
          />
        </Table.Td>
        <Table.Td>
          <strong>
            <TruncatedText value={doc.original_filename} label="file name" maxCh={28} />
          </strong>
          {doc.replaces_document_id !== null && doc.replaces_document_id !== undefined && (
            <div className={`${styles.small} ${styles.muted}`}>
              This file explicitly replaces document <code>{doc.replaces_document_id}</code>.
            </div>
          )}
        </Table.Td>
        <Table.Td>
          <StatusChip kind="storage" value={doc.storage_state} label={STORAGE_LABEL[doc.storage_state]} />
          {(doc.storage_state === "failed" || (retryOutcome !== null && retryOutcome.ok)) && (
            <StorageRecovery projectId={projectId} doc={doc} onChanged={onSaved} outcome={doc.storage_state === "failed" || retryOutcome?.ok === true ? retryOutcome : null} setOutcome={setRetryOutcome} />
          )}
        </Table.Td>
        <Table.Td>
          {doc.storage_state === "failed" ? (
            <span className={styles.muted}>Not available: stored copy missing or damaged</span>
          ) : (
            <>
              <StatusChip kind="extraction" value={doc.extraction_state} label={doc.extraction_state === "unsupported" && doc.format_family === "pdf" ? "No native parser; model processing available" : EXTRACTION_LABEL[doc.extraction_state]} />
              {doc.processing_detail !== null && doc.processing_detail !== undefined && (
                <div className={`${styles.small} ${styles.muted}`}>{doc.processing_detail}</div>
              )}
            </>
          )}
        </Table.Td>
        <Table.Td>
          <div>
            <UserCheck size={14} aria-hidden="true" /> {joinCategories(c.user_categories)}
          </div>
          <div className={`${styles.small} ${styles.muted}`}>Confirmed by you ({ORIGIN_LABEL[c.categories_origin]})</div>
        </Table.Td>
        <Table.Td>
          <div>
            <Lightbulb size={14} aria-hidden="true" /> {joinCategories(c.suggested_categories)}
          </div>
          <div className={`${styles.small} ${styles.muted}`}>
            Suggestion only, not confirmed (method {c.classification_method})
          </div>
        </Table.Td>
        <Table.Td>{c.tags.length === 0 ? <span className={styles.muted}>none</span> : c.tags.join(", ")}</Table.Td>
        <Table.Td>
          <div className={styles.row}>
            <Button
              size="compact-sm"
              variant="default"
              id={editId}
              ref={editButton}
              leftSection={<Pencil size={14} aria-hidden="true" />}
              aria-label={`Edit labels for ${doc.original_filename}`}
              aria-expanded={editing}
              onClick={() => (editing ? close() : setEditing(true))}
            >
              Edit labels
            </Button>
            <Button
              size="compact-sm"
              variant="default"
              leftSection={showDetails ? <ChevronUp size={14} aria-hidden="true" /> : <Info size={14} aria-hidden="true" />}
              aria-label={`${showDetails ? "Hide" : "Show"} details for ${doc.original_filename}`}
              aria-expanded={showDetails}
              aria-controls={detailId}
              onClick={() => setShowDetails(!showDetails)}
            >
              Details
            </Button>
            <EvidenceToggle
              doc={doc}
              open={inspecting}
              onToggle={() => setInspecting(!inspecting)}
              icon={inspecting ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
            />
          </div>
        </Table.Td>
      </Table.Tr>
      {(editing || inspecting || showDetails) && (
        <Table.Tr id={detailId}>
          <Table.Td colSpan={8} className={styles.detailCell}>
            <div className={styles.stack}>
              {showDetails && (
                <KeyValueList compact>
                  <KeyValue term="SHA-256">
                    <TruncatedText value={doc.sha256} label="SHA-256" maxCh={72} mono>
                      <code>{doc.sha256}</code>
                    </TruncatedText>
                  </KeyValue>
                  <KeyValue term="Size">{formatBytes(doc.size_bytes)} ({doc.size_bytes} bytes)</KeyValue>
                  <KeyValue term="Detected format">
                    {doc.format_family}
                    {doc.detected_media_type !== null && doc.detected_media_type !== undefined && <> ({doc.detected_media_type})</>}
                    {" "}— detected from file signature, not an engineering claim
                  </KeyValue>
                  <KeyValue term="Document ID">
                    <TruncatedText value={doc.document_id} label="document ID" maxCh={40} mono />
                  </KeyValue>
                  <KeyValue term="Source revision ID">
                    <TruncatedText value={doc.source_revision_id} label="source revision ID" maxCh={40} mono />
                  </KeyValue>
                  <KeyValue term="Labels version">{c.metadata_version}</KeyValue>
                </KeyValueList>
              )}
              {editing && (
                <ClassificationEditor
                  projectId={projectId}
                  doc={doc}
                  onSaved={() => {
                    onSaved();
                    close();
                  }}
                  onClose={close}
                />
              )}
              {inspecting && <Inspection projectId={projectId} doc={doc} />}
            </div>
          </Table.Td>
        </Table.Tr>
      )}
    </>
  );
}

interface ListProps {
  projectId: string;
  revisionId: string;
  /** Changes when the revision's status/counts change, forcing a silent refresh. */
  version: string;
  polling: boolean;
  /** A file the Reconstruction tab asked to show: its row is scrolled to, focused and marked when loaded. */
  focusDocumentId?: string | null;
}

export function DocumentList({ projectId, revisionId, version, polling, focusDocumentId = null }: ListProps) {
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
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set());
  const ready = state.kind === "ready";
  useEffect(() => {
    if (focusDocumentId === null || !ready) return;
    const row = document.getElementById(`source-file-${focusDocumentId}`);
    if (row === null) return;
    row.scrollIntoView?.({ block: "center" });
    row.focus();
  }, [focusDocumentId, ready]);

  if (state.kind === "loading") return <LoadingState label="Loading files…" status />;
  if (state.kind === "error") {
    return (
      <ErrorState
        message={`The file list could not be loaded: ${state.error.message}`}
        requestId={state.error.requestId}
        onRetry={reload}
        retryLabel="Retry loading files"
      />
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

  const selectedDocs = items.filter((d) => selectedIds.has(d.document_id));
  const allSelected = items.length > 0 && selectedDocs.length === items.length;

  if (items.length === 0) {
    return (
      <EmptyState title="No files">
        <p>This revision has no files{polling ? " yet; it is still being processed" : ""}.</p>
      </EmptyState>
    );
  }
  return (
    <div className={styles.stack}>
      {state.refreshError !== null && (
        <Callout tone="warning" role="alert">
          <p>Refreshing the file list failed: {state.refreshError.message}</p>
        </Callout>
      )}
      <BulkLabels
        projectId={projectId}
        docs={selectedDocs}
        onClear={() => setSelectedIds(new Set())}
        onFinished={(failedIds, changed) => {
          setSelectedIds(new Set(failedIds));
          if (changed || failedIds.length > 0) reload();
        }}
      />
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- keyboard-scrollable region */}
      <div role="region" aria-label="Files table" tabIndex={0} className={styles.scroll}>
        <Table aria-label="Files in this source revision" layout="fixed">
          <Table.Thead>
            <Table.Tr>
              <Table.Th scope="col" className={styles.colSelect}>
                <Checkbox
                  aria-label="Select all visible files"
                  checked={allSelected}
                  indeterminate={selectedIds.size > 0 && !allSelected}
                  onChange={(e) => {
                    const on = e.currentTarget.checked;
                    setSelectedIds(on ? new Set(items.map((d) => d.document_id)) : new Set());
                  }}
                />
              </Table.Th>
              <Table.Th scope="col" className={styles.colFile}>File</Table.Th>
              <Table.Th scope="col" className={styles.colStorage}>Storage</Table.Th>
              <Table.Th scope="col" className={styles.colExtraction}>Extraction</Table.Th>
              <Table.Th scope="col" className={styles.colLabels}>Your labels</Table.Th>
              <Table.Th scope="col" className={styles.colSuggested}>Suggested labels</Table.Th>
              <Table.Th scope="col" className={styles.colTags}>Tags</Table.Th>
              <Table.Th scope="col" className={styles.colActions}>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((d) => (
              <DocumentRow
                key={d.document_id}
                projectId={projectId}
                doc={d}
                onSaved={reload}
                highlighted={focusDocumentId === d.document_id}
                selected={selectedIds.has(d.document_id)}
                onToggle={(on) => {
                  const next = new Set(selectedIds);
                  if (on) next.add(d.document_id);
                  else next.delete(d.document_id);
                  setSelectedIds(next);
                }}
              />
            ))}
          </Table.Tbody>
        </Table>
      </div>
      {cursor !== null && (
        <div>
          <Button variant="default" size="xs" disabled={loadingMore} onClick={() => void loadMore()}>
            Load more files
          </Button>
        </div>
      )}
      {moreError !== null && (
        <Callout tone="danger" role="alert">
          <p>More files could not be loaded: {moreError.message}</p>
        </Callout>
      )}
    </div>
  );
}
