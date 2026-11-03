import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { getAssetSpec } from "./api";
import type { FieldSpecState } from "./fieldModel";

export interface WellboreRef {
  id: string;
  name: string;
}

const CONCURRENCY = 4;

/**
 * Loads the current asset spec of every wellbore (bounded concurrency, aborted on unmount). The
 * existing per-wellbore route is used: a project of ~12 wellbores costs 12 small reads, so no new
 * endpoint is needed. A 404 means "no spec yet" (a labelled placeholder), anything else is a failure
 * that can be retried for that wellbore only.
 */
export function useFieldSpecs(projectId: string, wellbores: readonly WellboreRef[]) {
  const [specs, setSpecs] = useState<ReadonlyMap<string, FieldSpecState>>(new Map());
  const [attempt, setAttempt] = useState(0);
  const retryIds = useRef<Set<string> | null>(null);
  const key = wellbores.map((w) => w.id).join(",");

  useEffect(() => {
    const ctl = new AbortController();
    const only = retryIds.current;
    retryIds.current = null;
    const queue = wellbores.map((w) => w.id).filter((id) => only === null || only.has(id));
    if (only === null) setSpecs(new Map());
    else setSpecs((m) => new Map([...m].filter(([id]) => !only.has(id))));
    const worker = async () => {
      for (let id = queue.shift(); id !== undefined; id = queue.shift()) {
        let state: FieldSpecState;
        try {
          const rec = await getAssetSpec(projectId, id, ctl.signal);
          state = { kind: "ready", spec: rec.spec, revision: rec.revision };
        } catch (e) {
          if (ctl.signal.aborted) return;
          state = e instanceof ApiError && e.status === 404 ? { kind: "missing" } : { kind: "error", message: e instanceof Error ? e.message : "The spec could not be loaded." };
        }
        if (ctl.signal.aborted) return;
        const settled = state;
        const wellboreId = id;
        setSpecs((m) => new Map(m).set(wellboreId, settled));
      }
    };
    void Promise.all(Array.from({ length: Math.min(CONCURRENCY, queue.length) }, worker));
    return () => ctl.abort();
    // `key` stands for the wellbore id list; names do not affect what is loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, key, attempt]);

  const retry = useCallback((ids?: readonly string[]) => {
    retryIds.current = ids === undefined ? null : new Set(ids);
    setAttempt((n) => n + 1);
  }, []);
  return { specs, retry };
}
