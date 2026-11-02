import { Button, Modal } from "@mantine/core";
import { Callout } from "../../design";
import type { Failure } from "../projects/scope";
import type { ProcessingRun } from "./api";
import styles from "./Processing.module.css";

interface Props {
  run: ProcessingRun;
  filename: string;
  confirming: boolean;
  failure: Failure | null;
  onConfirm: () => void;
  onClose: () => void;
}

/** The estimate and its separate explicit Confirm. Opening it spends nothing; only Confirm queues the run. */
export function ProcessEstimateDialog({ run, filename, confirming, failure, onConfirm, onClose }: Props) {
  const e = run.estimate;
  const live = e.provider !== "stub";
  const blocked = !e.confirmable || !e.fits_budget;
  const doc = run.documents[0];
  return (
    <Modal.Root opened onClose={onClose} size="lg" transitionProps={{ duration: 0 }} trapFocus returnFocus={false}>
      <Modal.Overlay />
      <Modal.Content>
        <div className={styles.dialogHead}>
          <Modal.Title>{`Model processing estimate for ${filename}`}</Modal.Title>
          <Modal.CloseButton aria-label="Close estimate" />
        </div>
        <Modal.Body>
          <div className={styles.dialogBody}>
            <Callout tone={live ? "warning" : "info"}>
              <p>
                This is an estimate only: nothing has started and nothing is spent until you press Confirm.{" "}
                {live ? (
                  <>
                    The provider is <strong>{e.provider}</strong>: confirming makes live model calls and records spend.
                  </>
                ) : (
                  <>
                    The provider is <strong>{e.provider}</strong>: no live model calls are made.
                  </>
                )}{" "}
                The model's answer is a proposal, shown as &quot;Model-read, unverified&quot;.
              </p>
            </Callout>
            <dl className={styles.facts} aria-label="Estimate totals">
              <dt>Pages to read</dt>
              <dd>
                {e.pages}
                {doc !== undefined && ` (pages ${doc.pages.page_start}-${doc.pages.page_end} of ${doc.page_count})`}
              </dd>
              <dt>Estimated tokens</dt>
              <dd>
                {e.estimated_input_tokens.toLocaleString("en-US")} input, {e.estimated_output_tokens.toLocaleString("en-US")} output
              </dd>
              <dt>Estimated cost</dt>
              <dd>USD {e.estimated_usd}</dd>
              <dt>Rates</dt>
              <dd>{e.pricing_source}</dd>
              <dt>Remaining budget</dt>
              <dd>
                USD {e.remaining_budget_usd} of USD {e.total_cap_usd} total cap
              </dd>
            </dl>
            {!e.fits_budget && (
              <Callout tone="danger" role="alert">
                <p>This estimate does not fit the remaining budget. It cannot be confirmed.</p>
              </Callout>
            )}
            {failure !== null && (
              <Callout tone="danger" role="alert">
                <p>
                  The run was not started: {failure.message}
                  {failure.code !== null && (
                    <>
                      {" "}
                      (<code>{failure.code}</code>)
                    </>
                  )}
                  . Nothing was spent.
                </p>
                {failure.requestId !== null && <p>Request ID: {failure.requestId}</p>}
              </Callout>
            )}
            <div className={styles.row}>
              <Button onClick={onConfirm} disabled={blocked || confirming} loading={confirming}>
                Confirm and start (USD {e.estimated_usd})
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
