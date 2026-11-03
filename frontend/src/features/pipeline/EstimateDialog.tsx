import { Button, Modal } from "@mantine/core";
import { Callout, Chip } from "../../design";
import { CircleCheck, CircleX } from "lucide-react";
import type { Failure } from "../projects/scope";
import type { ReconstructionEstimate, ReconstructionStageEstimate } from "./api";
import { STATUS_LABEL, reasonText, stageLabel, usd } from "./runs";
import styles from "./Pipeline.module.css";

const OK = { tone: "success", icon: CircleCheck } as const;
const NO = { tone: "neutral", icon: CircleX } as const;

interface Props {
  estimate: ReconstructionEstimate;
  /** What the estimate is for, e.g. "15/9-F-12" or "all ready wellbores". */
  scope: string;
  confirming: boolean;
  failure: Failure | null;
  onConfirm: () => void;
  onClose: () => void;
}

/** The estimate and its separate explicit Confirm. Opening it spends nothing; only Confirm queues runs. */
const STUB = { tone: "warning", icon: CircleX } as const;

/** "2 new, 3 reused (documents)" or the server's note: what is new work versus a stored result. */
function work(s: ReconstructionStageEstimate): string {
  if (s.new_work === 0 && s.reused === 0) return s.note ?? "Nothing to do.";
  const parts = [`${s.new_work} new`, `${s.reused} reused from earlier results`];
  return `${parts.join(", ")} (${s.unit})${s.note ? `. ${s.note}` : ""}`;
}

function StageRow({ s }: { s: ReconstructionStageEstimate }) {
  return (
    <li>
      <strong>{stageLabel(s.stage)}</strong>{" "}
      {s.kind === "agent" ? <span className={styles.note}>(uses a model)</span> : <span className={styles.note}>(no model)</span>}
      <p className={styles.note}>{s.description}</p>
      <div>
        {s.availability === "will_run" && <Chip spec={OK} label="Will run" />}
        {s.availability === "stub" && <Chip spec={STUB} label="Stub: no model is called" />}
        {s.availability === "not_available" && (
          <Chip spec={NO} label={s.stage === "design" ? "Available after the 3D asset feature" : "Not wired in this build"} />
        )}{" "}
        {s.availability === "not_available" ? (reasonText(s.reason_code) ?? s.note ?? "") : work(s)}
        {s.availability !== "not_available" && <> - estimated cost {usd(s.estimated_usd)}</>}
      </div>
    </li>
  );
}

/** The plain-language plan and its separate explicit Confirm. Opening it spends nothing; only Confirm starts runs. */
export function EstimateDialog({ estimate, scope, confirming, failure, onConfirm, onClose }: Props) {
  const fresh = estimate.items.filter((i) => !i.already_active);
  const blocked = !estimate.confirmable || fresh.length === 0;
  const stages = estimate.stage_totals ?? [];
  return (
    <Modal.Root opened onClose={onClose} size="lg" transitionProps={{ duration: 0 }} trapFocus returnFocus>
      <Modal.Overlay />
      <Modal.Content>
        {/* A div, not Modal.Header: that renders <header>, which axe reports as a second banner landmark. */}
        <div className={styles.dialogHead}>
          <Modal.Title>{`Reconstruction estimate for ${scope}`}</Modal.Title>
          <Modal.CloseButton aria-label="Close estimate" />
        </div>
        <Modal.Body>
          <div className={styles.nested}>
            <Callout tone="info">
              <p>
                Nothing has started and nothing is spent until you press Confirm. Costs below are information only:
                they are not a limit. {estimate.stub ? <strong>Stub provider: no model will be called in this run.</strong> : null}
              </p>
            </Callout>
            <ol className={styles.list} aria-label="What each stage does">
              {stages.map((s) => (
                <StageRow key={s.stage} s={s} />
              ))}
            </ol>
            {estimate.stub && (
              <p className={styles.note}>
                A stub run is shown as <strong>Stub run</strong> and ends partial: it is a draft, never a finished reconstruction.
              </p>
            )}
            <table className={styles.plain} aria-label="Wellbores in this run">
              <thead>
                <tr>
                  <th scope="col">Wellbore</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {estimate.items.map((i) => (
                  <tr key={i.wellbore_id}>
                    <th scope="row">{i.wellbore_name}</th>
                    <td>
                      {i.already_active ? (
                        <>
                          <Chip spec={NO} label="Already active" /> This wellbore already has a {STATUS_LABEL[i.run_status].toLowerCase()} run
                          for this source revision. It is shown, not started again.
                        </>
                      ) : (
                        "Will start"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <dl className={styles.facts} aria-label="Estimate totals">
              <dt>Estimated total cost (information only)</dt>
              <dd>{usd(estimate.total_estimated_usd)}</dd>
            </dl>
            {fresh.length === 0 && (
              <Callout tone="info" role="status">
                <p>Every selected wellbore already has an active run. Nothing new would start.</p>
              </Callout>
            )}
            {failure !== null && (
              <Callout tone="danger" role="alert">
                <p>
                  The run was not started: {failure.message}
                  {failure.code !== null && <> (<code>{failure.code}</code>)</>}. Nothing was spent.
                </p>
                {failure.requestId !== null && <p>Request ID: {failure.requestId}</p>}
              </Callout>
            )}
            <div className={styles.actions}>
              <Button onClick={onConfirm} disabled={blocked || confirming} loading={confirming}>
                Confirm and start ({usd(estimate.total_estimated_usd)})
              </Button>
              <Button variant="default" onClick={onClose} data-autofocus>
                Cancel
              </Button>
            </div>
          </div>
        </Modal.Body>
      </Modal.Content>
    </Modal.Root>
  );
}
