import { useEffect, useRef, useState } from "react";
import { Button, Checkbox, Fieldset, NativeSelect } from "@mantine/core";
import { CircleAlert, CircleCheck, Minus } from "lucide-react";
import { Callout } from "../../design";
import { CATEGORIES, updateClassification, type DocumentCategory, type SourceDocumentItem } from "./api";
import { categoryLabel } from "./format";
import styles from "./shared.module.css";
import { toFailure } from "../projects/scope";

export type BulkMode = "add" | "remove" | "set";

const MODE_LABEL: Record<BulkMode, string> = {
  add: "Add these categories to each document",
  remove: "Remove these categories from each document",
  set: "Set exactly these categories on each document (replaces the existing ones)",
};

/** The categories one document ends up with; the result is always in canonical order. */
export function nextCategories(
  current: readonly DocumentCategory[],
  mode: BulkMode,
  chosen: ReadonlySet<DocumentCategory>,
): DocumentCategory[] {
  const have = new Set(current);
  const result = CATEGORIES.filter((c) => {
    if (mode === "set") return chosen.has(c);
    if (mode === "add") return have.has(c) || chosen.has(c);
    return have.has(c) && !chosen.has(c);
  });
  return result;
}

const sameSet = (a: readonly string[], b: readonly string[]): boolean => a.length === b.length && a.every((x) => b.includes(x));

interface Outcome {
  documentId: string;
  filename: string;
  status: "saved" | "unchanged" | "failed";
  message: string;
}

type Phase =
  | { kind: "compose" }
  | { kind: "confirm" }
  | { kind: "running"; done: number; total: number }
  | { kind: "done"; outcomes: Outcome[] };

interface Props {
  projectId: string;
  /** The currently selected documents (latest loaded copy). */
  docs: readonly SourceDocumentItem[];
  /** Called after a run: the ids that failed (to stay selected) and whether anything changed on the server. */
  onFinished: (failedIds: string[], changed: boolean) => void;
  onClear: () => void;
}

/** One confirmation, then one existing per-document classification call each; every outcome is reported. */
export function BulkLabels({ projectId, docs, onFinished, onClear }: Props) {
  const [mode, setMode] = useState<BulkMode>("add");
  const [chosen, setChosen] = useState<ReadonlySet<DocumentCategory>>(new Set());
  const [phase, setPhase] = useState<Phase>({ kind: "compose" });
  const ctl = useRef<AbortController | null>(null);
  const confirmRegion = useRef<HTMLDivElement | null>(null);
  const resultRegion = useRef<HTMLDivElement | null>(null);
  useEffect(() => () => ctl.current?.abort(), []);
  useEffect(() => {
    if (phase.kind === "confirm") confirmRegion.current?.focus();
    if (phase.kind === "done") resultRegion.current?.focus();
  }, [phase.kind]);

  if (docs.length === 0 && phase.kind === "compose") return null;

  const emptyChange = mode !== "set" && chosen.size === 0;
  const chosenText = chosen.size === 0 ? "no categories" : CATEGORIES.filter((c) => chosen.has(c)).map(categoryLabel).join(", ");

  async function run() {
    const snapshot = [...docs];
    const c = new AbortController();
    ctl.current = c;
    const outcomes: Outcome[] = [];
    setPhase({ kind: "running", done: 0, total: snapshot.length });
    for (const doc of snapshot) {
      const target = nextCategories(doc.classification.user_categories, mode, chosen);
      if (sameSet(target, doc.classification.user_categories)) {
        outcomes.push({ documentId: doc.document_id, filename: doc.original_filename, status: "unchanged", message: "Already had these labels; nothing sent." });
      } else {
        try {
          await updateClassification(
            projectId,
            doc.document_id,
            { categories: target, tags: doc.classification.tags, expected_metadata_version: doc.classification.metadata_version },
            c.signal,
          );
          outcomes.push({ documentId: doc.document_id, filename: doc.original_filename, status: "saved", message: "Labels saved." });
        } catch (err) {
          if (c.signal.aborted) return;
          const f = toFailure(err);
          outcomes.push({
            documentId: doc.document_id,
            filename: doc.original_filename,
            status: "failed",
            message:
              f.status === 409
                ? "Not saved: this document's labels were changed elsewhere. The list was reloaded; try again."
                : `Not saved: ${f.message}`,
          });
        }
      }
      if (c.signal.aborted) return;
      setPhase({ kind: "running", done: outcomes.length, total: snapshot.length });
    }
    setPhase({ kind: "done", outcomes });
    onFinished(
      outcomes.filter((o) => o.status === "failed").map((o) => o.documentId),
      outcomes.some((o) => o.status === "saved"),
    );
  }

  if (phase.kind === "done") {
    const saved = phase.outcomes.filter((o) => o.status === "saved").length;
    const unchanged = phase.outcomes.filter((o) => o.status === "unchanged").length;
    const failed = phase.outcomes.filter((o) => o.status === "failed");
    return (
      <Callout tone={failed.length > 0 ? "warning" : "success"} role="status" tabIndex={-1} elementRef={resultRegion}>
        <p>
          Bulk labels finished: {saved} saved, {unchanged} unchanged, {failed.length} failed of {phase.outcomes.length} document(s).
          {failed.length > 0 && " The failed documents stay selected so you can retry."}
        </p>
        <ul className={styles.plainList} aria-label="Bulk label results">
          {phase.outcomes.map((o) => (
            <li key={o.documentId}>
              {o.status === "saved" && <CircleCheck size={14} aria-hidden="true" />}
              {o.status === "unchanged" && <Minus size={14} aria-hidden="true" />}
              {o.status === "failed" && <CircleAlert size={14} aria-hidden="true" />}{" "}
              <strong>{o.filename}</strong>: {o.status === "failed" ? "Failed. " : o.status === "saved" ? "Saved. " : "Unchanged. "}
              {o.message}
            </li>
          ))}
        </ul>
        <div className={styles.row}>
          <Button size="compact-sm" variant="default" onClick={() => setPhase({ kind: "compose" })}>
            Dismiss results
          </Button>
        </div>
      </Callout>
    );
  }

  return (
    <Fieldset legend={`Bulk labels for ${docs.length} selected file(s)`} className={styles.bulkBar}>
      <div className={styles.stack}>
        <p className={styles.note}>
          Categories are your hints, never engineering evidence. Tags are left unchanged. Each document is saved on its own.
        </p>
        <NativeSelect
          label="Bulk action"
          value={mode}
          disabled={phase.kind !== "compose"}
          data={(Object.keys(MODE_LABEL) as BulkMode[]).map((m) => ({ value: m, label: MODE_LABEL[m] }))}
          onChange={(e) => setMode(e.currentTarget.value as BulkMode)}
        />
        <Fieldset legend="Categories" disabled={phase.kind !== "compose"}>
          <div className={styles.row}>
            {CATEGORIES.map((c) => (
              <Checkbox
                key={c}
                label={categoryLabel(c)}
                checked={chosen.has(c)}
                onChange={(e) => {
                  const next = new Set(chosen);
                  if (e.currentTarget.checked) next.add(c);
                  else next.delete(c);
                  setChosen(next);
                }}
              />
            ))}
          </div>
        </Fieldset>
        {phase.kind === "confirm" && (
          <Callout tone="warning" role="alert" tabIndex={-1} elementRef={confirmRegion}>
            <p>
              {MODE_LABEL[mode]}: {chosenText}. This changes {docs.length} document(s), one request each. Continue?
            </p>
            <div className={styles.row}>
              <Button size="compact-sm" onClick={() => void run()}>
                Confirm bulk change for {docs.length} document(s)
              </Button>
              <Button size="compact-sm" variant="default" onClick={() => setPhase({ kind: "compose" })}>
                Cancel bulk change
              </Button>
            </div>
          </Callout>
        )}
        {phase.kind === "running" && (
          <p role="status">
            Saving labels: {phase.done} of {phase.total} document(s) processed…
          </p>
        )}
        <div className={styles.row}>
          <Button
            size="compact-sm"
            disabled={emptyChange || phase.kind !== "compose"}
            onClick={() => setPhase({ kind: "confirm" })}
          >
            Review bulk change
          </Button>
          <Button size="compact-sm" variant="default" disabled={phase.kind === "running"} onClick={onClear}>
            Clear selection
          </Button>
          {emptyChange && <span className={`${styles.small} ${styles.muted}`}>Choose at least one category to add or remove.</span>}
        </div>
      </div>
    </Fieldset>
  );
}
