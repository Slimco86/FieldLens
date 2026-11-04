import { createContext, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import {
  createExploreCommandBus,
  EXPLORE_COMMAND_TYPES,
  type ExploreCommandBus,
  type ExploreCommandHandlers,
  type ExploreCommandType,
} from "./exploreCommands";

const Ctx = createContext<ExploreCommandBus | null>(null);

/** Owns one bus for the Explore workspace; the bus identity never changes, so it never re-renders consumers. */
export function ExploreCommandsProvider({ children, bus }: { children: ReactNode; bus?: ExploreCommandBus }) {
  const owned = useMemo(() => bus ?? createExploreCommandBus(), [bus]);
  return <Ctx.Provider value={owned}>{children}</Ctx.Provider>;
}

/** The bus, or null outside a provider (viewers then simply have no external commander). */
export function useExploreCommandBus(): ExploreCommandBus | null {
  return useContext(Ctx);
}

/**
 * Register handlers for the lifetime of the component. The latest handlers are read through a ref,
 * so passing fresh closures every render neither re-subscribes nor allocates per frame. The
 * subscription changes only when the set of handled command types changes.
 */
export function useExploreCommandHandlers(handlers: ExploreCommandHandlers): void {
  const bus = useContext(Ctx);
  const ref = useRef(handlers);
  ref.current = handlers;
  const typesKey = EXPLORE_COMMAND_TYPES.filter((t) => handlers[t] !== undefined).join(",");
  useEffect(() => {
    if (bus === null || typesKey === "") return;
    const proxy: Record<string, unknown> = {};
    for (const t of typesKey.split(",") as ExploreCommandType[]) {
      proxy[t] = (payload: never) => {
        const h = ref.current[t] as ((p: never) => boolean) | undefined;
        return h === undefined ? false : h(payload);
      };
    }
    return bus.subscribe(proxy as ExploreCommandHandlers);
  }, [bus, typesKey]);
}
