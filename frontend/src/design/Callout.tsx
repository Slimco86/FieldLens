import type { CSSProperties, ReactNode, Ref } from "react";
import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import type { Tone } from "./tokens";
import styles from "./Callout.module.css";

const ICON = { neutral: Info, info: Info, success: CircleCheck, warning: TriangleAlert, danger: CircleAlert, unknown: Info };

interface Props {
  tone?: Tone;
  role?: "alert" | "status";
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  tabIndex?: number;
  elementRef?: Ref<HTMLDivElement>;
  label?: string;
}

/** Inline message block (notice, warning, error) with tone icon; text always carries the meaning. */
export function Callout({ tone = "info", role, title, children, actions, tabIndex, elementRef, label }: Props) {
  const Icon = ICON[tone];
  const vars = {
    "--callout-fg": `var(--fl-tone-${tone}-fg)`,
    "--callout-bg": `var(--fl-tone-${tone}-bg)`,
    "--callout-border": `var(--fl-tone-${tone}-border)`,
  } as CSSProperties;
  return (
    <div className={styles.callout} style={vars} role={role ?? (label === undefined ? undefined : "group")} tabIndex={tabIndex} ref={elementRef} aria-label={label}>
      <Icon size={18} aria-hidden="true" className={styles.icon} />
      <div className={styles.body}>
        {title !== undefined && <p className={styles.title}>{title}</p>}
        {children}
        {actions !== undefined && <div className={styles.actions}>{actions}</div>}
      </div>
    </div>
  );
}
