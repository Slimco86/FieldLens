import { useId } from "react";
import styles from "./Charts.module.css";

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export interface AsOfControlProps {
  /** Selected as-of date, ISO `YYYY-MM-DD`, or null = no as-of (latest). Date precision is preserved as typed. */
  value: string | null;
  onChange: (value: string | null) => void;
}

/**
 * Historical-view date for charts and the assistant. A native date input (keyboard operable, labelled) with an
 * explicit clear button. Whether a date is valid for the data is the server's call: a rejection is shown by the chart
 * panel as an alert. This is the selected view time, not a measurement/acquisition date.
 */
export function AsOfControl({ value, onChange }: AsOfControlProps) {
  const id = useId();
  return (
    <div className={styles.asOf} role="group" aria-label="As-of date">
      <label htmlFor={id}>As of</label>
      <input
        id={id}
        type="date"
        value={value ?? ""}
        aria-describedby={`${id}-hint`}
        onChange={(e) => {
          const v = e.target.value;
          onChange(ISO_DATE.test(v) ? v : null);
        }}
      />
      <button type="button" onClick={() => onChange(null)} disabled={value === null} aria-label="Clear as-of date (show latest)">
        Clear
      </button>
      <span id={`${id}-hint`} className={styles.asOfHint}>
        {value === null ? "Showing the latest record" : `Showing the record as of ${value}`}
      </span>
    </div>
  );
}
