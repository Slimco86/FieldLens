import { useState } from "react";
import {
  listCandidates,
  type EvidenceLink,
  type ExtractionCandidate,
  type ExtractionCandidatePage,
  type SourceDocumentItem,
} from "./api";
import { usePolled } from "./usePolled";
import { toFailure, type Failure } from "../projects/scope";

/** State is conveyed by a symbol and words, never by color alone (AX-7). */
const STATE: Record<ExtractionCandidate["state"], { mark: string; text: string }> = {
  accepted: { mark: "✔", text: "Accepted by validators" },
  flagged: { mark: "⚑", text: "Flagged (needs attention)" },
  rejected: { mark: "✖", text: "Rejected" },
  candidate: { mark: "○", text: "Unresolved candidate (not an accepted fact)" },
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
  const s = STATE[c.state];
  const failed = c.validator_results.filter((v) => v.outcome === "failed" || v.outcome === "flagged");
  return (
    <li data-state={c.state}>
      <strong>
        <span aria-hidden="true">{s.mark} </span>
        {s.text}
      </strong>{" "}
      <em>[{c.label}]</em>
      <div>{valueText(c)}</div>
      <small>
        source: <code>{describeLocator(c.evidence) || describe(c.evidence)}</code>
        {c.quote !== null && c.quote !== undefined && <> quote: &ldquo;{c.quote}&rdquo;</>}
      </small>
      {c.reason_codes.length > 0 && (
        <small>
          {" "}
          reason: {c.reason_codes.map((r) => REASON[r] ?? r).join("; ")}
        </small>
      )}
      {failed.length > 0 && (
        <small> validators: {failed.map((v) => `${v.validator} ${v.outcome}`).join(", ")}</small>
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
  const { state } = usePolled<ExtractionCandidatePage>(
    `candidates/${projectId}/${doc.document_id}`,
    (signal) => listCandidates(projectId, doc.document_id, signal),
    () => false,
  );
  const [more, setMore] = useState<ExtractionCandidate[]>([]);
  const [cursor, setCursor] = useState<string | null | undefined>(undefined);
  const [moreError, setMoreError] = useState<Failure | null>(null);

  if (state.kind === "loading") return <p role="status">Loading model-proposed candidates…</p>;
  if (state.kind === "error") {
    return <p role="alert">Model-proposed candidates could not be loaded: {state.error.message}</p>;
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
    <div>
      <h6>Model-proposed candidates</h6>
      {items.length === 0 ? (
        <p>No model-proposed candidates exist for this file.</p>
      ) : (
        <>
          <p>Proposals checked by rules. Only items marked accepted passed every check; none is a source record.</p>
          <ul aria-label={`Model-proposed candidates for ${doc.original_filename}`}>
            {items.map((c) => (
              <Candidate key={c.candidate_id} c={c} describeLocator={describeLocator} />
            ))}
          </ul>
        </>
      )}
      {next !== null && (
        <button type="button" onClick={() => void loadMore()}>
          Load more candidates
        </button>
      )}
      {moreError !== null && <p role="alert">More candidates could not be loaded: {moreError.message}</p>}
    </div>
  );
}
