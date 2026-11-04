/**
 * Explore command bus (TASK-095, wave 0). A typed, ref-based fan-out so the assistant (AppLink),
 * the camera lane, the charts lane and the evidence viewer can ask the Explore stage to do things
 * without importing each other. Nothing here touches React state: subscribers live in a Set, so a
 * dispatch during a camera flight costs no render.
 *
 * Contract:
 *  - `dispatch` offers the command to every subscriber that registered a handler for its type, in
 *    registration order, and reports the aggregate outcome. A subscriber returns `true` when it
 *    acted, `false` when the target is unknown to it (stale/missing target), or throws never.
 *  - Outcomes: `handled` (some subscriber acted), `unhandled` (subscribers exist but none could act;
 *    the caller shows an explicit stale/missing-target message, AV-4), `no-subscriber` (nobody
 *    listens for that type) and `not-implemented` (flyOver/stopFlyOver until the camera lane lands).
 */

export const EXPLORE_COMMAND_TYPES = [
  "focusWellbore",
  "focusElement",
  "focusFormation",
  "openSource",
  "openChart",
  "flyOver",
  "stopFlyOver",
] as const;

export type ExploreCommandType = (typeof EXPLORE_COMMAND_TYPES)[number];

/** AppLink source locator (AV-3): a document plus a page or free-form locator. */
export interface SourceRef {
  documentId: string;
  page?: number;
  locator?: string;
}

/** Chart kinds are owned by the charts lane; kept an open string id here on purpose. */
export type ChartKindId = string;

export interface ChartWindow {
  /** Inclusive ISO dates or MD metres, interpreted by the chart kind. */
  from?: string | number;
  to?: string | number;
}

export interface ExploreCommandMap {
  focusWellbore: { wellboreId: string };
  focusElement: { wellboreId: string; elementId: string };
  focusFormation: { wellboreId: string; formationId: string };
  openSource: { source: SourceRef };
  openChart: { kind: ChartKindId; wellboreId: string | null; window?: ChartWindow };
  flyOver: { wellboreId: string };
  stopFlyOver: object;
}

export type ExploreCommand = {
  [K in ExploreCommandType]: { type: K } & ExploreCommandMap[K];
}[ExploreCommandType];

export type ExploreCommandOutcome = "handled" | "unhandled" | "no-subscriber" | "not-implemented";

export type ExploreCommandHandler<K extends ExploreCommandType> = (payload: ExploreCommandMap[K]) => boolean;
export type ExploreCommandHandlers = { [K in ExploreCommandType]?: ExploreCommandHandler<K> };

/** Fly-over is not implemented in wave 0; this is its documented state (CM-3/CM-4 land in the camera lane). */
export type FlyOverState = "not-implemented";
export const FLY_OVER_STATE: FlyOverState = "not-implemented";

export interface ExploreCommandBus {
  /** Register handlers; returns the unsubscribe function. Safe to call the unsubscribe twice. */
  subscribe(handlers: ExploreCommandHandlers): () => void;
  dispatch(command: ExploreCommand): ExploreCommandOutcome;
  /** Number of live subscribers (tests/diagnostics). */
  readonly size: number;
}

export function createExploreCommandBus(): ExploreCommandBus {
  const subscribers = new Set<ExploreCommandHandlers>();
  return {
    subscribe(handlers) {
      // Own entry per call so the same object can be registered twice and removed independently.
      const entry: ExploreCommandHandlers = { ...handlers };
      subscribers.add(entry);
      return () => {
        subscribers.delete(entry);
      };
    },
    dispatch(command) {
      if (command.type === "flyOver" || command.type === "stopFlyOver") return "not-implemented";
      let listening = false;
      let acted = false;
      for (const s of [...subscribers]) {
        const h = s[command.type] as ((p: unknown) => boolean) | undefined;
        if (h === undefined) continue;
        listening = true;
        if (h(command)) acted = true;
      }
      return acted ? "handled" : listening ? "unhandled" : "no-subscriber";
    },
    get size() {
      return subscribers.size;
    },
  };
}
