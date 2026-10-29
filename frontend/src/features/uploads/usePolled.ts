import { useCallback, useEffect, useRef, useState } from "react";
import { toFailure, type Failure } from "../projects/scope";

export type Polled<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T; refreshError: Failure | null }
  | { kind: "error"; error: Failure };

interface Settled<T> {
  key: string;
  data: T | null;
  error: Failure | null;
}

export const POLL_INTERVAL_MS = 2000;

/**
 * Keyed read that refreshes silently (keeps the last data on screen) while `active(data)` is true.
 * A key change shows "loading" and aborts the old request; a response for any other key is never
 * rendered. Timers and requests are cleaned up on unmount. `version` forces a silent refresh.
 */
export function usePolled<T>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
  active: (data: T) => boolean,
  version = "",
  intervalMs = POLL_INTERVAL_MS,
) {
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    if (key === null) return;
    const ctl = new AbortController();
    loadRef.current(ctl.signal).then(
      (data) => {
        if (!ctl.signal.aborted) setSettled({ key, data, error: null });
      },
      (err: unknown) => {
        if (ctl.signal.aborted) return;
        const error = toFailure(err);
        // keep the last good data of the same key on screen and say that refreshing failed
        setSettled((prev) => ({ key, data: prev !== null && prev.key === key ? prev.data : null, error }));
      },
    );
    return () => ctl.abort();
  }, [key, nonce, version]);

  const current = settled !== null && settled.key === key ? settled : null;
  const shouldPoll = current !== null && current.data !== null && active(current.data);
  useEffect(() => {
    if (!shouldPoll) return;
    const timer = window.setTimeout(() => setNonce((n) => n + 1), intervalMs);
    return () => window.clearTimeout(timer);
  }, [shouldPoll, settled, intervalMs]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const replace = useCallback(
    (data: T) => {
      if (key !== null) setSettled({ key, data, error: null });
    },
    [key],
  );

  let state: Polled<T> = { kind: "loading" };
  if (current !== null) {
    state =
      current.data !== null
        ? { kind: "ready", data: current.data, refreshError: current.error }
        : { kind: "error", error: current.error ?? toFailure(null) };
  }
  return { state, reload, replace };
}
