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
  partial: "Partial: the stages that could run finished; others are not available yet. This is not a finished reconstruction.",
  failed: "This run failed. Nothing was completed.",
  cancelled: "This run was cancelled before it finished.",
  interrupted: "This run was interrupted and did not finish.",
};

export const STAGE_NAME: Record<StageName, string> = {
  gather: "Gather",
  extract: "Extract",
  identify: "Identify",
  assemble: "Assemble",
};

const AGENT_NOUN: Partial<Record<StageName, string>> = { extract: "extraction", identify: "merge identification" };

/** Label of a stage in the plain words a user needs; "not available" always names what is missing. */
export function stageStateLabel(s: Pick<ReconstructionStage, "stage" | "state" | "reason_code">): string {
  const map: Record<StageState, string> = {
    pending: "Pending",
    running: "Running",
    succeeded: "Done",
    not_available: `Not available yet: agent ${AGENT_NOUN[s.stage] ?? s.stage}`,
    failed: "Failed",
    cancelled: "Cancelled",
    interrupted: "Interrupted",
    skipped: "Skipped",
  };
  return map[s.state];
}

export function reasonText(code: string | null): string | null {
  if (code === null) return null;
  return code === "agent_step_not_implemented" ? "the agent step is not implemented in this build" : code.replace(/_/g, " ");
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
