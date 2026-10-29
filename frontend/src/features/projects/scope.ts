import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";

export interface Failure {
  message: string;
  requestId: string | null;
  status: number | null;
  code: string | null;
}

export function toFailure(err: unknown): Failure {
  if (err instanceof ApiError) {
    return { message: err.message, requestId: err.requestId, status: err.status, code: err.code };
  }
  return { message: "The local API is unreachable.", requestId: null, status: null, code: null };
}

type Settled<T> = { key: string; ok: true; data: T } | { key: string; ok: false; error: Failure };
export type Resource<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T }
  | { kind: "error"; error: Failure };

/**
 * Loads one keyed read. A change of key (or unmount) aborts the pending request and a result
 * stamped with any other key is never rendered: the derived state is "loading" instead.
 */
export function useScopedResource<T>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
) {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });
  const fullKey = key === null ? null : `${key}#${attempt}`;

  useEffect(() => {
    if (fullKey === null) return;
    const ctl = new AbortController();
    loadRef.current(ctl.signal).then(
      (data) => {
        if (!ctl.signal.aborted) setSettled({ key: fullKey, ok: true, data });
      },
      (err: unknown) => {
        if (!ctl.signal.aborted) setSettled({ key: fullKey, ok: false, error: toFailure(err) });
      },
    );
    return () => ctl.abort();
  }, [fullKey]);

  let state: Resource<T> = { kind: "loading" };
  if (settled !== null && settled.key === fullKey) {
    state = settled.ok ? { kind: "ready", data: settled.data } : { kind: "error", error: settled.error };
  }
  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const replace = useCallback(
    (data: T) => {
      if (fullKey !== null) setSettled({ key: fullKey, ok: true, data });
    },
    [fullKey],
  );
  return { state, reload, replace };
}

export type Outcome<T> =
  | { status: "ok"; value: T }
  | { status: "error"; error: Failure }
  | { status: "stale" };

/**
 * Runs user actions for one context. Switching context (key change) or unmounting aborts the
 * request and any later acknowledgement resolves as "stale", so callers cannot show it.
 */
export function useActionScope(key: string) {
  const current = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => current.current?.abort();
  }, [key]);
  return useCallback(async <T,>(action: (signal: AbortSignal) => Promise<T>): Promise<Outcome<T>> => {
    current.current?.abort();
    const ctl = new AbortController();
    current.current = ctl;
    try {
      const value = await action(ctl.signal);
      return ctl.signal.aborted ? { status: "stale" } : { status: "ok", value };
    } catch (err) {
      return ctl.signal.aborted ? { status: "stale" } : { status: "error", error: toFailure(err) };
    }
  }, []);
}
