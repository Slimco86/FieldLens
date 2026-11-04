import { useSyncExternalStore } from "react";
import type { ExploreCommandBus } from "../scene/exploreCommands";

/**
 * Tiny publish/subscribe bridge between a mounted Explore workspace and the project-level assistant.
 * Explore publishes its live selection and its command bus while it is mounted; the assistant reads them and falls
 * back to project-only context / no bus otherwise. Only small values pass through here (no scene state).
 */
export interface ExploreLiveContext {
  projectId: string;
  wellboreId: string | null;
  selectedElementId: string | null;
  asOf: string | null;
  view: "3d" | "charts" | "split";
}

interface Snapshot {
  context: ExploreLiveContext | null;
  bus: ExploreCommandBus | null;
}

let snapshot: Snapshot = { context: null, bus: null };
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function publishExploreContext(context: ExploreLiveContext | null): void {
  snapshot = { ...snapshot, context };
  emit();
}
export function publishExploreBus(bus: ExploreCommandBus | null): void {
  snapshot = { ...snapshot, bus };
  emit();
}
export function getExploreBridge(): Snapshot {
  return snapshot;
}
export function subscribeExploreBridge(l: () => void): () => void {
  listeners.add(l);
  return () => void listeners.delete(l);
}
export function useExploreBridge(): Snapshot {
  return useSyncExternalStore(subscribeExploreBridge, getExploreBridge, getExploreBridge);
}
