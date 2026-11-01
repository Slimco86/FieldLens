// Pure aggregation for the project Overview (UI-13). Every number is a count or copy of an API
// field; nothing here computes an engineering quantity (no totals of samples, no flow inference).
import type { components } from "../../api/generated";
import { describeLocator } from "../uploads/EvidencePanel";

type S = components["schemas"];

export type DocumentLite = {
  id: string;
  filename: string;
  format: string;
  storage: S["StorageState"];
  extraction: S["ExtractionState"];
};

export const lite = (d: S["SourceDocumentItem"]): DocumentLite => ({
  id: d.document_id,
  filename: d.original_filename,
  format: d.format_family,
  storage: d.storage_state,
  extraction: d.extraction_state,
});

export function countBy<T>(items: readonly T[], key: (item: T) => string): [string, number][] {
  const counts = new Map<string, number>();
  for (const item of items) counts.set(key(item), (counts.get(key(item)) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

/** Documents whose extraction can have produced a report worth reading. */
export const hasReport = (d: DocumentLite): boolean =>
  d.storage === "stored" && d.extraction !== "pending_extraction" && d.extraction !== "unsupported";

export interface IssueRow {
  issueId: string;
  severity: S["IssueSeverity"];
  code: S["IssueCode"];
  message: string;
  documentId: string;
  filename: string;
  locator: string | null;
}

export interface KindRow {
  kind: string;
  records: number;
  documents: number;
  complete: number;
  partial: number;
  unknown: number;
}

export interface ReportsSummary {
  /** Documents whose extraction report was requested / actually read. */
  eligible: number;
  read: number;
  failed: number;
  kinds: KindRow[];
  severity: Record<S["IssueSeverity"], number>;
  /** Every issue, worst first; the view shows only the first rows. */
  issues: IssueRow[];
  missingUnitIssues: number;
}

const SEVERITY_RANK: Record<S["IssueSeverity"], number> = { error: 0, warning: 1, info: 2 };

export function summarizeReports(
  docs: readonly DocumentLite[],
  reports: readonly { doc: DocumentLite; report: S["ExtractionReport"] | null }[],
): ReportsSummary {
  const kinds = new Map<string, KindRow>();
  const issues: IssueRow[] = [];
  const severity = { error: 0, warning: 0, info: 0 };
  let read = 0;
  for (const { doc, report } of reports) {
    if (report === null) continue;
    read += 1;
    for (const [kind, n] of Object.entries(report.record_counts ?? {})) {
      const row = kinds.get(kind) ?? { kind, records: 0, documents: 0, complete: 0, partial: 0, unknown: 0 };
      row.records += n;
      row.documents += 1;
      const status = report.coverage?.status ?? "unknown";
      row[status] += 1;
      kinds.set(kind, row);
    }
    for (const issue of report.issues ?? []) {
      severity[issue.severity] += 1;
      const link = issue.evidence_links?.[0];
      issues.push({
        issueId: `${doc.id}:${issue.issue_id}`,
        severity: issue.severity,
        code: issue.code,
        message: issue.message,
        documentId: doc.id,
        filename: doc.filename,
        locator: link === undefined ? null : describeLocator(link),
      });
    }
  }
  issues.sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
  const eligible = docs.filter(hasReport).length;
  return {
    eligible,
    read,
    failed: reports.filter((r) => r.report === null).length,
    kinds: [...kinds.values()].sort((a, b) => b.records - a.records || a.kind.localeCompare(b.kind)),
    severity,
    issues,
    missingUnitIssues: issues.filter((i) => i.code === "MISSING_UNIT").length,
  };
}

export interface SeriesRow {
  id: string;
  kind: S["SeriesKind"];
  measure: string;
  unit: string | null;
  unitStatus: S["SeriesUnitStatus"];
  indexName: string;
  indexUnit: string | null;
  indexUnitStatus: S["SeriesUnitStatus"];
  indexFirst: string;
  indexLast: string;
  min: number | null;
  max: number | null;
  valid: number;
  samples: number;
  filename: string | null;
}

export interface SeriesGroup {
  /** Label exactly as written in the source; null when the source gave none. */
  label: string | null;
  wellName: string | null;
  rows: SeriesRow[];
}

const indexText = (info: S["SeriesInfo"], which: "first" | "last"): string => {
  const date = which === "first" ? info.index.first_date : info.index.last_date;
  return date ?? String(info.index[which]);
};

/** Groups series by the wellbore label as written; no mapping to resolved wellbores is inferred. */
export function groupSeries(items: readonly S["SeriesInfo"][], filenames: ReadonlyMap<string, string>): SeriesGroup[] {
  const groups = new Map<string, SeriesGroup>();
  for (const s of items) {
    const key = `${s.wellbore_label ?? ""}\u0000${s.well_name ?? ""}`;
    const group = groups.get(key) ?? { label: s.wellbore_label, wellName: s.well_name, rows: [] };
    group.rows.push({
      id: s.series_id,
      kind: s.kind,
      measure: s.measure,
      unit: s.unit,
      unitStatus: s.unit_status,
      indexName: s.index.name,
      indexUnit: s.index.unit,
      indexUnitStatus: s.index.unit_status,
      indexFirst: indexText(s, "first"),
      indexLast: indexText(s, "last"),
      min: s.min_value,
      max: s.max_value,
      valid: s.valid_count,
      samples: s.sample_count,
      filename: filenames.get(s.document_id) ?? null,
    });
    groups.set(key, group);
  }
  return [...groups.values()]
    .map((g) => ({ ...g, rows: g.rows.sort((a, b) => a.kind.localeCompare(b.kind) || a.measure.localeCompare(b.measure)) }))
    .sort((a, b) => (a.label ?? "\uffff").localeCompare(b.label ?? "\uffff"));
}

/** Series whose value or index unit the source did not state (so none is assumed here). */
export const unitWarnings = (groups: readonly SeriesGroup[]): { group: SeriesGroup; row: SeriesRow; what: string }[] =>
  groups.flatMap((group) =>
    group.rows.flatMap((row) => {
      const out: { group: SeriesGroup; row: SeriesRow; what: string }[] = [];
      if (row.indexUnitStatus !== "stated")
        out.push({ group, row, what: `index “${row.indexName}” unit ${row.indexUnitStatus === "missing" ? "not stated" : "mixed"}` });
      if (row.unitStatus !== "stated")
        out.push({ group, row, what: `value unit ${row.unitStatus === "missing" ? "not stated" : "mixed"}` });
      return out;
    }),
  );
