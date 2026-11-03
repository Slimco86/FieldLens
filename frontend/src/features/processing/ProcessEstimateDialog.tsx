import { useState } from "react";
import { Button, Checkbox, Modal, NumberInput } from "@mantine/core";
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
  /** Pages in the document when the user may choose how many to read (live model route); otherwise null. */
  pageTotal?: number | null;
  onPagesChange?: (pages: number) => void;
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
  pageTotal = null,
  onPagesChange,
  onConfirm,
  onClose,
}: Props) {
  const e = run.estimate;
  const live = e.provider !== "stub";
  const spends = e.spends_money;
  const doc = run.documents[0];
  const [wanted, setWanted] = useState<number | string>(doc?.pages.page_end ?? e.pages);
  const chosen = typeof wanted === "number" && Number.isInteger(wanted) ? wanted : null;
  const validPages = chosen !== null && pageTotal !== null && chosen >= 1 && chosen <= pageTotal;
  const stale = pageTotal !== null && chosen !== e.pages;
  const blocked = !e.confirmable || stale;
  const noText = e.pages_without_text ?? [];
  const calls = e.calls ?? null;
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
            {pageTotal !== null && (
              <div className={styles.row}>
                <NumberInput
                  label={`Page count (1-${pageTotal}, starting at page 1)`}
                  value={wanted}
                  onChange={setWanted}
                  min={1}
                  max={pageTotal}
                  allowDecimal={false}
                  allowNegative={false}
                  disabled={reestimating || confirming}
                  w={220}
                />
                <Button
                  variant="default"
                  disabled={!validPages || !stale || reestimating || confirming}
                  onClick={() => chosen !== null && onPagesChange?.(chosen)}
                >
                  Update estimate
                </Button>
              </div>
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
                {calls !== null && ` (${calls} model call${calls === 1 ? "" : "s"})`}
              </dd>
              <dt>Estimated cost</dt>
              <dd>
                USD {e.estimated_usd}
                {e.upper_bound && " (upper bound; actual is usually lower)"}
              </dd>
              <dt>Rates</dt>
              <dd>
                {e.pricing_source}
                {e.input_usd_per_mtok != null && e.output_usd_per_mtok != null &&
                  `: USD ${e.input_usd_per_mtok} input, USD ${e.output_usd_per_mtok} output per million tokens`}
              </dd>
            </dl>
            {noText.length > 0 && (
              <Callout tone="warning" role="status">
                <p>
                  {noText.length} of {e.pages} selected pages have no text layer (page{noText.length === 1 ? "" : "s"} {noText.join(", ")}); OCR is not
                  available, so they send nothing and cost nothing.
                </p>
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
