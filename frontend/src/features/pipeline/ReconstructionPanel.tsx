import { useState } from "react";
import { Button, Title } from "@mantine/core";
import { RefreshCw } from "lucide-react";
import { Callout, EmptyState } from "../../design";
import { ProcessingPanel } from "./ProcessingPanel";
import { ReconstructionList } from "./ReconstructionList";
import styles from "./Pipeline.module.css";

/**
 * Reconstruction tab (UI-16, TASK-063): the identified wellbores (ready first), per-wellbore and bulk Process
 * (estimate, then a separate confirm) and the document processing runs. Existing APIs only.
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
  const [procKey, setProcKey] = useState(0);
  const [openRun, setOpenRun] = useState<string | null>(null);
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
          Wellbores and processing
        </Title>
        <Button
          size="xs"
          variant="default"
          leftSection={<RefreshCw size={14} aria-hidden="true" />}
          onClick={() => {
            setDataKey((n) => n + 1);
            setProcKey((n) => n + 1);
          }}
          aria-label="Refresh reconstruction"
        >
          Refresh
        </Button>
      </div>
      <Callout tone="info">
        <p>
          Parsing and indexing of supported files run automatically after upload. Process requests a model-processing
          estimate and, after you confirm it, runs the stub step. The stub step only walks pages: it is not reconstruction,
          this build has no OCR, and merge review is not yet available.
        </p>
      </Callout>
      <ReconstructionList
        projectId={projectId}
        refreshKey={dataKey}
        onOpenSource={onOpenSource}
        onEstimated={(runId) => {
          setOpenRun(runId);
          setProcKey((n) => n + 1);
        }}
      />
      <ProcessingPanel projectId={projectId} refreshKey={procKey} openRunId={openRun} onChanged={() => setDataKey((n) => n + 1)} />
    </section>
  );
}
