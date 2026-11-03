import { Button, Checkbox, Modal } from "@mantine/core";
import { Callout } from "../../design";
import type { Failure } from "../projects/scope";
import { STUB_TEXT, misconfiguredText, type ProcessingRun } from "./api";
import styles from "./Processing.module.css";

interface Props {
  run: ProcessingRun;
  filename: string;
  confirming: boolean;
  failure: Failure | null;
  /** Names of missing provider settings when the server refused with provider_misconfigured. */
  missing?: string[] | null;
  /** Offer the explicit "reuse the stored result" opt-in (documents that already have a result). */
  offerReuse?: boolean;
  reuse?: boolean;
  reestimating?: boolean;
  onReuseChange?: (reuse: boolean) => void;
  onConfirm: () => void;
  onClose: () => void;
}

/** The estimate and its separate explicit Confirm. Opening it spends nothing; only Confirm queues the run. */
export function ProcessEstimateDialog({
  run,
  filename,
  confirming,
  failure,
  missing = null,
  offerReuse = false,
  reuse = false,
  reestimating = false,
  onReuseChange,
  onConfirm,
  onClose,
}: Props) {
  const e = run.estimate;
  const live = e.provider !== "stub";
  const spends = e.spends_money;
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
            <Callout tone={spends ? "warning" : "info"}>
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
              {!live && <p>{STUB_TEXT}</p>}
            </Callout>
            <dl className={styles.facts} aria-label="Provider">
              <dt>Provider</dt>
              <dd>{e.provider}</dd>
              <dt>Model</dt>
              <dd>{e.model ?? "not recorded"}</dd>
              <dt>Spends money</dt>
              <dd>{spends ? "Yes: confirming spends provider budget up to the estimate" : "No: this run spends nothing"}</dd>
              <dt>Cache</dt>
              <dd>{e.force ? "Fresh read: the stored result is bypassed and a new result is stored" : "Reuses the stored result when the document is unchanged (no model call)"}</dd>
            </dl>
            {offerReuse && (
              <Checkbox
                label="Reuse the stored result if the document is unchanged (no model call)"
                checked={reuse}
                disabled={reestimating || confirming}
                onChange={(ev) => onReuseChange?.(ev.currentTarget.checked)}
              />
            )}
            {reestimating && (
              <p role="status" className={styles.muted}>
                Updating the estimate…
              </p>
            )}
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
            {failure !== null && missing !== null && (
              <Callout tone="danger" role="alert">
                <p>{misconfiguredText(missing)}</p>
              </Callout>
            )}
            {failure !== null && missing === null && (
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
              <Button onClick={onConfirm} disabled={blocked || confirming || reestimating} loading={confirming}>
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
