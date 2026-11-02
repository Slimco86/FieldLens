import { useState } from "react";
import { Button, Title } from "@mantine/core";
import { RefreshCw } from "lucide-react";
import { Callout, EmptyState } from "../../design";
import { ReconstructionList } from "./ReconstructionList";
import styles from "./Pipeline.module.css";

/**
 * Reconstruction tab (UI-17, TASK-067): the identified wellbores (ready first) with their source files.
 * The Reconstruct buttons are disabled until the run API is wired (TASK-069).
 */
export function ReconstructionPanel({
  projectId,
  revisionId,
  onOpenSource,
}: {
  projectId: string;
  revisionId: string | null;
  onOpenSource: (documentId: string) => void;
}) {
  // Counters and an id, not data: bumping one re-reads its sections. Data stays in the section resources.
  const [dataKey, setDataKey] = useState(0);
  if (revisionId === null) {
    return (
      <EmptyState title="Reconstruction is unavailable">
        <p>Reconstruction requires an imported source revision. This project has none; upload files in Sources first.</p>
      </EmptyState>
    );
  }
  return (
    <section aria-labelledby="pipeline-title" className={styles.panel}>
      <div className={styles.head}>
        <Title order={5} id="pipeline-title">
          Identified wellbores
        </Title>
        <Button
          size="xs"
          variant="default"
          leftSection={<RefreshCw size={14} aria-hidden="true" />}
          onClick={() => setDataKey((n) => n + 1)}
          aria-label="Refresh reconstruction"
        >
          Refresh
        </Button>
      </div>
      <Callout tone="info">
        <p>
          Parsing and indexing of supported files run automatically after upload. Starting a reconstruction is not
          available yet: it arrives in the next update. This build has no OCR and merge review is not yet available.
        </p>
      </Callout>
      <ReconstructionList
        projectId={projectId}
        refreshKey={dataKey}
        onOpenSource={onOpenSource}
      />
    </section>
  );
}
