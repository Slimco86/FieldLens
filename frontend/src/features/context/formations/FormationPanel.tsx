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
            {scene.legend.map((l) => (
              <li key={l.surfaceKey} className={styles.item} data-testid="formation-legend-item">
                <span className={styles.row}>
                  <input type="checkbox" aria-label={`Show ${l.name}`} checked={!opts.hidden.has(l.surfaceKey)} onChange={() => store.toggleSurface(l.surfaceKey)} />
                  <span className={styles.glyph} style={{ color: l.color }} aria-hidden="true">
                    {l.glyph}
                  </span>
                  <button type="button" className={`${styles.link} ${styles.name}`} onClick={() => focus(firstId(data, l.surfaceKey) ?? l.surfaceKey, null)}>
                    {l.name}
                  </button>
                </span>
                <span className={styles.muted}>
                  {l.tierLabel} · {l.status} · {l.markerCount} marker{l.markerCount === 1 ? "" : "s"}
                  {l.planeDrawn ? ` · ${LEVEL_PLANE_LABEL}` : ""}
                </span>
                {l.planeBlocked.map((r) => (
                  <span key={r} className={styles.reason}>
                    Plane not drawn: {r}
                  </span>
                ))}
              </li>
            ))}
          </ul>
          {scene.notDrawn.length > 0 && <NotDrawn items={scene.notDrawn} />}
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

function NotDrawn({ items }: { items: NotDrawnItem[] }) {
  return (
    <div>
      <h4 className={styles.heading}>Not drawn ({items.length})</h4>
      <ul className={styles.list} aria-label="Formation items not drawn">
        {items.map((i) => (
          <li key={i.id} className={styles.item} data-testid="formation-not-drawn">
            <span className={styles.name}>{i.name}</span>
            <span className={styles.reason}>
              {i.kind} ({i.reason}): {i.message}
            </span>
          </li>
        ))}
      </ul>
    </div>
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
