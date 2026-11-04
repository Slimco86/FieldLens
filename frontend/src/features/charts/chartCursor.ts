import { createContext, createElement, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";

/**
 * Linked time cursor: the window currently selected by zooming/panning a chart. It lives in a small external
 * store (not React state), so zooming costs no render; only components that read it re-render. Charts on the
 * same provider follow each other; it is also the seam for the Explore workspace (read the window, fetch).
 */
export interface CursorWindow {
  /** What the numbers mean: ms since epoch for "time", metres for "depth". Windows of different axes never mix. */
  axis: "time" | "depth";
  from: number;
  to: number;
}

export interface ChartCursorStore {
  get(): CursorWindow | null;
  /** `origin` identifies the writer so it can ignore its own echo. */
  set(window: CursorWindow | null, origin: string): void;
  origin(): string | null;
  subscribe(listener: () => void): () => void;
}

export function createChartCursorStore(): ChartCursorStore {
  let current: CursorWindow | null = null;
  let last: string | null = null;
  const listeners = new Set<() => void>();
  return {
    get: () => current,
    origin: () => last,
    set(window, origin) {
      const same = current === window || (current !== null && window !== null && current.axis === window.axis && current.from === window.from && current.to === window.to);
      last = origin;
      if (same) return;
      current = window;
      for (const l of [...listeners]) l();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

const Ctx = createContext<ChartCursorStore | null>(null);

/** Shares one cursor among the charts below it. Identity of the store never changes. */
export function ChartCursorProvider({ children, store }: { children: ReactNode; store?: ChartCursorStore }) {
  const owned = useMemo(() => store ?? createChartCursorStore(), [store]);
  return createElement(Ctx.Provider, { value: owned }, children);
}

export function useChartCursorStore(): ChartCursorStore | null {
  return useContext(Ctx);
}

const NONE: ChartCursorStore = createChartCursorStore();

/** The selected window (null = whole record). Re-renders the caller only when the window changes. */
export function useChartCursor(): CursorWindow | null {
  const store = useContext(Ctx) ?? NONE;
  return useSyncExternalStore(store.subscribe, store.get, store.get);
}

/** ISO date (YYYY-MM-DD) of a time-axis window bound, for `from`/`to` query parameters. */
export const windowBoundToIsoDate = (ms: number): string => new Date(ms).toISOString().slice(0, 10);
