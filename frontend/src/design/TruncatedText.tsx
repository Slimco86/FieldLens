import { useId, useState, useSyncExternalStore, type ReactNode } from "react";
import { Tooltip } from "@mantine/core";
import styles from "./TruncatedText.module.css";

// Only one tooltip may be open: a focused button wins over a hovered one (keyboard users must see
// the value of the control they are on even while the mouse rests on another).
let focusedId: string | null = null;
const listeners = new Set<() => void>();
function setFocused(id: string | null): void {
  focusedId = id;
  listeners.forEach((l) => l());
}
function useFocusedId(): string | null {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => focusedId,
  );
}

interface Props {
  /** The complete value; always kept in the DOM and shown in full by the tooltip. */
  value: string;
  /** What the value is, for the accessible name ("Copy SHA-256"). */
  label: string;
  /** Maximum visible width in `ch`; the rest is cut with an ellipsis. */
  maxCh?: number;
  mono?: boolean;
  children?: ReactNode;
}

/**
 * Long identifiers and file names stay on one line, cut with an ellipsis, so tables and sidebars keep
 * a fixed layout. The full value is reachable from the keyboard: the control is a button, focus or
 * hover shows it in a tooltip, and activating it copies it to the clipboard.
 */
export function TruncatedText({ value, label, maxCh = 24, mono = false, children }: Props) {
  const id = useId();
  const [copied, setCopied] = useState(false);
  const [hovered, setHovered] = useState(false);
  const active = useFocusedId();
  const opened = active === id || (hovered && active === null);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable: the tooltip still shows the full value */
    }
  }
  return (
    <Tooltip
      label={<span className={styles.tip}>{copied ? `Copied ${label}` : value}</span>}
      multiline
      withArrow
      opened={opened}
    >
      <button
        type="button"
        className={mono ? `${styles.button} ${styles.mono}` : styles.button}
        style={{ maxWidth: `min(${maxCh}ch, 100%)` }}
        aria-label={`Copy ${label}: ${value}`}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setFocused(id)}
        onBlur={() => {
          if (focusedId === id) setFocused(null);
        }}
        onClick={() => void copy()}
      >
        {children ?? value}
      </button>
    </Tooltip>
  );
}
