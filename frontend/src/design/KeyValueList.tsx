import type { ReactNode } from "react";
import styles from "./KeyValueList.module.css";

/** Definition list in a two-column grid. Children are `<dt>`/`<dd>` pairs. */
export function KeyValueList({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  return <dl className={compact ? `${styles.list} ${styles.compact}` : styles.list}>{children}</dl>;
}

export function KeyValue({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </>
  );
}
