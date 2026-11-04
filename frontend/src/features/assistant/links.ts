import type { ExploreCommand, ExploreCommandBus, SourceRef } from "../scene/exploreCommands";
import type { AppLink, Citation } from "./api";

type Evidence = NonNullable<Citation["evidence"]>;
type Locator = Evidence["locator"];

export type LinkResult = { ok: true; message: string } | { ok: false; message: string };

function locatorText(loc: Locator): string | undefined {
  const rec = loc as unknown as Record<string, unknown>;
  const pick = (k: string) => (typeof rec[k] === "string" ? (rec[k] as string) : undefined);
  return pick("cell_id") ?? pick("sheet") ?? pick("xpath") ?? pick("column_name") ?? loc.kind;
}

export function sourceRefFromLocator(loc: Locator, page?: number | null): SourceRef {
  const rec = loc as unknown as Record<string, unknown>;
  const locPage = typeof rec.page === "number" ? rec.page : undefined;
  const ref: SourceRef = { documentId: typeof rec.document_id === "string" ? rec.document_id : "" };
  const p = page ?? locPage;
  if (p !== undefined) ref.page = p;
  const text = locatorText(loc);
  if (text !== undefined) ref.locator = text;
  return ref;
}

/** Maps a validated AppLink to an ExploreCommand; null when the target lacks a required id (stale). */
export function appLinkToCommand(link: AppLink): ExploreCommand | null {
  const t = link.target;
  switch (t.kind) {
    case "source": {
      const ref: SourceRef = t.locator !== null ? sourceRefFromLocator(t.locator, t.page) : { documentId: t.document_id };
      if (ref.documentId === "") ref.documentId = t.document_id;
      if (t.locator === null && t.page !== null) ref.page = t.page;
      return { type: "openSource", source: ref };
    }
    case "element":
      return t.wellbore_id === null ? null : { type: "focusElement", wellboreId: t.wellbore_id, elementId: t.element_id };
    case "wellbore":
      return { type: "focusWellbore", wellboreId: t.wellbore_id };
    case "formation":
      return t.wellbore_id === null
        ? null
        : { type: "focusFormation", wellboreId: t.wellbore_id, formationId: t.pick_id ?? t.surface_key };
    case "chart":
      return { type: "openChart", kind: t.chart_key, wellboreId: t.wellbore_id };
  }
}

export function citationToCommand(c: Citation): ExploreCommand | null {
  const ev = c.evidence;
  if (ev === null) return null;
  const ref = sourceRefFromLocator(ev.locator);
  if (ref.documentId === "" && ev.document_id !== null) ref.documentId = ev.document_id;
  return ref.documentId === "" ? null : { type: "openSource", source: ref };
}

/** Dispatches on the bus and turns every non-handled outcome into an explicit message (AV-4). */
export function dispatchCommand(bus: ExploreCommandBus | null, command: ExploreCommand | null): LinkResult {
  if (command === null) return { ok: false, message: "This link points to a target that is missing or no longer available." };
  if (bus === null) return { ok: false, message: "Nothing in this view can open that link (no Explore workspace)." };
  switch (bus.dispatch(command)) {
    case "handled":
      return { ok: true, message: "Opened." };
    case "no-subscriber":
      return { ok: false, message: "Nothing is listening for this link here; open the Explore view and try again." };
    case "unhandled":
      return { ok: false, message: "The target could not be found: it may be stale, hidden or not loaded." };
    case "queued":
      return { ok: false, message: "Nothing is listening for this link yet; it will run when the view is ready." };
  }
}

export const dispatchAppLink = (bus: ExploreCommandBus | null, link: AppLink): LinkResult =>
  dispatchCommand(bus, appLinkToCommand(link));
