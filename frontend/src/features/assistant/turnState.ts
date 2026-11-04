import type { ChatRunState, ChatTurn } from "./api";

export const ACTIVE_STATES: readonly ChatRunState[] = ["queued", "running"];
export const isActiveTurn = (t: ChatTurn): boolean => ACTIVE_STATES.includes(t.state);

/** Plain-language label per run state; no state is rendered as success unless it is `completed`. */
export const STATE_LABEL: Record<ChatRunState, string> = {
  queued: "Queued",
  running: "Working",
  completed: "Answered",
  failed: "Failed",
  cancelled: "Cancelled",
  refused: "Refused",
  truncated: "Truncated: answer is incomplete",
};

export type AvatarState = "idle" | "thinking" | "answering" | "refusal-error";

export function avatarStateFor(turn: ChatTurn | null): AvatarState {
  if (turn === null) return "idle";
  switch (turn.state) {
    case "queued":
    case "running":
      return "thinking";
    case "completed":
    case "truncated":
      return "answering";
    case "failed":
    case "refused":
      return "refusal-error";
    default:
      return "idle";
  }
}

/** Text for the polite live region: announces progress and the finished state, once per change. */
export function announcementFor(turn: ChatTurn | null): string {
  if (turn === null) return "";
  switch (turn.state) {
    case "queued":
      return "Question queued.";
    case "running":
      return "Assistant is working on an answer.";
    case "completed":
      return "Assistant finished answering.";
    case "truncated":
      return "Assistant answer was truncated and is incomplete.";
    case "cancelled":
      return "Answer cancelled.";
    case "refused":
      return `Assistant refused: ${turn.failure?.message ?? "request not answered"}.`;
    case "failed":
      return `Assistant failed: ${turn.failure?.message ?? "no answer produced"}.`;
  }
}

export function failureHeadline(turn: ChatTurn): string {
  const code = turn.failure?.code;
  if (code === "provider_outage") return "The model provider is unavailable. No answer was produced.";
  if (turn.state === "refused" || code === "provider_refusal") return "The assistant refused this request.";
  if (turn.state === "cancelled") return "This answer was cancelled.";
  if (turn.state === "truncated") return "The answer hit a limit and is incomplete.";
  return "The assistant could not answer.";
}
