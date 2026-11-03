import type { SceneElement } from "./sceneModel";
import { KIND_LABEL, REPRESENTATION_LABEL, placementText } from "./sceneModel";
import { KeyValue, KeyValueList } from "../../design";
import type { TrajectoryState } from "./trajectorySource";
import { useRoute } from "../../app/shell/route";
import { SourceLink } from "../documents/SourceLink";
import styles from "./Scene.module.css";

const DIM_TEXT = { spec: "from spec", default: "default (illustrative)", interval: "from interval", derived: "derived" } as const;
const has = <T,>(v: T | null | undefined): v is T => v !== null && v !== undefined;
const fmt = (m: number) => `${Math.round(m * 1000) / 1000} m`;

/** Details of the selected element, including every evidence reference and the visual reference. */
export function Inspector({ element, survey, projectId: projectIdProp }: { element: SceneElement | null; survey?: TrajectoryState | undefined; projectId?: string | undefined }) {
  const route = useRoute();
  const projectId = projectIdProp ?? (route.kind === "project" ? route.projectId : null);
  if (element === null) {
    return (
      <div className={styles.inspector} data-testid="inspector">
        <p className={styles.note}>Select a component in the list or the scene to see its details.</p>
        <SurveyPanel survey={survey} projectId={projectId} />
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
            <li key={i} data-testid="inspector-evidence-item">
              {has(e.document_id) && projectId !== null ? (
                <SourceLink
                  projectId={projectId}
                  documentId={e.document_id}
                  filename={e.filename}
                  page={e.page}
                  locator={e.locator ?? (has(e.page) ? `page ${e.page}` : null)}
                  statement={e.statement ?? e.quote}
                />
              ) : (
                <>
                  {has(e.document_id) ? "Document (filename unavailable)" : "Candidate"}
                  {has(e.page) ? `, page ${e.page}` : ""}
                  {has(e.quote) ? `: “${e.quote}”` : ""}
                </>
              )}
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
      <SurveyPanel survey={survey} projectId={projectId} />
    </div>
  );
}

/** Where the drawn trace comes from, the surface location with its CRS, and the sets that were not drawn. */
function SurveyPanel({ survey, projectId }: { survey: TrajectoryState | undefined; projectId: string | null }) {
  if (survey === undefined) return null;
  if (survey.kind === "loading") return <p className={styles.note}>Loading survey…</p>;
  if (survey.kind !== "ready") {
    return (
      <p className={styles.note} data-testid="survey-unavailable">
        Survey unavailable ({survey.reason}); the wellbore is drawn as a vertical placeholder, not a survey.
      </p>
    );
  }
  const i = survey.info;
  return (
    <section data-testid="survey-info" aria-label="Survey">
      <h4>Survey</h4>
      <p data-testid="survey-label">
        {i.source !== null && projectId !== null ? (
          <>
            Survey:{" "}
            <SourceLink projectId={projectId} documentId={i.source.documentId} filename={i.source.filename} page={i.source.page} format={i.source.format} linkOnly />
            {i.label.slice(`Survey: ${i.source.filename}`.length)}
          </>
        ) : (
          i.label
        )}
      </p>
      <p data-testid="survey-surface">{i.surfaceText ?? "Surface location: no validated location"}</p>
      <p className={styles.note}>{i.references}</p>
      <p className={styles.note}>{i.counts}</p>
      {i.others.length > 0 && (
        <ul className={styles.evidence} data-testid="survey-others">
          {i.others.map((o) => (
            <li key={o}>Not drawn: {o}</li>
          ))}
        </ul>
      )}
      {i.warnings.map((w) => (
        <p key={w} className={styles.note}>
          {w}
        </p>
      ))}
    </section>
  );
}
