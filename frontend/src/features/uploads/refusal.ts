import type { components } from "../../api/generated";

export type ImportRefusal = components["schemas"]["ImportRefusal"];
export type RefusedFile = components["schemas"]["RefusedFile"];

/** A refusal as the UI uses it: validated, never trusted beyond the fields it checked. */
export interface ParsedRefusal {
  scope: "files" | "batch";
  reason: string | null;
  /** False when the server says so, or when some entries were unreadable and dropped. */
  complete: boolean;
  fileCount: number | null;
  limit: number | null;
  files: ParsedRefusedFile[];
}

export interface ParsedRefusedFile {
  filename: string;
  position: number;
  reason: string;
  message: string;
  statusCode: number | null;
  limit: number | null;
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Returns null for anything that is not a well-formed ImportRefusal, so callers fall back to the generic message. */
export function parseImportRefusal(details: unknown): ParsedRefusal | null {
  if (!isRecord(details)) return null;
  const scope = details["scope"];
  if (scope !== "files" && scope !== "batch") return null;
  const raw = details["refused_files"];
  if (!Array.isArray(raw)) return null;
  const files: ParsedRefusedFile[] = [];
  let dropped = 0;
  for (const item of raw as unknown[]) {
    if (!isRecord(item)) {
      dropped += 1;
      continue;
    }
    const filename = str(item["filename"]);
    const position = num(item["position"]);
    if (filename === null || position === null || !Number.isInteger(position) || position < 0) {
      dropped += 1;
      continue;
    }
    const reason = str(item["reason"]) ?? "refused";
    files.push({
      filename,
      position,
      reason,
      message: str(item["message"]) ?? reason,
      statusCode: num(item["status_code"]),
      limit: num(item["limit"]),
    });
  }
  return {
    scope,
    reason: str(details["reason"]),
    complete: details["refusals_complete"] === true && dropped === 0 && scope === "files",
    fileCount: num(details["file_count"]),
    limit: num(details["limit"]),
    files,
  };
}

export interface RefusalMatch {
  refusal: ParsedRefusedFile;
  /** True when the server position and the file name disagree and the name decided. */
  byNameOnly: boolean;
}

/**
 * Attribute refusals to local entries. A refusal matches when its position AND filename agree; the rest fall back to the
 * first still-unclaimed file of that name (flagged), otherwise stay unmatched. Returns per-index matches and leftovers.
 */
export function matchRefusals(
  names: readonly string[],
  refused: readonly ParsedRefusedFile[],
): { byIndex: Map<number, RefusalMatch>; unmatched: ParsedRefusedFile[] } {
  const byIndex = new Map<number, RefusalMatch>();
  const rest: ParsedRefusedFile[] = [];
  for (const r of refused) {
    if (names[r.position] === r.filename && !byIndex.has(r.position)) byIndex.set(r.position, { refusal: r, byNameOnly: false });
    else rest.push(r);
  }
  const unmatched: ParsedRefusedFile[] = [];
  for (const r of rest) {
    const index = names.findIndex((n, i) => n === r.filename && !byIndex.has(i));
    if (index === -1) unmatched.push(r);
    else byIndex.set(index, { refusal: r, byNameOnly: true });
  }
  return { byIndex, unmatched };
}
