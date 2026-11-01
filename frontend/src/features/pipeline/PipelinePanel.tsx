import { useState } from "react";
import { Button, Title } from "@mantine/core";
import { RefreshCw } from "lucide-react";
import { Callout, EmptyState } from "../../design";
import { ExposureSection } from "./ExposureSection";
import { ProcessingPanel } from "./ProcessingPanel";
import { ReadinessChecklist } from "./ReadinessChecklist";
import styles from "./Pipeline.module.css";

/** Pipeline panel (UI-15, TASK-053): readiness, data exposure and explicit document processing, from existing APIs only. */
export function PipelinePanel({ projectId, revisionId }: { projectId: string; revisionId: string | null }) {
  // Counters, not data: bumping one re-reads its sections. Data stays in the section resources.
  const [dataKey, setDataKey] = useState(0);
  const [procKey, setProcKey] = useState(0);
  return (
    <section aria-labelledby="pipeline-title" className={styles.panel}>
      <div className={styles.head}>
        <Title order={5} id="pipeline-title">
          Processing pipeline
        </Title>
        <Button
          size="xs"
          variant="default"
          leftSection={<RefreshCw size={14} aria-hidden="true" />}
          onClick={() => {
            setDataKey((n) => n + 1);
            setProcKey((n) => n + 1);
          }}
          aria-label="Refresh processing pipeline"
        >
          Refresh
        </Button>
      </div>
      <Callout tone="info">
        <p>
          Parsing and indexing of supported files run automatically after upload. Documents without a native parser wait
          for you to start model processing below. This build has no OCR and no reconstruction start; merge review is not
          yet available.
        </p>
      </Callout>
      {revisionId === null ? (
        <EmptyState title="Nothing to process yet">
          <p>This project has no imported source revision. Upload files below first.</p>
        </EmptyState>
      ) : (
        <>
          <ReadinessChecklist projectId={projectId} refreshKey={dataKey} />
          <ExposureSection projectId={projectId} refreshKey={dataKey} />
          <ProcessingPanel projectId={projectId} refreshKey={procKey} onChanged={() => setDataKey((n) => n + 1)} />
        </>
      )}
    </section>
  );
}
