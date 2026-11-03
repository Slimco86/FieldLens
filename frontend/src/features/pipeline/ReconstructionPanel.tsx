import { useState } from "react";
import { Button, Title } from "@mantine/core";
import { RefreshCw } from "lucide-react";
import { Callout, EmptyState } from "../../design";
import { MergeReview } from "../merge/MergeReview";
import { ReconstructionList } from "./ReconstructionList";
import styles from "./Pipeline.module.css";

/**
 * Reconstruction tab (UI-18, TASK-069): the identified wellbores (ready first) with their source files.
 * Reconstruct per wellbore and for all ready wellbores (estimate, separate confirm, run state and draft).
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
          Parsing and indexing of supported files run automatically after upload. Reconstruct shows what each step would
          do and starts only after you confirm it. A run collects sources, reads documents, proposes wellbore matches for
          you to review, and assembles a <strong>draft</strong> summary. The 3D asset step is not part of this version yet.
        </p>
      </Callout>
      <MergeReview projectId={projectId} onChanged={() => setDataKey((n) => n + 1)} />
      <ReconstructionList
        projectId={projectId}
        refreshKey={dataKey}
        onOpenSource={onOpenSource}
      />
    </section>
  );
}
