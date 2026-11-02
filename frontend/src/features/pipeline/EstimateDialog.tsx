import { Button, Modal } from "@mantine/core";
import { Callout, Chip } from "../../design";
import { CircleCheck, CircleX } from "lucide-react";
import type { Failure } from "../projects/scope";
import type { ReconstructionEstimate } from "./api";
import { STAGE_NAME, STATUS_LABEL, reasonText, usd } from "./runs";
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
export function EstimateDialog({ estimate, scope, confirming, failure, onConfirm, onClose }: Props) {
  const fresh = estimate.items.filter((i) => !i.already_active);
  const pageCap = estimate.items.flatMap((i) => i.stages).find((s) => s.page_cap !== null)?.page_cap ?? null;
  const unavailable = [
    ...new Map(
      estimate.items.flatMap((i) => i.stages).filter((s) => s.availability === "not_available").map((s) => [s.stage, s.reason_code] as const),
    ),
  ];
  const blocked = !estimate.confirmable || !estimate.fits_budget || fresh.length === 0;
  return (
    <Modal
      opened
      onClose={onClose}
      title={`Reconstruction estimate for ${scope}`}
      size="lg"
      transitionProps={{ duration: 0 }}
      closeButtonProps={{ "aria-label": "Close estimate" }}
      trapFocus
      returnFocus
    >
      <div className={styles.nested}>
        <Callout tone="info">
          <p>
            This is an estimate only: nothing has started and nothing is spent until you press Confirm. The provider is{" "}
            <strong>stub</strong>: no live model calls are made ({estimate.pricing_label}). Pages read by extraction are
            capped at {pageCap ?? 500} per run.
          </p>
        </Callout>
        <table className={styles.plain} aria-label="Estimate per wellbore">
          <thead>
            <tr>
              <th scope="col">Wellbore</th>
              <th scope="col">Estimated cost</th>
              <th scope="col">Stages</th>
            </tr>
          </thead>
          <tbody>
            {estimate.items.map((i) => (
              <tr key={i.wellbore_id}>
                <th scope="row">{i.wellbore_name}</th>
                <td>{i.already_active ? "No new cost" : usd(i.estimated_usd)}</td>
                <td>
                  {i.already_active ? (
                    <>
                      <Chip spec={NO} label="Already active" /> This wellbore already has a {STATUS_LABEL[i.run_status].toLowerCase()} run for
                      this source revision. It is shown, not started again.
                    </>
                  ) : (
                    <ul className={styles.list} aria-label={`Stages of ${i.wellbore_name}`}>
                      {i.stages.map((s) => (
                        <li key={s.stage}>
                          {STAGE_NAME[s.stage]}:{" "}
                          {s.availability === "will_run" ? (
                            <>
                              <Chip spec={OK} label="Will run" /> ({usd(s.estimated_usd)})
                            </>
                          ) : (
                            <>
                              <Chip spec={NO} label="Not available yet" /> {reasonText(s.reason_code)}
                            </>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className={styles.facts} aria-label="Estimate totals">
          <dt>Total estimate</dt>
          <dd>{usd(estimate.total_estimated_usd)}</dd>
          <dt>Remaining budget</dt>
          <dd>
            {usd(estimate.remaining_budget_usd)} of {usd(estimate.total_cap_usd)} total cap
          </dd>
        </dl>
        {unavailable.length > 0 && (
          <p className={styles.note}>
            Not available yet: {unavailable.map(([s, r]) => `${STAGE_NAME[s]} (${reasonText(r) ?? "no reason given"})`).join("; ")}. A run
            therefore ends <strong>partial</strong>: it is a draft summary, not a finished reconstruction, and there is no OCR.
          </p>
        )}
        {!estimate.fits_budget && (
          <Callout tone="danger" role="alert">
            <p>This estimate does not fit the remaining budget. It cannot be confirmed.</p>
          </Callout>
        )}
        {estimate.fits_budget && fresh.length === 0 && (
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
    </Modal>
  );
}
