import { useSyncExternalStore } from "react";

// The sidebar list and the project view are separate regions; a save in one asks the other to
// re-read. Only a counter is shared, never project data.
let version = 0;
const listeners = new Set<() => void>();

export function bumpProjectList(): void {
  version += 1;
  listeners.forEach((l) => l());
}

export function useProjectListVersion(): number {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => version,
  );
}
