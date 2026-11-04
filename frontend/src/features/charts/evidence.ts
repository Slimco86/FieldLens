import type { SourceRef } from "../scene/exploreCommands";
import type { ExploreCommandBus } from "../scene/exploreCommands";
import type { EvidenceLink } from "./api";

export type OpenSourceResult =
  /** A subscriber opened the source. */
  | "opened"
  /** Nobody listens for `openSource` (no evidence viewer is mounted in this view). */
  | "no-viewer"
  /** A viewer exists but could not locate the document/page. */
  | "not-found"
  /** The link has no document to open (for example a derivation). */
  | "no-document";

/** Maps an evidence link to the AppLink source locator; null when it points at no document. */
export function evidenceToSource(link: EvidenceLink): SourceRef | null {
  const loc = link.locator;
  const documentId = link.document_id ?? ("document_id" in loc ? loc.document_id : null);
  if (documentId === null) return null;
  switch (loc.kind) {
    case "pdf":
      return { documentId, page: loc.page, locator: loc.table_id ?? loc.cell_id ?? undefined };
    case "xlsx":
      return { documentId, locator: `${loc.sheet}!${loc.cell_range}` };
    case "text":
    case "converted_text":
      return { documentId, locator: `${loc.kind}` };
    default:
      return { documentId, locator: loc.kind };
  }
}

export function evidenceLabel(link: EvidenceLink): string {
  const s = evidenceToSource(link);
  if (s === null) return `${link.locator.kind} (no document)`;
  return s.page !== undefined ? `document ${s.documentId.slice(0, 8)}, page ${s.page}` : `document ${s.documentId.slice(0, 8)}${s.locator ? `, ${s.locator}` : ""}`;
}

/** Opens the original evidence through the command bus; every outcome is reported, none is swallowed. */
export function openEvidence(bus: Pick<ExploreCommandBus, "dispatch"> | null, link: EvidenceLink): OpenSourceResult {
  const source = evidenceToSource(link);
  if (source === null) return "no-document";
  if (bus === null) return "no-viewer";
  const outcome = bus.dispatch({ type: "openSource", source });
  if (outcome === "handled") return "opened";
  if (outcome === "unhandled") return "not-found";
  return "no-viewer"; // no-subscriber (and the camera-only not-implemented, which cannot occur here)
}

export const OPEN_RESULT_MESSAGE: Record<OpenSourceResult, string> = {
  opened: "Source opened.",
  "no-viewer": "The source viewer is not available in this view, so the evidence could not be opened.",
  "not-found": "The source viewer could not find that document or page.",
  "no-document": "This evidence has no document to open.",
};
