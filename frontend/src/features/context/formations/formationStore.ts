/**
 * Presentation state of the formation layer (toggles, opacity, label mode, selection, hover). A tiny external
 * store shared by the in-Canvas layer and the DOM panel: updates are events, never per-frame, and neither
 * side needs the other's React tree. Options are presentation only; they never change picks or depths (FO-5).
 */

export type LabelMode = "all" | "selected" | "off";

export interface FormationOptions {
  /** Master toggle for the whole layer. */
  visible: boolean;
  /** Surface keys switched off individually. */
  hidden: ReadonlySet<string>;
  /** Level-plane fill opacity before the cutaway reduction, 0.05..0.6. */
  planeOpacity: number;
  labelMode: LabelMode;
  selectedId: string | null;
  hoverId: string | null;
}

export const DEFAULT_OPTIONS: FormationOptions = Object.freeze({
  visible: true,
  hidden: new Set<string>(),
  planeOpacity: 0.22,
  labelMode: "all",
  selectedId: null,
  hoverId: null,
});

export interface FormationStore {
  getState(): FormationOptions;
  subscribe(listener: () => void): () => void;
  setVisible(v: boolean): void;
  toggleSurface(surfaceKey: string): void;
  setPlaneOpacity(v: number): void;
  setLabelMode(m: LabelMode): void;
  select(id: string | null): void;
  hover(id: string | null): void;
}

export function createFormationStore(initial: Partial<FormationOptions> = {}): FormationStore {
  let state: FormationOptions = { ...DEFAULT_OPTIONS, ...initial };
  const listeners = new Set<() => void>();
  const set = (patch: Partial<FormationOptions>) => {
    const next = { ...state, ...patch };
    if ((Object.keys(patch) as (keyof FormationOptions)[]).every((k) => state[k] === next[k])) return;
    state = next;
    for (const l of [...listeners]) l();
  };
  return {
    getState: () => state,
    subscribe(l) {
      listeners.add(l);
      return () => {
        listeners.delete(l);
      };
    },
    setVisible: (visible) => set({ visible }),
    toggleSurface(key) {
      const hidden = new Set(state.hidden);
      if (!hidden.delete(key)) hidden.add(key);
      set({ hidden });
    },
    setPlaneOpacity: (v) => set({ planeOpacity: Math.min(0.6, Math.max(0.05, Number.isFinite(v) ? v : DEFAULT_OPTIONS.planeOpacity)) }),
    setLabelMode: (labelMode) => set({ labelMode }),
    select: (selectedId) => set({ selectedId }),
    hover: (hoverId) => set({ hoverId }),
  };
}

/** Whether a surface (and its markers/plane) is shown under the current options. */
export const isSurfaceShown = (o: FormationOptions, surfaceKey: string): boolean => o.visible && !o.hidden.has(surfaceKey);
