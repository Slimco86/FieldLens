const ORDER = ["sheet", "page", "table", "row", "cell", "column", "curve"] as const;

const present = (v: unknown): v is string | number => (typeof v === "string" && v !== "") || typeof v === "number";

/**
 * Short source locator in words a reader can follow in the file: page, table, sheet, row, cell, line(s).
 * Ids, kinds and other keys are never shown and nothing is interpreted. `line_start`/`line_end` become
 * "line 26" or "lines 26-30", never raw key names.
 */
export function locatorText(loc: Record<string, unknown> | undefined): string {
  if (loc === undefined) return "no locator";
  const parts: string[] = [];
  for (const k of ORDER) {
    const v = loc[k];
    if (present(v)) parts.push(`${k} ${String(v)}`);
  }
  const { line, line_start: from, line_end: to } = loc;
  if (present(line)) parts.push(`line ${String(line)}`);
  else if (present(from) && present(to) && String(from) !== String(to)) parts.push(`lines ${String(from)}-${String(to)}`);
  else if (present(from) || present(to)) parts.push(`line ${String(present(from) ? from : to)}`);
  return parts.length === 0 ? "no locator" : parts.join(", ").slice(0, 160);
}
