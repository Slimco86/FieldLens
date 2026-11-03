import { Button } from "@mantine/core";
import { Ban, CircleAlert, CircleCheck, CircleHelp, CircleX, Clock, LoaderCircle, TriangleAlert } from "lucide-react";
import { Callout, Chip } from "../../design";
import type { ChipSpec } from "../../design/StatusChip";
import type { ReconstructionEvidenceRef, ReconstructionRun } from "./api";
import { locatorText } from "./locator";
import { STATUS_LABEL, STATUS_NOTE, isActive, reasonText, stageLabel, stageStateLabel, usd, type RunStatus } from "./runs";
import styles from "./Pipeline.module.css";

const STATUS_CHIP: Record<RunStatus, ChipSpec> = {
  estimated: { tone: "neutral", icon: Clock },
  queued: { tone: "info", icon: Clock },
  running: { tone: "info", icon: LoaderCircle, spin: true },
  partial: { tone: "warning", icon: TriangleAlert },
  succeeded: { tone: "success", icon: CircleCheck },
  failed: { tone: "danger", icon: CircleX },
  cancelled: { tone: "neutral", icon: Ban },
  interrupted: { tone: "warning", icon: CircleAlert },
};
const UNKNOWN: ChipSpec = { tone: "unknown", icon: CircleHelp };

export function RunChip({ status }: { status: RunStatus }) {
  return <Chip spec={STATUS_CHIP[status] ?? UNKNOWN} label={STATUS_LABEL[status] ?? status} />;
}

/** One line per stage; the not-available stages say what is missing. */
function StageList({ run }: { run: ReconstructionRun }) {
  return (
    <ol className={styles.list} aria-label={`Stages of ${run.wellbore_name}`}>
      {run.stages.map((s) => (
        <li key={s.stage}>
          <strong>{stageLabel(s.stage)}</strong>: {stageStateLabel(s)}
          {(s.state === "not_available" || s.state === "stubbed") && reasonText(s.reason_code) !== null && <> ({reasonText(s.reason_code)})</>}
          {s.message !== null && s.state !== "not_available" && s.state !== "stubbed" && <> - {s.message}</>}
          {s.state === "failed" && s.error_code !== null && <> (<code>{s.error_code}</code>)</>}
        </li>
      ))}
    </ol>
  );
}

/** Compact run state in the Action cell: status, stages, and the run actions. */
export function RunCell({
  run,
  busy,
  onCancel,
  onRetry,
  onDetails,
  detailsOpen,
}: {
  run: ReconstructionRun;
  busy: boolean;
  onCancel: () => void;
  onRetry: () => void;
  onDetails: () => void;
  detailsOpen: boolean;
}) {
  const name = run.wellbore_name;
  return (
    <div className={styles.nested}>
      <RunChip status={run.status} />
      {run.stub_run && <Chip spec={{ tone: "warning", icon: TriangleAlert }} label="Stub run" />}
      {run.invalidated_at !== null && (
        <p className={styles.note} role="status">
          This draft is out of date: wellbore matches changed after it was built. Reconstruct again to refresh it.
        </p>
      )}
      {STATUS_NOTE[run.status] !== undefined && <p className={styles.note}>{STATUS_NOTE[run.status]}</p>}
      <StageList run={run} />
      <div className={styles.actions}>
        {isActive(run) && (
          <Button size="xs" variant="default" disabled={busy || run.cancel_requested} onClick={onCancel} aria-label={`Cancel reconstruction of ${name}`}>
            {run.cancel_requested ? "Cancelling…" : "Cancel"}
          </Button>
        )}
        {run.retryable && (
          <Button size="xs" variant="default" disabled={busy} onClick={onRetry} aria-label={`Retry reconstruction of ${name}`}>
            Retry
          </Button>
        )}
        <Button size="xs" variant="subtle" aria-expanded={detailsOpen} onClick={onDetails} aria-label={`${detailsOpen ? "Hide" : "Show"} run draft of ${name}`}>
          {detailsOpen ? "Hide run draft" : "Run draft"}
        </Button>
      </div>
    </div>
  );
}

const MAX_EVIDENCE = 5;

/** One entry per file: the server may return several references to the same file; their locators are combined. */
export function groupEvidence(refs: ReconstructionEvidenceRef[]): { document_id: string; filename: string | null; locators: string[] }[] {
  const out = new Map<string, { document_id: string; filename: string | null; locators: string[] }>();
  for (const e of refs) {
    const cur = out.get(e.document_id) ?? { document_id: e.document_id, filename: e.filename, locators: [] };
    const loc = locatorText(e.locator);
    if (loc !== "no locator" && !cur.locators.includes(loc)) cur.locators.push(loc);
    out.set(e.document_id, cur);
  }
  return [...out.values()];
}

function Evidence({ refs, truncated, onOpenSource }: { refs: ReconstructionEvidenceRef[]; truncated?: boolean; onOpenSource: (id: string) => void }) {
  if (refs.length === 0) return null;
  const files = groupEvidence(refs);
  return (
    <ul className={styles.list} aria-label="Evidence references">
      {files.slice(0, MAX_EVIDENCE).map((e) => (
        <li key={e.document_id}>
          <a
            href="#sources"
            aria-label={`Open ${e.filename ?? "file"} in Sources`}
            onClick={(ev) => {
              ev.preventDefault();
              onOpenSource(e.document_id);
            }}
          >
            {e.filename ?? "Source file"}
          </a>{" "}
          <span className={styles.note}>
            (document {e.document_id.slice(0, 8)}; {e.locators.length === 0 ? "no locator recorded" : e.locators.slice(0, 5).join("; ")})
          </span>
        </li>
      ))}
      {(files.length > MAX_EVIDENCE || truncated === true) && (
        <li className={styles.note}>
          {files.length > MAX_EVIDENCE ? `${files.length - MAX_EVIDENCE} more file(s) are not listed here. ` : ""}
          {truncated === true && "The server limits evidence per category; counts stay exact."}
        </li>
      )}
    </ul>
  );
}

/** Stage list and the draft summary of one run. A draft: not published, no 3D scene, no charts. */
export function RunDetail({ run, onOpenSource }: { run: ReconstructionRun; onOpenSource: (id: string) => void }) {
  const name = run.wellbore_name;
  const sum = run.summary;
  return (
    <section aria-label={`Run draft of ${name}`} className={styles.nested}>
      <h6 className={styles.catHeading}>
        Reconstruction run draft: {name} <RunChip status={run.status} />
      </h6>
      <Callout tone="warning">
        <p>
          This is a <strong>draft</strong> summary of what ran and what is still open. It is not the published 3D model or
          charts; reviewing and publishing a model is a later feature. {STATUS_NOTE[run.status] ?? ""}
        </p>
      </Callout>
      <dl className={styles.facts} aria-label={`Run facts of ${name}`}>
        <dt>Provider</dt>
        <dd>stub (no live model calls)</dd>
        <dt>Estimated</dt>
        <dd>{usd(run.estimated_usd)}</dd>
        <dt>Spent so far</dt>
        <dd>{usd(run.actual_usd)}</dd>
        {run.started_at !== null && (
          <>
            <dt>Started</dt>
            <dd>{run.started_at}</dd>
          </>
        )}
        {run.finished_at !== null && (
          <>
            <dt>Finished</dt>
            <dd>{run.finished_at}</dd>
          </>
        )}
      </dl>
      {run.error_message !== null && (
        <Callout tone="danger" role="alert">
          <p>
            {run.error_message}
            {run.error_code !== null && <> (<code>{run.error_code}</code>)</>}
          </p>
        </Callout>
      )}
      <StageList run={run} />
      {sum === null && <p className={styles.note}>No draft summary exists yet; it is written when the Assemble stage finishes.</p>}
      {sum !== null && (
        <>
          <p>{sum.note}</p>
          <h6 className={styles.catHeading}>Coverage per category</h6>
          <ul className={styles.list} aria-label={`Coverage of ${name}`}>
            {sum.coverage.map((c) => (
              <li key={c.category}>
                <strong>{c.category.replace(/_/g, " ")}</strong>:{" "}
                {c.present
                  ? `${c.record_count} record(s); accepted candidates ${c.accepted_candidate_count}, open ${c.open_candidate_count}, conflicting records ${c.conflicting_record_count}`
                  : "no data"}
                {c.gap_reasons.length > 0 && <> (gaps: {c.gap_reasons.join(", ")})</>}
                <Evidence refs={c.evidence} truncated={c.evidence_truncated} onOpenSource={onOpenSource} />
              </li>
            ))}
          </ul>
          <h6 className={styles.catHeading}>Unresolved</h6>
          {sum.unresolved.length === 0 ? (
            <p className={styles.note}>The server lists nothing unresolved.</p>
          ) : (
            <ul className={styles.list} aria-label={`Unresolved items of ${name}`}>
              {sum.unresolved.map((u, i) => (
                <li key={`${u.code}-${i}`}>
                  <code>{u.code}</code> {u.message}
                  {u.count !== null && <> ({u.count})</>}
                  <Evidence refs={u.evidence ?? []} onOpenSource={onOpenSource} />
                </li>
              ))}
            </ul>
          )}
          <h6 className={styles.catHeading}>Conflicts</h6>
          {sum.conflicts.length === 0 ? (
            <p className={styles.note}>The server lists no conflicts.</p>
          ) : (
            <ul className={styles.list} aria-label={`Conflicts of ${name}`}>
              {sum.conflicts.map((c, i) => (
                <li key={`${c.code}-${i}`}>
                  <code>{c.code}</code> {c.message} <span className={styles.note}>({c.category}; {c.severity})</span>
                  <Evidence refs={c.evidence} onOpenSource={onOpenSource} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
