/**
 * Explore command bus (TASK-095, wave 0). A typed, ref-based fan-out so the assistant (AppLink),
 * the camera lane, the charts lane and the evidence viewer can ask the Explore stage to do things
 * without importing each other. Nothing here touches React state: subscribers live in a Set, so a
 * dispatch during a camera flight costs no render.
 *
 * Contract:
 *  - `dispatch` offers the command to every subscriber that registered a handler for its type, in
 *    registration order, and reports the aggregate outcome. A subscriber returns `true` when it
 *    acted, `false` when the target is unknown to it (stale/missing target) or `"defer"` when it is
 *    mounted but not ready (its imperative commands are not set up yet).
 *  - Outcomes: `handled` (some subscriber acted), `unhandled` (subscribers exist but none could act;
 *    the caller shows an explicit stale/missing-target message, AV-4), `no-subscriber` (nobody
 *    listens for that type and the command is not queueable) and `queued` (nobody could act yet; a
 *    focus/fly-over command is kept for a short, bounded time and replayed when a viewer subscribes
 *    or calls `replay()`; callers should treat it as "pending", not as success).
 *  - A throwing subscriber is isolated: it counts as not having acted and the others still run.
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

export type ExploreCommandOutcome = "handled" | "unhandled" | "no-subscriber" | "queued";

/** `true` acted, `false` target unknown to this subscriber, `"defer"` mounted but not ready yet (keep the command pending). */
export type ExploreCommandHandler<K extends ExploreCommandType> = (payload: ExploreCommandMap[K]) => boolean | "defer";
export type ExploreCommandHandlers = { [K in ExploreCommandType]?: ExploreCommandHandler<K> };

/** Fly-over is implemented by the camera lane (TASK-096) for the single-wellbore viewer only. */
export type FlyOverState = "implemented";
export const FLY_OVER_STATE: FlyOverState = "implemented";

/** Commands worth holding for a viewer that has not mounted yet (navigation intent, not data requests). */
const QUEUEABLE: ReadonlySet<ExploreCommandType> = new Set(["focusWellbore", "focusElement", "focusFormation", "flyOver"]);
/** Focus commands supersede each other (last value wins); fly-over keeps its own slot. */
const slotOf = (c: ExploreCommand): string => (c.type === "flyOver" ? "flyOver" : "focus");

export const PENDING_TTL_MS = 5000;
export const PENDING_MAX = 4;

export interface ExploreCommandBusOptions {
  now?: () => number;
  ttlMs?: number;
  maxPending?: number;
  /** Receives exceptions thrown by subscribers (default: console.error). */
  onError?: (error: unknown, command: ExploreCommand) => void;
}

export interface ExploreCommandBus {
  /** Register handlers; returns the unsubscribe function. Safe to call the unsubscribe twice. Replays pending commands. */
  subscribe(handlers: ExploreCommandHandlers): () => void;
  dispatch(command: ExploreCommand): ExploreCommandOutcome;
  /** Retry pending commands (a viewer calls this once its imperative commands are ready). */
  replay(): void;
  /** Number of live subscribers (tests/diagnostics). */
  readonly size: number;
  /** Number of unexpired queued commands (tests/diagnostics). */
  readonly pending: number;
}

export function createExploreCommandBus(options: ExploreCommandBusOptions = {}): ExploreCommandBus {
  const now = options.now ?? (() => Date.now());
  const ttlMs = options.ttlMs ?? PENDING_TTL_MS;
  const maxPending = options.maxPending ?? PENDING_MAX;
  const onError = options.onError ?? ((e) => console.error("Explore command subscriber failed", e));
  const subscribers = new Set<ExploreCommandHandlers>();
  let queue: { command: ExploreCommand; expires: number }[] = [];

  const prune = () => {
    const t = now();
    queue = queue.filter((q) => q.expires > t);
  };

  /** Offer to the given subscribers; reports whether any listened and whether any acted. */
  const offer = (command: ExploreCommand, targets: Iterable<ExploreCommandHandlers>): { listening: boolean; acted: boolean; deferred: boolean } => {
    let listening = false;
    let acted = false;
    let deferred = false;
    for (const s of [...targets]) {
      const h = s[command.type] as ((p: unknown) => boolean | "defer") | undefined;
      if (h === undefined) continue;
      listening = true;
      try {
        const r = h(command);
        if (r === true) acted = true;
        else if (r === "defer") deferred = true;
      } catch (error) {
        try {
          onError(error, command);
        } catch {
          /* a failing error reporter must not break dispatch */
        }
      }
    }
    return { listening, acted, deferred };
  };

  const flush = (targets: Iterable<ExploreCommandHandlers>) => {
    prune();
    const list = [...targets];
    // Oldest first; a handled command leaves the queue, an unhandled one waits for the next chance.
    queue = queue.filter((q) => !offer(q.command, list).acted);
    // (Entries stay queued until acted on or expired; a refusing subscriber never consumes them.)
  };

  return {
    subscribe(handlers) {
      // Own entry per call so the same object can be registered twice and removed independently.
      const entry: ExploreCommandHandlers = { ...handlers };
      subscribers.add(entry);
      flush([entry]);
      return () => {
        subscribers.delete(entry);
      };
    },
    dispatch(command) {
      const { listening, acted, deferred } = offer(command, subscribers);
      if (acted) {
        // A newer handled command supersedes older pending ones in its slot.
        queue = queue.filter((q) => slotOf(q.command) !== slotOf(command));
        return "handled";
      }
      // Queue only when nobody is listening yet or a listener said it is not ready; a plain refusal
      // from a ready viewer is a stale/missing target and is reported as `unhandled` (AV-4).
      if (QUEUEABLE.has(command.type) && (!listening || deferred)) {
        prune();
        queue = queue.filter((q) => slotOf(q.command) !== slotOf(command));
        queue.push({ command, expires: now() + ttlMs });
        while (queue.length > maxPending) queue.shift();
        return "queued";
      }
      return listening ? "unhandled" : "no-subscriber";
    },
    replay() {
      flush(subscribers);
    },
    get size() {
      return subscribers.size;
    },
    get pending() {
      prune();
      return queue.length;
    },
  };
}
