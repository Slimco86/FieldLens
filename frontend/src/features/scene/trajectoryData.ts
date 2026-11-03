import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { getTrajectory } from "./api";
import type { WellboreRef } from "./fieldData";
import type { SurfaceLocation } from "./fieldModel";
import { loadTrajectory, toTrajectoryState, type TrajectoryState } from "./trajectorySource";

const CONCURRENCY = 4;

/** Planar surface location as stated by the survey route (null when only lat/lon or nothing is stated). */
export function planarSurface(t: { surface_location: { easting: number | null; northing: number | null; crs: string | null; geodetic_datum: string | null; unit: string | null } | null }): SurfaceLocation | null {
  const s = t.surface_location;
  if (s === null || s.easting === null || s.northing === null) return null;
  return { easting: s.easting, northing: s.northing, crs: s.crs, datum: s.geodetic_datum, unit: s.unit };
}

const CODE_TEXT: Record<string, string> = {
  TRAJECTORY_PLANNED_ONLY: "only a planned survey exists",
  TRAJECTORY_INVALID_STATIONS: "survey stations are invalid or conflicting",
  TRAJECTORY_MD_NOT_MONOTONIC: "measured depth does not increase",
  TRAJECTORY_TOO_FEW_STATIONS: "too few survey stations",
  TRAJECTORY_STATUS_CONFLICTING: "survey status is conflicting",
  TRAJECTORY_BLOCKING_ISSUE: "an extraction error blocks the geometry",
  AZIMUTH_REFERENCE_NOT_STATED: "the azimuth reference is not stated",
  WELLHEAD_START_UNKNOWN: "the first station is not at the wellhead and states no TVD",
};

function noSurvey(e: ApiError): TrajectoryState {
  if (e.details?.["code"] !== "no_trajectory") return { kind: "none", reason: "the wellbore was not found" };
  const raw = e.details?.["sets"];
  const codes = new Set<string>();
  for (const s of Array.isArray(raw) ? (raw as { reasons?: unknown }[]) : []) {
    if (Array.isArray(s.reasons)) for (const r of s.reasons) if (typeof r === "string") codes.add(r);
  }
  const text = [...codes].map((c) => CODE_TEXT[c] ?? c);
  return { kind: "none", reason: text.length > 0 ? `no valid survey: ${text.join("; ")}` : "no survey records for this wellbore" };
}

export interface FieldTrajectory {
  state: TrajectoryState;
  /** Structured planar surface location for the layout (the info panel keeps its own text). */
  surface: SurfaceLocation | null;
}

/** One survey read that returns both the drawn state and the structured surface location. */
export async function loadFieldTrajectory(projectId: string, wellboreId: string, signal: AbortSignal): Promise<FieldTrajectory> {
  if (typeof window !== "undefined" && window.__FIELDLENS_TEST_TRAJECTORY__?.[wellboreId] !== undefined) {
    return { state: await loadTrajectory(projectId, wellboreId, signal), surface: null };
  }
  try {
    const t = await getTrajectory(projectId, wellboreId, signal);
    return { state: toTrajectoryState(t), surface: planarSurface(t) };
  } catch (e) {
    if (signal.aborted) throw e;
    if (e instanceof ApiError && e.status === 404) return { state: noSurvey(e), surface: null };
    return { state: { kind: "error", reason: `the survey could not be loaded${e instanceof Error ? ` (${e.message})` : ""}` }, surface: null };
  }
}

interface Scheduler {
  ctl: AbortController;
  queue: string[];
  requested: Set<string>;
  active: number;
}

/**
 * Loads the survey of the GIVEN wellbores (the reconstructed ones) for the field view: bounded
 * concurrency, incremental (ids that arrive later, as specs resolve, are appended without refetching
 * the ones already requested), aborted on unmount. A wellbore without a valid survey (404) or a failed
 * read only affects that wellbore: it keeps the labelled vertical placeholder with the reason.
 */
export function useFieldTrajectories(projectId: string, wellbores: readonly WellboreRef[]) {
  const [loaded, setLoaded] = useState<ReadonlyMap<string, FieldTrajectory>>(new Map());
  const [attempt, setAttempt] = useState(0);
  const sched = useRef<Scheduler | null>(null);
  const loadedRef = useRef(loaded);
  loadedRef.current = loaded;
  const key = wellbores.map((w) => w.id).join(",");

  useEffect(() => {
    const s: Scheduler = { ctl: new AbortController(), queue: [], requested: new Set(), active: 0 };
    sched.current = s;
    setLoaded(new Map());
    return () => s.ctl.abort();
  }, [projectId]);

  useEffect(() => {
    const s = sched.current;
    if (s === null) return;
    for (const w of wellbores) {
      if (!s.requested.has(w.id)) {
        s.requested.add(w.id);
        s.queue.push(w.id);
      }
    }
    const pump = () => {
      while (s.active < CONCURRENCY && s.queue.length > 0 && !s.ctl.signal.aborted) {
        const id = s.queue.shift()!;
        s.active += 1;
        void loadFieldTrajectory(projectId, id, s.ctl.signal)
          .then((r) => {
            if (!s.ctl.signal.aborted) setLoaded((m) => new Map(m).set(id, r));
          })
          .catch(() => undefined) // aborted
          .finally(() => {
            s.active -= 1;
            pump();
          });
      }
    };
    pump();
    // `key` stands for the wellbore id list; names do not affect what is loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, key, attempt]);

  /** Re-reads the wellbores whose survey read failed (404 "no survey" is an answer, not a failure). */
  const retry = useCallback(() => {
    const s = sched.current;
    if (s === null) return;
    const failed = [...loadedRef.current].filter(([, v]) => v.state.kind === "error").map(([id]) => id);
    for (const id of failed) s.requested.delete(id);
    setLoaded((m) => new Map([...m].filter(([id]) => !failed.includes(id))));
    setAttempt((n) => n + 1);
  }, []);

  return { trajectories: loaded, retry };
}
