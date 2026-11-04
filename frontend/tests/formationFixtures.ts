import type { DepthValue, FormationLayerSet, FormationPick, FormationSurface } from "../src/features/context/formations/formationTypes";

export const PROJECT = "00000000-0000-4000-8000-000000000001";
export const WB = "00000000-0000-4000-8000-0000000000a1";
export const DOC = "00000000-0000-4000-8000-0000000000d1";

export const depth = (reference: DepthValue["reference"], value: number | null, unit: string | null, extra: Partial<DepthValue> = {}): DepthValue => ({
  reference,
  value,
  unit,
  datum: null,
  datum_status: reference === "md" || reference === "scene_elevation" ? "not_applicable" : "unknown",
  original_text: null,
  unknown_reason: value === null ? "not stated" : null,
  ...extra,
});

const pdf = (page: number) => ({
  document_id: DOC,
  record_id: null,
  source_revision_id: null,
  locator: { kind: "pdf" as const, page, cell_id: null, rect: null, source_revision_id: "r1", table_id: null, document_id: DOC },
});

export function pick(id: string, name: string, over: Partial<FormationPick> = {}): FormationPick {
  return {
    pick_id: id,
    wellbore_id: WB,
    surface_key: name.toLowerCase(),
    surface_name: name,
    name,
    md: depth("md", 1500, "m"),
    tvd: depth("tvd", 1450, "m", { datum: "KB", datum_status: "stated" }),
    tvdss: depth("tvdss", 1400, "m", { datum: "MSL", datum_status: "stated" }),
    twt: null,
    scene_elevation: depth("scene_elevation", -1450, "m"),
    position_enu: [10, 20, -1450],
    qualifier: null,
    source_dip: null,
    source_azimuth: null,
    validation_state: "valid",
    tier: "T1",
    status: "observed",
    label: "pick - observed",
    evidence: [pdf(7)],
    extraction_method: "table row",
    ...over,
  };
}

export const footprint = { min_east: -100, max_east: 300, min_north: -50, max_north: 150, margin_m: 40 };

export function surface(key: string, name: string, over: Partial<FormationSurface> = {}): FormationSurface {
  return {
    surface_key: key,
    name,
    tier: "T2",
    tier_label: "T2 level plane - illustrative",
    status: "illustrative",
    scope: "wellbore",
    wellbore_ids: [WB],
    picks: [],
    plane: null,
    mesh: null,
    blocked: [],
    evidence: [],
    ...over,
  };
}

/** Rich set: a drawable plane, a datum-blocked plane, a T3 surface, a conflict, an unsupported pick, an unlocated pick and a layer-level block. */
export function richSet(): FormationLayerSet {
  const alpha = pick("00000000-0000-4000-8000-0000000000b1", "Alpha", { surface_key: "alpha" });
  const alpha2 = pick("00000000-0000-4000-8000-0000000000b2", "Alpha deep", { surface_key: "alpha", position_enu: [10, 20, -1500] });
  const bravo = pick("00000000-0000-4000-8000-0000000000b3", "Bravo", { surface_key: "bravo", tvd: depth("tvd", 900, "ft", { datum_status: "unknown", unknown_reason: "datum not stated" }), position_enu: [4, 6, -900] });
  const unlocated = pick("00000000-0000-4000-8000-0000000000b4", "Bravo unplaced", { surface_key: "bravo", position_enu: null });
  const conflicted = pick("00000000-0000-4000-8000-0000000000b5", "Delta", { surface_key: "delta", position_enu: [1, 1, -2000] });
  const gamma = pick("00000000-0000-4000-8000-0000000000b6", "Gamma", { surface_key: "gamma", position_enu: [2, 2, -1000], tier: "T3", status: "interpolated" });
  return {
    project_id: PROJECT,
    wellbore_id: WB,
    frame: { origin_enu: [0, 0, 0], horizontal_crs: null, length_unit: "m", vertical_reference: null, vertical_reference_status: "unknown", exaggeration_neutral: true, tvd_tolerance_m: 2 },
    surfaces: [
      surface("alpha", "Alpha", {
        picks: [alpha, alpha2],
        plane: { elevation: depth("scene_elevation", -1450, "m"), footprint, label: "level plane - illustrative", note: "not an interpreted horizon", status: "illustrative", source_pick_id: alpha.pick_id },
      }),
      surface("bravo", "Bravo", { picks: [bravo, unlocated], blocked: [{ reason: "unknown_datum", message: "TVD datum is not stated; no plane.", pick_ids: [bravo.pick_id] }] }),
      surface("delta", "Delta", { picks: [conflicted], blocked: [{ reason: "tvd_conflict", message: "Plane blocked for the conflicting pick.", pick_ids: [conflicted.pick_id] }] }),
      surface("gamma", "Gamma", { tier: "T3", tier_label: "T3 interpolated surface", status: "interpolated", picks: [gamma] }),
    ],
    conflicts: [{ pick_id: conflicted.pick_id, wellbore_id: WB, reason: "tvd_conflict", message: "Source TVD differs from the trajectory by 12 m.", source_depth: null, trajectory_depth: null, difference: 12, difference_unit: "m", tolerance: 2 }],
    unsupported: [{ pick_id: "00000000-0000-4000-8000-0000000000b7", wellbore_id: WB, surface_name: "Fault X", qualifier: "FP", reason: "unsupported_qualifier", message: "Fault pick is listed, not drawn.", evidence: [] }],
    blocked: [{ reason: "datum_mismatch", message: "Wellbores use different vertical references.", pick_ids: [] }],
    empty_reason: null,
    generated_from_revision: "rev-1",
  };
}

export const emptySet = (reason: string | null = "no formation picks in this project"): FormationLayerSet => ({
  project_id: PROJECT,
  wellbore_id: null,
  frame: { origin_enu: null, horizontal_crs: null, length_unit: "m", vertical_reference: null, vertical_reference_status: "unknown", exaggeration_neutral: true, tvd_tolerance_m: null },
  surfaces: [],
  conflicts: [],
  unsupported: [],
  blocked: [],
  empty_reason: reason,
  generated_from_revision: "rev-0",
});
