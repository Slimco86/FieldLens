import { useEffect, useMemo, useState } from "react";
import { ApiError, getJson } from "../../../api/client";
import { normalizeLayerSet, type FormationLayerSet, type FormationTarget, type RawFormationLayerSet } from "./formationTypes";

export const formationsPath = (projectId: string, target: FormationTarget): string =>
  target.kind === "wellbore"
    ? `/api/v1/projects/${encodeURIComponent(projectId)}/wellbores/${encodeURIComponent(target.wellboreId)}/formations`
    : `/api/v1/projects/${encodeURIComponent(projectId)}/formations`;

export const getFormations = async (projectId: string, target: FormationTarget, signal: AbortSignal): Promise<FormationLayerSet> =>
  normalizeLayerSet(await getJson<RawFormationLayerSet>(formationsPath(projectId, target), signal));

export type FormationLayersState =
  | { status: "idle" | "loading"; data: null; error: null; revision: null }
  | { status: "error"; data: null; error: string; revision: null }
  /** The read model answered but holds nothing at all to show or explain. */
  | { status: "empty"; data: FormationLayerSet; error: null; revision: string }
  | { status: "ready"; data: FormationLayerSet; error: null; revision: string };

export const isEmptySet = (d: FormationLayerSet): boolean =>
  d.surfaces.length === 0 && d.unsupported.length === 0 && d.conflicts.length === 0 && d.blocked.length === 0;

export function describeError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 404) return "The wellbore or project was not found, so no formation data is available.";
    return `Formation data could not be loaded (${e.message}).`;
  }
  return `Formation data could not be loaded${e instanceof Error ? ` (${e.message})` : ""}.`;
}

type Settled = { key: string } & ({ ok: true; data: FormationLayerSet } | { ok: false; error: string });

/**
 * Formation read model for one project and one wellbore (or the whole field). Project-scoped (the project id is part of
 * the key and of the URL), keyed by `revisionKey` (pass the model/trajectory revision so a changed input refetches), with
 * explicit loading/error/empty states. A response for a superseded key is never shown. The data is held as the single
 * response object; the viewer reads typed buffers derived from it, not React state arrays.
 */
export function useFormationLayers(projectId: string | null, target: FormationTarget, revisionKey: string | number | null = null): FormationLayersState {
  const wellboreId = target.kind === "wellbore" ? target.wellboreId : null;
  const key = projectId === null ? null : `${projectId}|${target.kind}|${wellboreId ?? ""}|${revisionKey ?? ""}`;
  const [settled, setSettled] = useState<Settled | null>(null);

  useEffect(() => {
    if (key === null || projectId === null) return;
    const ctl = new AbortController();
    const t: FormationTarget = wellboreId === null ? { kind: "field" } : { kind: "wellbore", wellboreId };
    getFormations(projectId, t, ctl.signal).then(
      (data) => {
        if (!ctl.signal.aborted) setSettled({ key, ok: true, data });
      },
      (e: unknown) => {
        if (!ctl.signal.aborted) setSettled({ key, ok: false, error: describeError(e) });
      },
    );
    return () => ctl.abort();
  }, [key, projectId, wellboreId]);

  return useMemo<FormationLayersState>(() => {
    if (key === null) return { status: "idle", data: null, error: null, revision: null };
    if (settled === null || settled.key !== key) return { status: "loading", data: null, error: null, revision: null };
    if (!settled.ok) return { status: "error", data: null, error: settled.error, revision: null };
    const revision = settled.data.generated_from_revision;
    return isEmptySet(settled.data) ? { status: "empty", data: settled.data, error: null, revision } : { status: "ready", data: settled.data, error: null, revision };
  }, [key, settled]);
}
