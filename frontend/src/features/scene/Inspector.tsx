import type { SceneElement } from "./sceneModel";
import { KIND_LABEL, REPRESENTATION_LABEL, placementText } from "./sceneModel";
import { KeyValue, KeyValueList } from "../../design";
import styles from "./Scene.module.css";

const DIM_TEXT = { spec: "from spec", default: "default (illustrative)", interval: "from interval", derived: "derived" } as const;
const has = <T,>(v: T | null | undefined): v is T => v !== null && v !== undefined;
const fmt = (m: number) => `${Math.round(m * 1000) / 1000} m`;

/** Details of the selected element, including every evidence reference and the visual reference. */
export function Inspector({ element }: { element: SceneElement | null }) {
  if (element === null) {
    return (
      <div className={styles.inspector} data-testid="inspector">
        <p className={styles.note}>Select a component in the list or the scene to see its details.</p>
      </div>
    );
  }
  const s = element.source;
  const ref = s.visual_reference;
  return (
    <div className={styles.inspector} data-testid="inspector">
      <h3 data-testid="inspector-label">{element.label}</h3>
      <KeyValueList compact>
        <KeyValue term="Kind">{KIND_LABEL[element.kind]}</KeyValue>
        <KeyValue term="Placement">
          <span data-testid="inspector-placement">{placementText(element)}</span>
        </KeyValue>
        <KeyValue term="Representation">
          <span data-testid="inspector-representation">{REPRESENTATION_LABEL[element.representation]}</span>
        </KeyValue>
        <KeyValue term="Outer diameter">
          {fmt(element.outerRadiusM * 2)} ({DIM_TEXT[element.dims.od]})
        </KeyValue>
        <KeyValue term="Length">
          {fmt(element.lengthM)} ({DIM_TEXT[element.dims.length]})
        </KeyValue>
      </KeyValueList>
      {has(s.confidence_note) && <p className={styles.note}>{s.confidence_note}</p>}
      <h4>Evidence</h4>
      {(s.evidence ?? []).length === 0 ? (
        <p className={styles.note} data-testid="inspector-no-evidence">No evidence references: this component is not source-backed.</p>
      ) : (
        <ul className={styles.evidence} data-testid="inspector-evidence">
          {(s.evidence ?? []).map((e, i) => (
            <li key={i}>
              {has(e.document_id) ? `Document ${e.document_id}` : "Candidate"}
              {has(e.page) ? `, page ${e.page}` : ""}
              {has(e.candidate_id) ? ` (candidate ${e.candidate_id})` : ""}
              {has(e.quote) ? `: “${e.quote}”` : ""}
            </li>
          ))}
        </ul>
      )}
      {has(ref) && (
        <p data-testid="inspector-visual-reference">
          Visual reference:{" "}
          {has(ref.url) && /^https?:\/\//i.test(ref.url) ? (
            <a href={ref.url} target="_blank" rel="noopener noreferrer">
              {ref.title ?? ref.url}
            </a>
          ) : (
            (ref.title ?? "see note")
          )}
          {has(ref.note) ? ` — ${ref.note}` : ""}
        </p>
      )}
    </div>
  );
}
