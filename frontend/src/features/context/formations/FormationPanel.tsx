import { useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useExploreCommandBus, useExploreCommandHandlers } from "../../scene/ExploreCommandsContext";
import { RENDER_ORIGIN } from "../../scene/sceneLayers";
import {
  buildFormationScene,
  inspectorModel,
  openFormationSource,
  requestFocusFormation,
  resolveFormationId,
  type InspectorModel,
  type NotDrawnItem,
} from "./formationModel";
import type { FormationStore, LabelMode } from "./formationStore";
import type { FormationLayersState } from "./useFormationLayers";
import type { LegendItem } from "./formationModel";
import { LEVEL_PLANE_LABEL, type EvidenceLink } from "./formationTypes";
import styles from "./Formations.module.css";

export interface FormationPanelProps {
  state: FormationLayersState;
  store: FormationStore;
  /** Selected wellbore (wellbore view) or null (field view); scopes `focusFormation` commands. */
  wellboreId: string | null;
}

/**
 * Layer toggle, legend, reasons for items that are not drawn, and the formation inspector (name, MD/TVD/TVDSS with
 * original units and datum, tier, status, qualifier, extraction method, source links). DOM-side companion of
 * `FormationLayer`; the two share only the presentation store. Also answers the `focusFormation` command bus message
 * by selecting the formation (the camera lane moves the camera from `formationFocusTarget`).
 */
export function FormationPanel({ state, store, wellboreId }: FormationPanelProps) {
  const opts = useSyncExternalStore(store.subscribe, store.getState, store.getState);
  const bus = useExploreCommandBus();
  const [message, setMessage] = useState<string | null>(null);
  const data = state.data;
  // While this panel itself dispatches focusFormation, its own handler must not count as the camera acting.
  const selfDispatch = useRef(false);
  const scene = useMemo(() => buildFormationScene(data, { origin: RENDER_ORIGIN }), [data]);
  const { drawn, undrawn } = useMemo(() => groupLegend(scene.legend), [scene]);

  useExploreCommandHandlers({
    focusFormation: (p) => {
      if (selfDispatch.current) return false;
      if (wellboreId !== null && p.wellboreId !== wellboreId) return false;
      const id = resolveFormationId(data, p.formationId, p.wellboreId);
      if (id === null) return false;
      store.select(id);
      return true;
    },
  });

  const shownId = opts.hoverId ?? opts.selectedId;
  const info = useMemo(() => inspectorModel(data, shownId), [data, shownId]);

  const focus = (id: string, wb: string | null) => {
    store.select(id);
    const target = wb ?? wellboreId;
    if (target === null) return;
    selfDispatch.current = true;
    try {
      const r = requestFocusFormation(bus, target, id);
      // This panel itself subscribes to focusFormation (to answer assistant/list requests), so an "unhandled" outcome here
      // means no camera acted (none registered, or it refused); the formation is selected either way.
      setMessage(r.outcome === "unhandled" ? "The camera did not move: no camera is available for this view, or the formation is stale." : r.message);
    } finally {
      selfDispatch.current = false;
    }
  };

  return (
    <section className={styles.panel} aria-label="Formation layer" data-testid="formation-panel">
      <h3 className={styles.heading}>Formations</h3>
      {state.status === "idle" && <p role="status">Select a project to see formations.</p>}
      {state.status === "loading" && <p role="status">Loading formations…</p>}
      {state.status === "error" && (
        <p role="alert">Formations unavailable: {state.error} The wellbore, equipment and other layers are unaffected.</p>
      )}
      {state.status === "empty" && <p role="status">{state.data.empty_reason ?? "No formation picks for this scope"}</p>}
      {data !== null && state.status !== "empty" && (
        <>
          <div className={styles.row}>
            <label>
              <input type="checkbox" checked={opts.visible} onChange={(e) => store.setVisible(e.target.checked)} /> Show formations
            </label>
            <label>
              Plane opacity{" "}
              <input
                type="range"
                min={0.05}
                max={0.6}
                step={0.05}
                value={opts.planeOpacity}
                onChange={(e) => store.setPlaneOpacity(Number(e.target.value))}
                aria-valuetext={`${Math.round(opts.planeOpacity * 100)} percent`}
              />
            </label>
            <label>
              Labels{" "}
              <select value={opts.labelMode} onChange={(e) => store.setLabelMode(e.target.value as LabelMode)}>
                <option value="all">All</option>
                <option value="selected">Selected only</option>
                <option value="off">Off</option>
              </select>
            </label>
          </div>
          {scene.emptyText !== null && <p role="status">{scene.emptyText}</p>}
          <ul className={styles.list} aria-label="Formation legend">
            {drawn.map((g) => (
              <li key={g.keys.join("|")} className={styles.item} data-testid="formation-legend-item">
                <span className={styles.row}>
                  <input
                    type="checkbox"
                    aria-label={`Show ${g.item.name}`}
                    checked={g.keys.every((k) => !opts.hidden.has(k))}
                    onChange={(e) => g.keys.forEach((k) => opts.hidden.has(k) === e.target.checked && store.toggleSurface(k))}
                  />
                  <span className={styles.glyph} style={{ color: g.item.color }} aria-hidden="true">
                    {g.item.glyph}
                  </span>
                  <button type="button" className={`${styles.link} ${styles.name}`} onClick={() => focus(firstId(data, g.keys[0]!) ?? g.keys[0]!, null)}>
                    {g.item.name}
                  </button>
                  {g.keys.length > 1 && <span className={styles.muted}>×{g.keys.length}</span>}
                </span>
                <span className={styles.muted}>
                  {g.item.tierLabel} · {g.item.status} · {g.markerCount} marker{g.markerCount === 1 ? "" : "s"}
                  {g.item.planeDrawn ? ` · ${LEVEL_PLANE_LABEL}` : ""}
                </span>
              </li>
            ))}
          </ul>
          <NotDrawn items={scene.notDrawn} hiddenSurfaces={undrawn.length} />
        </>
      )}
      <p className={styles.muted}>
        Level planes are {LEVEL_PLANE_LABEL}, drawn at true scale (not exaggerated), not an interpreted horizon. Shape and name identify each surface; colour is only a hint.
      </p>
      {info !== null && <Inspector info={info} hovering={opts.hoverId !== null && opts.hoverId !== opts.selectedId} onFocus={() => focus(info.id, info.wellboreId)} onOpen={(l) => setMessage(openFormationSource(bus, l).message)} />}
      <p role="status" aria-live="polite" data-testid="formation-message">
        {message}
      </p>
    </section>
  );
}

function firstId(data: NonNullable<FormationLayersState["data"]>, surfaceKey: string): string | undefined {
  return resolveFormationId(data, surfaceKey) ?? undefined;
}

interface LegendGroup {
  item: LegendItem;
  keys: string[];
  markerCount: number;
}

/**
 * Only surfaces that are drawn (a placed marker or a drawn plane) are listed. Drawn rows with the same name and the
 * same draw state are one row with a count; toggling it applies to every surface in the group.
 */
export function groupLegend(legend: LegendItem[]): { drawn: LegendGroup[]; undrawn: LegendItem[] } {
  const drawn = new Map<string, LegendGroup>();
  const undrawn: LegendItem[] = [];
  for (const l of legend) {
    if (l.markerCount === 0 && !l.planeDrawn) {
      undrawn.push(l);
      continue;
    }
    const k = [l.name, l.tier, l.status, l.planeDrawn, l.shape].join("|");
    const g = drawn.get(k);
    if (g) {
      g.keys.push(l.surfaceKey);
      g.markerCount += l.markerCount;
    } else drawn.set(k, { item: l, keys: [l.surfaceKey], markerCount: l.markerCount });
  }
  return { drawn: [...drawn.values()], undrawn };
}

/** One collapsed summary instead of a card per undrawn item; reasons stay available inside the disclosure. */
function NotDrawn({ items, hiddenSurfaces }: { items: NotDrawnItem[]; hiddenSurfaces: number }) {
  const total = Math.max(items.length, hiddenSurfaces);
  if (total === 0) return null;
  const counts = new Map<string, number>();
  for (const i of items) counts.set(i.reason, (counts.get(i.reason) ?? 0) + 1);
  const summary = [...counts].map(([r, n]) => `${r} ×${n}`).join(", ");
  return (
    <details className={styles.notDrawn} data-testid="formation-not-drawn-summary">
      <summary>
        {total} formation{total === 1 ? "" : "s"} not drawn{summary === "" ? "" : ` (${summary})`}
      </summary>
      <ul className={styles.list} aria-label="Formation items not drawn">
        {items.map((i) => (
          <li key={i.id} className={styles.muted} data-testid="formation-not-drawn">
            {i.name}: {i.kind} ({i.reason}): {i.message}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Inspector({ info, hovering, onFocus, onOpen }: { info: InspectorModel; hovering: boolean; onFocus: () => void; onOpen: (l: EvidenceLink) => void }) {
  return (
    <div role="region" aria-label="Formation details" data-testid="formation-inspector">
      <h4 className={styles.heading}>
        {info.title}
        {hovering ? " (hover)" : ""}
      </h4>
      <p className={styles.muted}>
        {info.tierLabel} · {info.statusText}
      </p>
      <dl className={styles.facts}>
        {info.rows.map((r) => (
          <div key={r.label} style={{ display: "contents" }}>
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
      {info.notes.map((n) => (
        <p key={n} className={styles.muted}>
          {n}
        </p>
      ))}
      <div className={styles.row}>
        {info.evidence.length === 0 ? (
          <span className={styles.muted}>No source link stored for this item.</span>
        ) : (
          info.evidence.map((l, i) => (
            <button key={i} type="button" className={styles.button} onClick={() => onOpen(l)}>
              Open source {evidenceText(l, i)}
            </button>
          ))
        )}
        {info.wellboreId !== null && (
          <button type="button" className={styles.button} onClick={onFocus}>
            Focus camera
          </button>
        )}
      </div>
    </div>
  );
}

function evidenceText(l: EvidenceLink, i: number): string {
  const loc = l.locator as { kind: string; page?: number };
  return loc.kind === "pdf" && typeof loc.page === "number" ? `(page ${loc.page})` : `(${i + 1}: ${loc.kind})`;
}
