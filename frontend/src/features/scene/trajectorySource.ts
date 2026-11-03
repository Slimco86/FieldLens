import type { TrajectoryInput } from "./trajectory";

declare global {
  interface Window {
    /** Test-only injection: wellbore id -> stations (the survey API is not wired in this build). */
    __FIELDLENS_TEST_TRAJECTORY__?: Record<string, TrajectoryInput>;
  }
}

/**
 * Trajectory source for a wellbore. No survey API is wired yet, so this returns null (the viewer
 * then draws the labelled vertical placeholder). Tests may inject stations through the window
 * hook above; the real source replaces this function without touching the viewer.
 */
export function trajectoryFor(wellboreId: string): TrajectoryInput | null {
  if (typeof window === "undefined") return null;
  return window.__FIELDLENS_TEST_TRAJECTORY__?.[wellboreId] ?? null;
}
