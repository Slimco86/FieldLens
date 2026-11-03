import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { routeHash } from "../../app/shell/route";
import { isPdfSource } from "./content";
import styles from "./SourceLink.module.css";

// The viewer chunk is fetched on first open only.
const DocumentViewer = lazy(() => import("./DocumentViewer"));

export interface SourceLinkProps {
  projectId: string;
  documentId: string;
  filename?: string | null | undefined;
  /** 1-based page the PDF opens at. */
  page?: number | null | undefined;
  /** e.g. "page 3, table 2, row 5". */
  locator?: string | null | undefined;
  /** Readable statement; shown as quoted text. */
  statement?: string | null | undefined;
  /** Detected format family; without it the file name's extension decides. */
  format?: string | null | undefined;
  /** Non-PDF sources keep the jump to the Sources row; without it the link goes to the Sources tab. */
  onOpenSource?: ((documentId: string) => void) | undefined;
  /** Hide the locator/statement text (the caller shows its own). */
  linkOnly?: boolean;
  /** Visible link text when it should not be the file name (the accessible name still names the file). */
  text?: string;
}

const SAFE_PAGE = (p: number | null | undefined): number | null => (typeof p === "number" && Number.isInteger(p) && p > 0 ? p : null);

/** A source file as direct as the data allows: file name (never a bare id), locator, quoted statement; PDFs open in the viewer. */
export function SourceLink({ projectId, documentId, filename, page, locator, statement, format, onOpenSource, linkOnly = false, text }: SourceLinkProps) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const wasOpen = useRef(false);
  // The viewer unmounts on close, so its own focus return cannot run: put focus back on the trigger here.
  useEffect(() => {
    if (wasOpen.current && !open) trigger.current?.focus();
    wasOpen.current = open;
  }, [open]);
  const name = filename ?? null;
  const label = name ?? "Document (filename unavailable)";
  const pg = SAFE_PAGE(page);
  const pdf = isPdfSource(format, name);
  return (
    <span data-testid="source-link">
      {pdf ? (
        <>
          <button
            ref={trigger}
            type="button"
            className={styles.trigger}
            aria-haspopup="dialog"
            aria-label={`Open ${label} in viewer${pg !== null ? ` at page ${pg}` : ""}`}
            onClick={() => setOpen(true)}
          >
            {text ?? label}
          </button>
          {open && (
            <Suspense fallback={<span role="status">Loading viewer…</span>}>
              <DocumentViewer projectId={projectId} documentId={documentId} filename={name} page={pg} onClose={() => setOpen(false)} />
            </Suspense>
          )}
        </>
      ) : (
        <a
          href={routeHash({ kind: "project", projectId, section: "sources" })}
          aria-label={`Open ${label} in Sources`}
          onClick={
            onOpenSource === undefined
              ? undefined
              : (e) => {
                  e.preventDefault();
                  onOpenSource(documentId);
                }
          }
        >
          {text ?? label}
        </a>
      )}
      {!linkOnly && locator !== undefined && locator !== null && locator !== "" && <span className={styles.note}> ({locator})</span>}
      {!linkOnly && statement !== undefined && statement !== null && statement !== "" && <q className={styles.quote}>{statement}</q>}
    </span>
  );
}
