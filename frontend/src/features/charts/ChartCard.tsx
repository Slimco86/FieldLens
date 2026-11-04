import { useEffect, useRef, useState } from "react";
import type { ChartSpecWire } from "./api";
import { ChartBlock } from "./ChartBlock";
import styles from "./Charts.module.css";

export interface ChartCardProps {
  spec: ChartSpecWire;
  wellboreId?: string | null;
}

/**
 * Overview card for the chart grid plus a full-screen modal with the full-detail chart. The modal copy is mounted
 * only while open (its ECharts instance is created on open and disposed on close) and reads the same spec and
 * shared window/cursor state, so there is no refetch.
 */
export function ChartCard({ spec, wellboreId = null }: ChartCardProps) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement | null>(null);
  const dialog = useRef<HTMLDialogElement | null>(null);
  const closeBtn = useRef<HTMLButtonElement | null>(null);

  function close() {
    setOpen(false);
    opener.current?.focus();
  }

  useEffect(() => {
    const d = dialog.current;
    if (!open || d === null) return;
    // Native modal where available (focus trap, inert page, top layer); plain `open` where the DOM lacks showModal.
    if (typeof d.showModal === "function") {
      if (!d.open) d.showModal();
    } else {
      d.setAttribute("open", "");
    }
    closeBtn.current?.focus();
    return () => {
      if (typeof d.close === "function" && d.open) d.close();
    };
  }, [open]);

  const title = spec.title;
  return (
    <div className={styles.cell}>
      <ChartBlock
        spec={spec}
        variant="overview"
        height="13rem"
        wellboreId={wellboreId}
        headerAction={
          <button ref={opener} type="button" className={styles.expand} aria-haspopup="dialog" aria-label={`Expand chart: ${title}`} title="Expand chart" onClick={() => setOpen(true)}>
            <span aria-hidden="true">⤢</span>
          </button>
        }
      />
      {open && (
        <dialog
          ref={dialog}
          className={styles.dialog}
          aria-labelledby={`${spec.chart_id}-dlg-title`}
          onCancel={(e) => {
            e.preventDefault();
            close();
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              close();
            }
          }}
        >
          <div className={styles.dialogBar}>
            <span id={`${spec.chart_id}-dlg-title`} className={styles.dialogTitle}>
              {title}
            </span>
            <button ref={closeBtn} type="button" onClick={close} aria-label={`Close chart: ${title}`}>
              Close
            </button>
          </div>
          <div className={styles.dialogBody}>
            <ChartBlock spec={spec} variant="detail" height="65dvh" headingLevel={2} inDialog wellboreId={wellboreId} />
          </div>
        </dialog>
      )}
    </div>
  );
}
