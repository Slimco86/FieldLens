import { useEffect, useState } from "react";
import { Drawer } from "@mantine/core";
import { documentContentUrl, probeContent } from "./content";
import styles from "./SourceLink.module.css";

interface Props {
  projectId: string;
  documentId: string;
  filename: string | null;
  page: number | null;
  onClose: () => void;
}

/**
 * Right-hand drawer with the browser's own PDF viewer in a same-origin iframe (no PDF.js). The iframe carries no
 * `sandbox` attribute: it stops Chromium's viewer. Loaded lazily and fetches nothing until it is opened.
 */
export default function DocumentViewer({ projectId, documentId, filename, page, onClose }: Props) {
  const [problem, setProblem] = useState<string | null | undefined>(undefined); // undefined = checking
  useEffect(() => {
    const ctl = new AbortController();
    probeContent(projectId, documentId, ctl.signal).then(setProblem, () => undefined);
    return () => ctl.abort();
  }, [projectId, documentId]);
  const name = filename ?? "Document";
  const url = documentContentUrl(projectId, documentId, page);
  return (
    <Drawer.Root opened onClose={onClose} position="right" size="xl" transitionProps={{ duration: 0 }} trapFocus returnFocus closeOnEscape>
      <Drawer.Overlay />
      <Drawer.Content aria-label={`${name}${page !== null ? `, page ${page}` : ""}`}>
        <Drawer.Header>
          <Drawer.Title>
            {name}
            {page !== null ? `, page ${page}` : ""}
          </Drawer.Title>
          <Drawer.CloseButton aria-label="Close document viewer" />
        </Drawer.Header>
        <Drawer.Body>
          <div className={styles.viewer}>
            {problem === undefined && <p role="status">Loading document…</p>}
            {typeof problem === "string" && <p role="alert">{problem}</p>}
            {problem === null && <iframe className={styles.frame} src={url} title={`${name} (PDF)`} />}
            {problem !== undefined && problem === null && (
              <a href={url} target="_blank" rel="noopener noreferrer">
                Open in new tab
              </a>
            )}
          </div>
        </Drawer.Body>
      </Drawer.Content>
    </Drawer.Root>
  );
}
