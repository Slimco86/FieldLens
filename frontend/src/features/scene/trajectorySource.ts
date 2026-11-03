import { ApiError } from "../../api/client";
import { getTrajectory, type WellboreTrajectory } from "./api";
import { tieInInput, type TrajectoryInput } from "./trajectory";

declare global {
  interface Window {
    /** Test-only override: wellbore id -> stations. When set for an id the survey API is not called. */
    __FIELDLENS_TEST_TRAJECTORY__?: Record<string, TrajectoryInput>;
  }
}

/** What the info panel shows about the drawn survey (all text comes from the backend, nothing is inferred). */
export interface SurveyInfo {
  /** "Survey: <document>, as-built, MD x-y m". */
  label: string;
  /** The survey file, for a link that opens it (at `page` when it is a PDF); null when unknown. */
  source: { documentId: string; filename: string; page: number | null; format: string | null } | null;
  /** "Surface location: E … m, N … m (CRS: …)" or null when no validated location exists. */
  surfaceText: string | null;
  references: string;
  counts: string;
  others: readonly string[];
  warnings: readonly string[];
}

export type TrajectoryState =
  | { kind: "loading" }
  | { kind: "ready"; input: TrajectoryInput; info: SurveyInfo }
  | { kind: "none"; reason: string }
  | { kind: "error"; reason: string };

const STATUS_TEXT: Record<string, string> = {
  as_built: "as-built",
  planned: "planned",
  unstated: "status not stated",
  conflicting: "status conflicting",
  not_applicable: "status not stated",
};

const REASON_TEXT: Record<string, string> = {
  TRAJECTORY_PLANNED_ONLY: "only a planned survey exists",
  TRAJECTORY_INVALID_STATIONS: "survey stations are invalid or conflicting",
  TRAJECTORY_MD_NOT_MONOTONIC: "measured depth does not increase",
  TRAJECTORY_TOO_FEW_STATIONS: "too few survey stations",
  TRAJECTORY_STATUS_CONFLICTING: "survey status is conflicting",
  TRAJECTORY_BLOCKING_ISSUE: "an extraction error blocks the geometry",
  AZIMUTH_REFERENCE_NOT_STATED: "the azimuth reference is not stated",
  WELLHEAD_START_UNKNOWN: "the first station is not at the wellhead and states no TVD",
};

const num = (v: number) => (Math.round(v * 10) / 10).toString();

/** The survey set carries no format family: only a `.pdf` file name is treated as a PDF (the viewer offers nothing otherwise). */
const pdfFormat = (filename: string): string | null => (/\.pdf$/i.test(filename) ? "pdf" : "other");

export function surfaceText(t: WellboreTrajectory): string | null {
  const s = t.surface_location;
  if (s === null) return null;
  const crs = s.crs !== null ? `CRS: ${s.crs}` : "CRS not stated";
  const datum = s.geodetic_datum !== null ? `, datum: ${s.geodetic_datum}` : "";
  if (s.easting !== null && s.northing !== null) {
    const u = s.unit !== null ? ` ${s.unit}` : "";
    return `Surface location: E ${s.easting}${u}, N ${s.northing}${u} (${crs}${datum})`;
  }
  if (s.latitude !== null && s.longitude !== null) return `Surface location: lat ${s.latitude}°, lon ${s.longitude}° (${crs}${datum})`;
  return null;
}

/** Stations and provenance for `WellPath` plus the info panel text. */
export function toTrajectoryState(t: WellboreTrajectory): TrajectoryState {
  const set = t.survey_set;
  const label = `Survey: ${set.filename}, ${STATUS_TEXT[t.survey_status] ?? t.survey_status}, MD ${num(t.md_min_m)}-${num(t.md_max_m)} m`;
  const refs = [
    t.md_reference !== null ? `MD reference: ${t.md_reference}` : "MD reference not stated",
    t.tvd_reference !== null ? `TVD reference: ${t.tvd_reference}` : null,
    `azimuth reference: ${t.azimuth_reference ?? "not stated"}`,
    `offsets relative to ${t.north_reference} north`,
  ].filter((x): x is string => x !== null);
  return {
    kind: "ready",
    input: {
      source: label,
      stations: t.points.map((p) => ({ md_m: p.md_m, tvd_m: p.tvd_m, east_m: p.east_m, north_m: p.north_m })),
      // Derived, display-only tie-in (null when none was derived); never a survey station.
      tieIn: tieInInput(t.tie_in),
    },
    info: {
      label,
      source: { documentId: set.document_id, filename: set.filename, page: set.page, format: pdfFormat(set.filename) },
      surfaceText: surfaceText(t),
      references: refs.join("; "),
      counts: `${t.displayed_count} of ${t.source_count} stations displayed (display downsample only; calculations use all stations)`,
      others: t.other_sets.map((o) => `${o.filename} (${STATUS_TEXT[o.survey_status] ?? o.survey_status}): ${o.reasons.map((r) => REASON_TEXT[r.code] ?? r.message).join("; ") || "not used"}`),
      warnings: t.warnings.map((w) => w.message),
    },
  };
}

function noSurveyReason(e: ApiError): string {
  const raw = e.details?.["sets"];
  const sets = Array.isArray(raw) ? (raw as { reasons?: unknown }[]) : [];
  const codes = new Set<string>();
  for (const s of sets) if (Array.isArray(s.reasons)) for (const r of s.reasons) if (typeof r === "string") codes.add(r);
  const text = [...codes].map((c) => REASON_TEXT[c] ?? c);
  return text.length > 0 ? `no valid survey: ${text.join("; ")}` : "no survey records for this wellbore";
}

/** Fetches one wellbore's survey. A 404 is an answer ("none" with the reason), anything else a failure. */
export async function loadTrajectory(projectId: string, wellboreId: string, signal: AbortSignal): Promise<TrajectoryState> {
  const injected = typeof window === "undefined" ? undefined : window.__FIELDLENS_TEST_TRAJECTORY__?.[wellboreId];
  if (injected !== undefined) {
    return { kind: "ready", input: injected, info: { label: injected.source, source: null, surfaceText: null, references: "test fixture", counts: "", others: [], warnings: [] } };
  }
  try {
    return toTrajectoryState(await getTrajectory(projectId, wellboreId, signal));
  } catch (e) {
    if (signal.aborted) throw e;
    if (e instanceof ApiError && e.status === 404) {
      return e.details?.["code"] === "no_trajectory" ? { kind: "none", reason: noSurveyReason(e) } : { kind: "none", reason: "the wellbore was not found" };
    }
    return { kind: "error", reason: `the survey could not be loaded${e instanceof Error ? ` (${e.message})` : ""}` };
  }
}

/** Why a wellbore is drawn as the labelled vertical placeholder ("" when a survey is drawn). */
export function placeholderReason(state: TrajectoryState | undefined): string {
  if (state === undefined || state.kind === "loading") return "survey is loading";
  if (state.kind === "ready") return "";
  return state.reason;
}

/** The stations to draw, or null (placeholder). */
export function inputOf(state: TrajectoryState | undefined): TrajectoryInput | null {
  return state?.kind === "ready" ? state.input : null;
}
