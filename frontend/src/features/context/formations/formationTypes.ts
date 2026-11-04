import type { components } from "../../../api/generated";

type S = components["schemas"];
type Req<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

/*
 * The generated types mark list fields that have server defaults as optional. The API always sends them, but the
 * viewer never relies on that: `normalizeLayerSet` fills the defaults once, and every consumer sees these types.
 */
export type RawFormationLayerSet = S["FormationLayerSet"];
export type DepthValue = S["DepthValue"];
export type EvidenceLink = S["EvidenceLink"];
export type LevelPlane = S["LevelPlane"];
export type FormationConflict = S["FormationConflict"];
export type FormationBlocked = Req<S["FormationBlocked"], "pick_ids">;
export type FormationPick = Req<S["FormationPick"], "evidence">;
export type FormationUnsupportedPick = Req<S["FormationUnsupportedPick"], "evidence">;
export type FormationSurface = Omit<S["FormationSurface"], "picks" | "blocked" | "evidence"> & {
  picks: FormationPick[];
  blocked: FormationBlocked[];
  evidence: EvidenceLink[];
};
export type FormationLayerSet = Omit<RawFormationLayerSet, "surfaces" | "conflicts" | "unsupported" | "blocked"> & {
  surfaces: FormationSurface[];
  conflicts: FormationConflict[];
  unsupported: FormationUnsupportedPick[];
  blocked: FormationBlocked[];
};

export function normalizeLayerSet(raw: RawFormationLayerSet): FormationLayerSet {
  const blocked = (b: S["FormationBlocked"]): FormationBlocked => ({ ...b, pick_ids: b.pick_ids ?? [] });
  return {
    ...raw,
    surfaces: (raw.surfaces ?? []).map((s) => ({
      ...s,
      picks: (s.picks ?? []).map((p) => ({ ...p, evidence: p.evidence ?? [] })),
      blocked: (s.blocked ?? []).map(blocked),
      evidence: s.evidence ?? [],
    })),
    conflicts: raw.conflicts ?? [],
    unsupported: (raw.unsupported ?? []).map((u) => ({ ...u, evidence: u.evidence ?? [] })),
    blocked: (raw.blocked ?? []).map(blocked),
  };
}

export type Vec3 = readonly [number, number, number];

/** What the formation read model is requested for. */
export type FormationTarget = { kind: "wellbore"; wellboreId: string } | { kind: "field" };

/** Fixed on-screen wording (mirrors the backend contract constants). */
export const LEVEL_PLANE_LABEL = "level plane - illustrative";
export const LEVEL_PLANE_NOTE = "not an interpreted horizon";
