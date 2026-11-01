import type { ReactNode } from "react";
import { Button, Skeleton } from "@mantine/core";
import { Inbox, RefreshCw } from "lucide-react";
import { Callout } from "./Callout";
import styles from "./states.module.css";

/** Shared loading state: skeleton bars plus a visible caption (UI-4). */
export function LoadingState({ label, status = false }: { label: string; status?: boolean }) {
  return (
    <div className={styles.loading} aria-busy="true" aria-live="polite" role={status ? "status" : undefined}>
      <Skeleton height="var(--fl-space-md)" width="60%" radius="sm" />
      <Skeleton height="var(--fl-space-md)" width="85%" radius="sm" />
      <p className={styles.caption}>{label}</p>
    </div>
  );
}

/** Shared empty state; `children` states the real next step or prerequisite. */
export function EmptyState({ title, children, icon }: { title?: string; children: ReactNode; icon?: ReactNode }) {
  return (
    <div className={styles.empty}>
      <span className={styles.emptyIcon} aria-hidden="true">
        {icon ?? <Inbox size={28} />}
      </span>
      {title !== undefined && <p className={styles.emptyTitle}>{title}</p>}
      {typeof children === "string" ? <p>{children}</p> : children}
    </div>
  );
}

interface ErrorProps {
  /** Full sentence, e.g. "Projects could not be loaded: down". */
  message: string;
  requestId: string | null;
  onRetry?: () => void;
  retryLabel?: string;
}

/** Shared error state: alert with the request ID and a retry action (UI-4). */
export function ErrorState({ message, requestId, onRetry, retryLabel = "Retry" }: ErrorProps) {
  return (
    <Callout
      tone="danger"
      role="alert"
      actions={
        onRetry === undefined ? undefined : (
          <Button size="xs" variant="default" leftSection={<RefreshCw size={14} aria-hidden="true" />} onClick={onRetry}>
            {retryLabel}
          </Button>
        )
      }
    >
      <p>{message}</p>
      {requestId !== null && <p>Request ID: {requestId}</p>}
    </Callout>
  );
}
