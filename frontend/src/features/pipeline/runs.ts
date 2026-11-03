import type { components } from "../../api/generated";
import type { ReconstructionRun, ReconstructionStage } from "./api";

type S = components["schemas"];
export type RunStatus = S["ReconstructionRunStatus"];
type StageName = S["ReconstructionStageName"];
type StageState = S["ReconstructionStageState"];

/** Statuses that still change on the server; only these are polled. */
export const ACTIVE_STATUSES: ReadonlySet<RunStatus> = new Set(["queued", "running"]);

export const isActive = (r: Pick<ReconstructionRun, "status">) => ACTIVE_STATUSES.has(r.status);

/** Honest status words: `partial` is never worded as processed, complete or succeeded. */
export const STATUS_LABEL: Record<RunStatus, string> = {
  estimated: "Estimated, not confirmed",
  queued: "Queued",
  running: "Running",
  partial: "Partial",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
  interrupted: "Interrupted",
};

export const STATUS_NOTE: Partial<Record<RunStatus, string>> = {
  partial: "Partial: the run finished but not every stage did real work (see the stages below). This is a draft, not a finished reconstruction.",
  failed: "This run failed. Nothing was completed.",
  cancelled: "This run was cancelled before it finished.",
  interrupted: "This run was interrupted and did not finish.",
};

export const STAGE_NAME: Record<StageName, string> = {
  gather: "Collect sources",
  extract: "Read documents",
  identify: "Match wellbores",
  assemble: "Assemble data",
  design: "Design 3D asset",
};

/** Plain-language numbered label used in lists, e.g. "S2 Read documents". */
export const stageLabel = (s: StageName): string => `S${Object.keys(STAGE_NAME).indexOf(s) + 1} ${STAGE_NAME[s]}`;

/** Label of a stage in the plain words a user needs; a stub or not-wired stage never reads as done. */
export function stageStateLabel(s: Pick<ReconstructionStage, "stage" | "state" | "reason_code">): string {
  const map: Record<StageState, string> = {
    pending: "Pending",
    running: "Running",
    succeeded: "Done",
    not_available: s.stage === "design" ? "The 3D model step is not available yet" : "Not wired in this build",
    stubbed: "Not available: no model configured",
    failed: "Failed",
    cancelled: "Cancelled",
    interrupted: "Interrupted",
    skipped: "Skipped",
  };
  return map[s.state];
}

export function reasonText(code: string | null): string | null {
  if (code === null) return null;
  if (code === "agent_step_not_implemented") return "the agent step is not implemented in this build";
  if (code === "asset_design_not_wired") return "the 3D design step is not part of this build";
  if (code === "stub_provider") return "no model configured";
  return code.replace(/_/g, " ");
}

/** The newest confirmed run per wellbore (estimates that were never confirmed are not runs). */
export function latestByWellbore(runs: ReconstructionRun[]): Map<string, ReconstructionRun> {
  const out = new Map<string, ReconstructionRun>();
  for (const r of runs) {
    if (r.status === "estimated") continue;
    const cur = out.get(r.wellbore_id);
    if (cur === undefined || r.created_at > cur.created_at) out.set(r.wellbore_id, r);
  }
  return out;
}

export function usd(value: string): string {
  return `USD ${value}`;
}
