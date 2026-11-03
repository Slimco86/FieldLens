import { useRef, type KeyboardEvent } from "react";
import type { SceneModel, SceneElement } from "./sceneModel";
import { KIND_LABEL } from "./sceneModel";
import styles from "./Scene.module.css";

interface Props {
  model: SceneModel;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const GROUPS: { key: "downhole" | "surface" | "unlocated"; title: string }[] = [
  { key: "downhole", title: "Downhole (by measured depth)" },
  { key: "surface", title: "Surface facilities" },
  { key: "unlocated", title: "Unlocated components" },
];

/** Keyboard-navigable component list: arrows move focus, Enter/Space selects (and flies to it). */
export function ComponentList({ model, selectedId, onSelect }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const move = (e: KeyboardEvent<HTMLDivElement>) => {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(e.key) || root.current === null) return;
    const items = Array.from(root.current.querySelectorAll<HTMLButtonElement>("button[data-element-id]"));
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    let next = at;
    if (e.key === "ArrowDown") next = Math.min(items.length - 1, at + 1);
    if (e.key === "ArrowUp") next = Math.max(0, at - 1);
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = items.length - 1;
    e.preventDefault();
    items[next]?.focus();
  };
  return (
    // Key events bubble from the real buttons inside; the wrapper only adds arrow-key roving focus.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <div ref={root} onKeyDown={move} role="group" aria-label="Components" data-testid="component-list">
      {GROUPS.map(({ key, title }) => {
        const els: SceneElement[] = model[key];
        if (els.length === 0) return null;
        return (
          <section key={key} aria-label={title}>
            <h3 className={styles.groupTitle}>
              {title} ({els.length})
            </h3>
            <ul className={styles.list}>
              {els.map((el) => (
                <li key={el.id}>
                  <button
                    type="button"
                    className={styles.item}
                    data-element-id={el.id}
                    aria-pressed={el.id === selectedId}
                    onClick={() => onSelect(el.id)}
                  >
                    {el.label}
                    <span className={styles.itemKind}>
                      {KIND_LABEL[el.kind]} · {el.illustrative ? "illustrative" : "documented"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
