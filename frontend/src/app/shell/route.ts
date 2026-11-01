import { useMemo, useSyncExternalStore } from "react";
import { SECTIONS, isProjectId, type Section } from "../../features/projects/keys";

/** Hash routes: `#/` (home) and `#/projects/<id>/<section>`. Works behind any static server. */
export type Route =
  | { kind: "home" }
  | { kind: "project"; projectId: string; section: Section }
  | { kind: "invalid"; raw: string };

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "");
  if (path === "" || path === "/") return { kind: "home" };
  const parts = path.split("/").filter((p) => p !== "");
  if (parts[0] !== "projects" || parts.length < 2 || parts.length > 3) return { kind: "home" };
  const id = parts[1] ?? "";
  if (!isProjectId(id)) return { kind: "invalid", raw: id };
  const section = SECTIONS.find((s) => s === parts[2]) ?? "sources";
  return { kind: "project", projectId: id, section };
}

export function routeHash(route: Route): string {
  if (route.kind !== "project") return "#/";
  return `#/projects/${route.projectId}/${route.section}`;
}

// A one-shot explanation shown on the home view after the app redirected there.
let noticeText: string | null = null;
const noticeListeners = new Set<() => void>();
const emitNotice = () => noticeListeners.forEach((l) => l());

export function setHomeNotice(text: string | null): void {
  noticeText = text;
  emitNotice();
}

export function useHomeNotice(): string | null {
  return useSyncExternalStore(
    (cb) => {
      noticeListeners.add(cb);
      return () => noticeListeners.delete(cb);
    },
    () => noticeText,
  );
}

function subscribe(cb: () => void): () => void {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return useMemo(() => parseRoute(hash), [hash]);
}

/** Navigate; `replace` avoids adding a history entry (used for redirects). */
export function navigate(route: Route, options: { replace?: boolean } = {}): void {
  const target = routeHash(route);
  if (window.location.hash === target || (target === "#/" && window.location.hash === "")) return;
  if (options.replace) {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${target}`);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    window.location.hash = target;
  }
}
