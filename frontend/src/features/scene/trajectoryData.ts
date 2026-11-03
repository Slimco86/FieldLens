import { useCallback, useEffect, useRef, useState } from "react";
import { loadTrajectory, type TrajectoryState } from "./trajectorySource";
import type { WellboreRef } from "./fieldData";

const CONCURRENCY = 4;

/**
 * Loads the survey of every wellbore for the field view (bounded concurrency like the asset specs,
 * aborted on unmount). A wellbore without a valid survey (404) or a failed read only affects that
 * wellbore: it keeps the labelled vertical placeholder with the reason.
 */
export function useFieldTrajectories(projectId: string, wellbores: readonly WellboreRef[]) {
  const [states, setStates] = useState<ReadonlyMap<string, TrajectoryState>>(new Map());
  const [attempt, setAttempt] = useState(0);
  const retryIds = useRef<Set<string> | null>(null);
  const key = wellbores.map((w) => w.id).join(",");

  useEffect(() => {
    const ctl = new AbortController();
    const only = retryIds.current;
    retryIds.current = null;
    const queue = wellbores.map((w) => w.id).filter((id) => only === null || only.has(id));
    if (only === null) setStates(new Map());
    else setStates((m) => new Map([...m].filter(([id]) => !only.has(id))));
    const worker = async () => {
      for (let id = queue.shift(); id !== undefined; id = queue.shift()) {
        let state: TrajectoryState;
        try {
          state = await loadTrajectory(projectId, id, ctl.signal);
        } catch {
          return; // aborted
        }
        if (ctl.signal.aborted) return;
        const settled = state;
        const wellboreId = id;
        setStates((m) => new Map(m).set(wellboreId, settled));
      }
    };
    void Promise.all(Array.from({ length: Math.min(CONCURRENCY, queue.length) }, worker));
    return () => ctl.abort();
    // `key` stands for the wellbore id list; names do not affect what is loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, key, attempt]);

  const retry = useCallback(() => {
    retryIds.current = null;
    setAttempt((n) => n + 1);
  }, []);
  return { trajectories: states, retry };
}
