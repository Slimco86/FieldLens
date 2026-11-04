import { createContext, useContext } from "react";

/** Explore stage modes (XC-7): the 3D scene, the chart set, or both. */
export const STAGE_MODES = ["3d", "charts", "split"] as const;
export type StageMode = (typeof STAGE_MODES)[number];
export const STAGE_MODE_LABEL: Record<StageMode, string> = { "3d": "3D", charts: "Charts", split: "Split" };
export const DEFAULT_STAGE_MODE: StageMode = "3d";

/** What the Explore stage is showing: one wellbore or the whole field. Slots read this, never guess it. */
export type ExploreStageContext = { kind: "wellbore"; wellboreId: string } | { kind: "field" };

export interface ExploreStageState {
  mode: StageMode;
  context: ExploreStageContext;
}

const Ctx = createContext<ExploreStageState | null>(null);
export const ExploreStageProvider = Ctx.Provider;

/** Stage mode and wellbore/field context for slot content (null outside an ExploreWorkspace). */
export function useExploreStage(): ExploreStageState | null {
  return useContext(Ctx);
}

export const STAGE_MODE_STORAGE_KEY = "fieldlens.explore.stageMode";

export function isStageMode(v: unknown): v is StageMode {
  return typeof v === "string" && (STAGE_MODES as readonly string[]).includes(v);
}

export function readStageMode(storage: Pick<Storage, "getItem"> | null = safeStorage()): StageMode {
  try {
    const v = storage?.getItem(STAGE_MODE_STORAGE_KEY);
    return isStageMode(v) ? v : DEFAULT_STAGE_MODE;
  } catch {
    return DEFAULT_STAGE_MODE;
  }
}

export function writeStageMode(mode: StageMode, storage: Pick<Storage, "setItem"> | null = safeStorage()): void {
  try {
    storage?.setItem(STAGE_MODE_STORAGE_KEY, mode);
  } catch {
    /* persistence is best effort */
  }
}

function safeStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
