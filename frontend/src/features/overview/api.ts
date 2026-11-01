import { getJson } from "../../api/client";
import type { components } from "../../api/generated";
import { getExtraction, listDocuments } from "../uploads/api";
import { hasReport, lite, summarizeReports, type DocumentLite, type ReportsSummary } from "./model";

type S = components["schemas"];

/** Bounds keep the Overview cheap: beyond them it says so instead of silently under-counting. */
export const MAX_DOCUMENT_PAGES = 10; // 500 documents
export const MAX_REPORTS = 100;
export const REPORT_CONCURRENCY = 4;
export const SERIES_PAGE = 500;
export const MAX_SERIES_PAGES = 4; // 2000 series

const base = (projectId: string) => `/api/v1/projects/${projectId}`;

export interface DocumentsResult {
  docs: DocumentLite[];
  truncated: boolean;
}

export async function loadAllDocuments(projectId: string, revisionId: string, signal: AbortSignal): Promise<DocumentsResult> {
  const docs: DocumentLite[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < MAX_DOCUMENT_PAGES; page += 1) {
    const res = await listDocuments(projectId, revisionId, signal, cursor);
    for (const d of res.items) {
      if (d.source_revision_id !== revisionId || d.project_id !== projectId) continue; // wrong context: never counted
      docs.push(lite(d));
    }
    if (res.page.next_cursor === null) return { docs, truncated: false };
    cursor = res.page.next_cursor;
  }
  return { docs, truncated: true };
}

export function getIdentity(projectId: string, signal: AbortSignal): Promise<S["IdentityListing"]> {
  return getJson<S["IdentityListing"]>(`${base(projectId)}/identity`, signal);
}

export interface SeriesResult {
  items: S["SeriesInfo"][];
  total: number;
}

export async function loadSeries(projectId: string, signal: AbortSignal): Promise<SeriesResult> {
  const items: S["SeriesInfo"][] = [];
  let offset = 0;
  let total = 0;
  for (let page = 0; page < MAX_SERIES_PAGES; page += 1) {
    const res = await getJson<S["SeriesList"]>(
      `${base(projectId)}/series?limit=${SERIES_PAGE}&offset=${offset}`,
      signal,
    );
    total = res.total;
    items.push(...res.items.filter((s) => s.project_id === projectId));
    if (res.next_offset === null) break;
    offset = res.next_offset;
  }
  return { items, total };
}

export interface ReportsResult extends ReportsSummary {
  capped: boolean;
}

/** Reads per-document extraction reports with bounded concurrency; one failure never hides the rest. */
export async function loadReports(
  projectId: string,
  docs: readonly DocumentLite[],
  signal: AbortSignal,
): Promise<ReportsResult> {
  const eligible = docs.filter(hasReport);
  const targets = eligible.slice(0, MAX_REPORTS);
  const out: { doc: DocumentLite; report: S["ExtractionReport"] | null }[] = new Array(targets.length);
  let next = 0;
  const worker = async () => {
    while (next < targets.length) {
      const i = next++;
      const doc = targets[i] as DocumentLite;
      try {
        const report = await getExtraction(projectId, doc.id, signal);
        out[i] = { doc, report: report.project_id === projectId ? report : null };
      } catch (err) {
        if (signal.aborted) throw err;
        out[i] = { doc, report: null };
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(REPORT_CONCURRENCY, targets.length) }, worker));
  return { ...summarizeReports(docs, out), capped: eligible.length > targets.length };
}
