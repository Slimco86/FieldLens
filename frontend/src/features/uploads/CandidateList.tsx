import { useState } from "react";
import { Button, Title } from "@mantine/core";
import { Callout, EmptyState, ErrorState, EvidenceClassChip, LoadingState, StatusChip } from "../../design";
import {
  listCandidates,
  type EvidenceLink,
  type ExtractionCandidate,
  type ExtractionCandidatePage,
  type SourceDocumentItem,
} from "./api";
import { usePolled } from "./usePolled";
import { toFailure, type Failure } from "../projects/scope";
import styles from "./CandidateList.module.css";

/** State is a kit chip: icon plus words, never color alone (AX-7). */
const STATE_TEXT: Record<ExtractionCandidate["state"], string> = {
  accepted: "Accepted by validators",
  flagged: "Flagged (needs attention)",
  rejected: "Rejected",
  candidate: "Unresolved candidate (not an accepted fact)",
};

const REASON: Record<string, string> = {
  locator_not_found: "the cited location does not exist",
  locator_unsupported: "the cited location type is not supported",
  quote_missing: "no quote from the source was given",
  quote_not_in_span: "the quote is not in the cited text",
  value_not_in_quote: "the value is not in the quote",
  attribute_unknown: "unknown attribute",
  unit_unparseable: "the unit could not be read",
  unit_dimension_mismatch: "the unit does not fit the attribute",
  unit_defaulted_meters: "no unit stated; meters assumed",
  out_of_range: "the value is outside the plausible range",
  md_tvd_confusion: "measured depth and true vertical depth were mixed",
  compound_depth_pair: "an MD/TVD pair was given as one value",
  subject_unresolved: "no matching well/wellbore identity",
  subject_document_mismatch: "the document's own records name a different wellbore",
  parsed_conflict: "disagrees with the parsed source value (the parsed value stays)",
  crs_not_stated: "no coordinate reference system stated",
  date_not_in_source: "the date is not in the quote",
  unit_conflicts_with_quote: "the unit differs from the one written in the quote",
  unit_not_in_source: "the unit is not stated by the quote or its context",
  number_unparseable: "the number is ambiguous and was not guessed",
  field_unverified: "some fields are not in the text layer and were removed",
  coordinate_fallback_unsupported: "coordinates and survey values are not accepted from a model",
  model_read_unverified: "read from a page image without a text layer; unverified",
};

function describe(link: EvidenceLink): string {
  const loc = link.locator;
  if (loc.kind === "pdf") return `pdf page ${loc.page}`;
  if (loc.kind === "text") return `text line ${loc.line_start}${loc.line_end !== loc.line_start ? `-${loc.line_end}` : ""}`;
  return loc.kind;
}

function valueText(c: ExtractionCandidate): string {
  const a = c.attributes;
  if (a.kind === "measurement") {
    return `${a.attribute_key}: ${a.value_text}${a.unit_as_written ? ` ${a.unit_as_written}` : a.unit_defaulted ? " (unit not stated)" : ""}`;
  }
  return [a.item_type, a.name, a.depth_text].filter((p): p is string => Boolean(p)).join(" - ");
}

function Candidate({
  c,
  describeLocator,
}: {
  c: ExtractionCandidate;
  describeLocator: (l: EvidenceLink) => string;
}) {
  const failed = c.validator_results.filter((v) => v.outcome === "failed" || v.outcome === "flagged");
  return (
    <li data-state={c.state} className={styles.item}>
      <div className={styles.chips}>
        <StatusChip kind="candidate" value={c.state} label={STATE_TEXT[c.state]} />
        <StatusChip kind="validation" value={c.validation_state} label={c.validation_state} />
        <EvidenceClassChip value={c.evidence_class} />
        <em className={styles.label}>[{c.label}]</em>
      </div>
      <div className={styles.value}>{valueText(c)}</div>
      <div className={styles.meta}>
        source: <code>{describeLocator(c.evidence) || describe(c.evidence)}</code>
        {c.quote !== null && c.quote !== undefined && <span className={styles.quote}> quote: &ldquo;{c.quote}&rdquo;</span>}
      </div>
      {c.reason_codes.length > 0 && (
        <div className={styles.meta}>reason: {c.reason_codes.map((r) => REASON[r] ?? r).join("; ")}</div>
      )}
      {failed.length > 0 && (
        <div className={styles.meta}>validators: {failed.map((v) => `${v.validator} ${v.outcome}`).join(", ")}</div>
      )}
    </li>
  );
}

/** Model-proposed candidates for one file: proposals, never source records. */
export function CandidateList({
  projectId,
  doc,
  describeLocator,
}: {
  projectId: string;
  doc: SourceDocumentItem;
  describeLocator: (l: EvidenceLink) => string;
}) {
  const { state, reload } = usePolled<ExtractionCandidatePage>(
    `candidates/${projectId}/${doc.document_id}`,
    (signal) => listCandidates(projectId, doc.document_id, signal),
    () => false,
  );
  const [more, setMore] = useState<ExtractionCandidate[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [moreError, setMoreError] = useState<Failure | null>(null);

  if (state.kind === "loading") return <LoadingState label="Loading model-proposed candidates…" status />;
  if (state.kind === "error") {
    return (
      <ErrorState
        message={`Model-proposed candidates could not be loaded: ${state.error.message}`}
        requestId={state.error.requestId}
        onRetry={reload}
        retryLabel="Retry loading candidates"
      />
    );
  }
  const page = state.data;
  const items = [...page.items, ...more];
  const next = cursor === undefined ? (page.page.next_cursor ?? null) : cursor;
  async function loadMore() {
    if (next === null) return;
    try {
      const res = await listCandidates(projectId, doc.document_id, new AbortController().signal, next);
      setMore((m) => [...m, ...res.items]);
      setCursor(res.page.next_cursor ?? null);
      setMoreError(null);
    } catch (err) {
      setMoreError(toFailure(err));
    }
  }
  return (
    <div className={styles.block}>
      <Title order={6}>Model-proposed candidates</Title>
      {items.length === 0 ? (
        <EmptyState title="Nothing proposed">
          <p>No model-proposed candidates exist for this file.</p>
        </EmptyState>
      ) : (
        <>
          <p className={styles.note}>
            Proposals checked by rules. Only items marked accepted passed every check; none is a source record.
          </p>
          <ul aria-label={`Model-proposed candidates for ${doc.original_filename}`} className={styles.list}>
            {items.map((c) => (
              <Candidate key={c.candidate_id} c={c} describeLocator={describeLocator} />
            ))}
          </ul>
        </>
      )}
      {next !== null && (
        <div>
          <Button variant="default" size="xs" onClick={() => void loadMore()}>
            Load more candidates
          </Button>
        </div>
      )}
      {moreError !== null && (
        <Callout tone="danger" role="alert">
          <p>More candidates could not be loaded: {moreError.message}</p>
        </Callout>
      )}
    </div>
  );
}
