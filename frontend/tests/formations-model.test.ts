import { describe, expect, it, vi } from "vitest";
import {
  buildFormationScene,
  datumText,
  enuToRender,
  evidenceToSourceRef,
  formatDepth,
  formationFocusTarget,
  inspectorModel,
  markerRadius,
  MAX_LABELS,
  MAX_PLANES,
  openFormationSource,
  pickLabels,
  planeId,
  planeOpacity,
  requestFocusFormation,
  resolveFormationId,
} from "../src/features/context/formations/formationModel";
import { createFormationStore, isSurfaceShown } from "../src/features/context/formations/formationStore";
import { normalizeLayerSet, type FormationLayerSet, type RawFormationLayerSet } from "../src/features/context/formations/formationTypes";
import { createExploreCommandBus } from "../src/features/scene/exploreCommands";
import { depth, DOC, emptySet, footprint, pick, richSet, surface, WB } from "./formationFixtures";

const ORIGIN = [0, 0, 0] as const;
const B1 = "00000000-0000-4000-8000-0000000000b1";
const B3 = "00000000-0000-4000-8000-0000000000b3";
const B4 = "00000000-0000-4000-8000-0000000000b4";
const B5 = "00000000-0000-4000-8000-0000000000b5";

describe("coordinates and display helpers", () => {
  it("maps ENU to render axes around the viewer origin (x east, y up, z -north)", () => {
    expect(enuToRender([10, 20, -1450], [0, 0, 0], ORIGIN)).toEqual([10, -1450, -20]);
    expect(enuToRender([10, 20, -1450], null, [5, -3, 2])).toEqual([15, -1453, -18]);
  });

  it("removes a large frame origin in double precision before the float32 conversion", () => {
    const big = 6_500_000.25;
    const p = enuToRender([big + 3.5, big + 1.5, 100.5], [big, big, 0], ORIGIN);
    expect(p).toEqual([3.5, 100.5, -1.5]);
  });

  it("scales marker size with exaggeration, bounded, while planes use their own opacity rule", () => {
    expect(markerRadius(null)).toBe(2.5);
    expect(markerRadius(0.2)).toBe(2.5);
    expect(markerRadius(4)).toBe(10);
    expect(markerRadius(1000)).toBe(40);
    expect(planeOpacity(0.3, false)).toBe(0.3);
    expect(planeOpacity(0.3, true)).toBe(0.1);
    expect(planeOpacity(5, false)).toBe(0.6);
    expect(planeOpacity(0, false)).toBe(0.05);
  });

  it("formats depths with unit, reference and datum status, never assuming a datum", () => {
    expect(formatDepth(depth("md", 1500, "m"), "md")).toBe("MD 1500 m (along bore)");
    expect(formatDepth(depth("tvd", 1450.123, "m", { datum: "KB", datum_status: "stated" }), "tvd")).toBe("TVD 1450.12 m (datum KB)");
    expect(formatDepth(depth("tvd", 900, "ft"), "tvd")).toBe("TVD 900 ft (datum unknown, not assumed)");
    expect(formatDepth(depth("tvdss", null, null), "tvdss")).toBe("TVDSS unknown - not stated");
    expect(formatDepth(null, "tvdss")).toBe("TVDSS not stated");
    expect(datumText(depth("scene_elevation", -5, "m"))).toBe("scene frame, from trajectory");
  });
});

describe("buildFormationScene", () => {
  const scene = buildFormationScene(richSet(), { origin: ORIGIN });

  it("draws placed, validated picks as markers and nothing for conflicts, unplaced or unsupported picks", () => {
    expect(scene.markers.map((m) => m.name).sort()).toEqual(["Alpha", "Alpha deep", "Bravo", "Gamma"]);
    const a = scene.markers.find((m) => m.id === B1);
    expect(a?.position).toEqual([10, -1450, -20]);
    expect(a?.label).toBe("Alpha (pick - observed)");
    expect(scene.markers.some((m) => m.id === B5 || m.id === B4)).toBe(false);
  });

  it("draws only the unblocked T2 level plane, bounded to its footprint, with the illustrative label", () => {
    expect(scene.planes).toHaveLength(1);
    const p = scene.planes[0]!;
    expect(p.center).toEqual([100, -1450, -50]);
    expect([p.width, p.depth]).toEqual([400, 200]);
    expect(p.label).toBe("Alpha: level plane - illustrative");
    expect(p.note).toBe("not an interpreted horizon");
    expect(p.statusText).toBe("status: illustrative");
    expect(p.sourceText).toContain('pick "Alpha"');
  });

  it("lists every block, conflict and unsupported item with its reason", () => {
    const by = (kind: string) => scene.notDrawn.filter((n) => n.kind === kind);
    expect(by("conflict").map((n) => n.reason)).toEqual(["tvd_conflict"]);
    expect(by("unsupported")[0]?.message).toContain("qualifier FP");
    expect(by("unlocated").map((n) => n.id)).toEqual([`pick:${B4}`]);
    expect(by("tier")[0]?.reason).toBe("tier_not_rendered");
    expect(scene.notDrawn.some((n) => n.reason === "datum_mismatch" && n.name === "Formation layer")).toBe(true);
    expect(scene.notDrawn.some((n) => n.reason === "unknown_datum" && n.name === "Bravo")).toBe(true);
    // The conflicting pick is listed once from the conflict list, not again as a generic block.
    expect(scene.notDrawn.filter((n) => n.name === "Delta" && n.kind === "conflict")).toHaveLength(1);
  });

  it("builds a legend with tier, status, shape and reasons so colour is never the only cue", () => {
    expect(scene.legend.map((l) => l.name)).toEqual(["Alpha", "Bravo", "Delta", "Gamma"]);
    const alpha = scene.legend[0]!;
    expect(alpha).toMatchObject({ tierLabel: "T2 level plane - illustrative", status: "illustrative", planeDrawn: true, markerCount: 2 });
    expect(new Set(scene.legend.map((l) => l.shape)).size).toBe(4);
    expect(scene.legend[1]!.planeBlocked[0]).toContain("unknown_datum");
    expect(scene.legend[3]!.planeBlocked[0]).toContain("tier_not_rendered");
    expect(scene.legend[2]!.markerCount).toBe(0);
  });

  it("keeps the style slot independent of response order", () => {
    const set = richSet();
    const reversed: FormationLayerSet = { ...set, surfaces: [...set.surfaces].reverse() };
    const a = buildFormationScene(set, { origin: ORIGIN }).legend.find((l) => l.name === "Alpha");
    const b = buildFormationScene(reversed, { origin: ORIGIN }).legend.find((l) => l.name === "Alpha");
    expect(b?.styleIndex).toBe(a?.styleIndex);
    expect(b?.color).toBe(a?.color);
  });

  it("applies the viewer origin to markers and planes", () => {
    const s = buildFormationScene(richSet(), { origin: [5, -3, 2] });
    expect(s.markers.find((m) => m.id === B1)?.position).toEqual([15, -1453, -18]);
    expect(s.planes[0]?.center).toEqual([105, -1453, -48]);
  });

  it("orders planes deepest first for stable translucency and caps them", () => {
    const mk = (key: string, up: number) => surface(key, key, { plane: { elevation: depth("scene_elevation", up, "m"), footprint, label: "level plane - illustrative", note: "n", status: "illustrative", source_pick_id: null } });
    const set = { ...emptySet(), surfaces: [mk("a", -100), mk("b", -900), mk("c", -500)] };
    expect(buildFormationScene(set, { origin: ORIGIN }).planes.map((p) => p.surfaceKey)).toEqual(["b", "c", "a"]);
    const many = { ...emptySet(), surfaces: Array.from({ length: MAX_PLANES + 3 }, (_, i) => mk(`s${String(i).padStart(3, "0")}`, -i)) };
    const capped = buildFormationScene(many, { origin: ORIGIN });
    expect(capped.planes).toHaveLength(MAX_PLANES);
    expect(capped.notDrawn.filter((n) => n.kind === "limit")).toHaveLength(3);
  });

  it("refuses planes without a metre elevation instead of guessing a unit", () => {
    const s = surface("ft", "Feet", { plane: { elevation: depth("scene_elevation", -100, "ft"), footprint, label: "level plane - illustrative", note: "n", status: "illustrative", source_pick_id: null } });
    const out = buildFormationScene({ ...emptySet(), surfaces: [s] }, { origin: ORIGIN });
    expect(out.planes).toHaveLength(0);
    expect(out.notDrawn[0]?.reason).toBe("plane_unit");
  });

  it("states empty, and unavailable-only scopes", () => {
    expect(buildFormationScene(emptySet(), { origin: ORIGIN }).emptyText).toBe("no formation picks in this project");
    expect(buildFormationScene(emptySet(null), { origin: ORIGIN }).emptyText).toBe("No formation picks for this scope");
    const blockedOnly = { ...emptySet(), blocked: [{ reason: "datum_mismatch" as const, message: "differs", pick_ids: [] }] };
    expect(buildFormationScene(blockedOnly, { origin: ORIGIN }).emptyText).toMatch(/see the reasons/);
    expect(buildFormationScene(null, { origin: ORIGIN })).toMatchObject({ markers: [], planes: [], emptyText: null });
  });

  it("does not draw invalid, unsupported or conflicting validation states", () => {
    const p = pick("p1", "Bad", { validation_state: "invalid" });
    const out = buildFormationScene({ ...emptySet(), surfaces: [surface("bad", "Bad", { tier: "T1", tier_label: "T1 pick marker", status: "observed", picks: [p] })] }, { origin: ORIGIN });
    expect(out.markers).toHaveLength(0);
    expect(out.notDrawn[0]).toMatchObject({ reason: "not_validated" });
  });
});

describe("inspector model", () => {
  const set = richSet();
  it("shows MD/TVD/TVDSS with original units and datum, qualifier, tier, evidence and extraction method", () => {
    const m = inspectorModel(set, B1)!;
    const row = (l: string) => m.rows.find((r) => r.label === l)?.value;
    expect(row("MD")).toBe("MD 1500 m (along bore)");
    expect(row("TVD")).toBe("TVD 1450 m (datum KB)");
    expect(row("TVDSS")).toBe("TVDSS 1400 m (datum MSL)");
    expect(row("Qualifier")).toBe("none");
    expect(row("Extraction method")).toBe("table row");
    expect(m.tierLabel).toBe("T1 pick marker");
    expect(m.statusText).toBe("pick - observed");
    expect(m.evidence).toHaveLength(1);
    expect(m.wellboreId).toBe(WB);
  });

  it("keeps an unknown datum visible and never converts the unit", () => {
    expect(inspectorModel(set, B3)!.rows.find((r) => r.label === "TVD")?.value).toBe("TVD 900 ft (datum unknown, not assumed)");
  });

  it("describes the plane as illustrative, level and not exaggerated", () => {
    const m = inspectorModel(set, planeId("alpha"))!;
    expect(m.kind).toBe("plane");
    expect(m.tierLabel).toBe("T2 level plane - illustrative");
    expect(m.statusText).toContain("level plane - illustrative");
    expect(m.notes).toContain("not an interpreted horizon");
    expect(m.notes.join(" ")).toContain("not vertically exaggerated");
    expect(m.evidence).toHaveLength(1);
  });

  it("returns null for unknown ids, a plane that does not exist and no selection", () => {
    expect(inspectorModel(set, "zz")).toBeNull();
    expect(inspectorModel(set, planeId("bravo"))).toBeNull();
    expect(inspectorModel(set, null)).toBeNull();
    expect(inspectorModel(null, B1)).toBeNull();
  });

  it("notes that source dip is an attribute only", () => {
    const p = pick("p", "Dip", { source_dip: depth("md", 12, "deg") });
    const s = { ...emptySet(), surfaces: [surface("dip", "Dip", { tier: "T1", tier_label: "T1", status: "observed", picks: [p] })] };
    expect(inspectorModel(s, "p")!.notes[0]).toMatch(/attributes only/);
  });
});

describe("focus helpers", () => {
  const set = richSet();
  it("targets a pick marker in render coordinates", () => {
    expect(formationFocusTarget(set, B1, { origin: ORIGIN })).toMatchObject({ kind: "pick", target: [10, -1450, -20], id: B1, wellboreId: WB });
    expect(formationFocusTarget(set, B1, { origin: [1, 1, 1] })?.target).toEqual([11, -1449, -19]);
  });

  it("targets a plane by plane id, and a surface key by its first marker", () => {
    const plane = formationFocusTarget(set, planeId("alpha"), { origin: ORIGIN })!;
    expect(plane).toMatchObject({ kind: "plane", target: [100, -1450, -50] });
    expect(plane.radius).toBeCloseTo(Math.hypot(400, 200) / 2);
    expect(plane.distance).toBeGreaterThanOrEqual(80);
    expect(formationFocusTarget(set, "alpha", { origin: ORIGIN })?.kind).toBe("pick");
  });

  it("returns null for unknown, undrawn, stale or other-wellbore targets", () => {
    expect(formationFocusTarget(set, "nope", { origin: ORIGIN })).toBeNull();
    expect(formationFocusTarget(set, B5, { origin: ORIGIN })).toBeNull();
    // A surface without a drawable plane falls back to its first placed marker.
    expect(formationFocusTarget(set, planeId("bravo"), { origin: ORIGIN })).toMatchObject({ kind: "pick", id: B3 });
    expect(formationFocusTarget(set, planeId("delta"), { origin: ORIGIN })).toBeNull();
    expect(formationFocusTarget(set, B1, { origin: ORIGIN }, "other")).toBeNull();
    expect(formationFocusTarget(set, "alpha", { origin: ORIGIN }, "other")).toBeNull();
    expect(formationFocusTarget(null, B1, { origin: ORIGIN })).toBeNull();
  });

  it("resolves selection ids", () => {
    expect(resolveFormationId(set, B1)).toBe(B1);
    expect(resolveFormationId(set, "alpha")).toBe(planeId("alpha"));
    expect(resolveFormationId(set, "bravo")).toBe(B3);
    expect(resolveFormationId(set, "alpha", "other")).toBeNull();
    expect(resolveFormationId(set, "x")).toBeNull();
    expect(resolveFormationId(null, "x")).toBeNull();
  });
});

describe("command-bus helpers", () => {
  const link = richSet().surfaces[0]!.picks[0]!.evidence[0]!;

  it("maps a pdf evidence link to a source reference", () => {
    expect(evidenceToSourceRef(link)).toEqual({ documentId: DOC, page: 7 });
    expect(evidenceToSourceRef({ ...link, document_id: null, locator: { kind: "derivation", input_claim_ids: [], result_id: "r" } as never })).toBeNull();
  });

  it("dispatches openSource and reports each outcome explicitly", () => {
    const bus = createExploreCommandBus();
    expect(openFormationSource(bus, link)).toMatchObject({ ok: false, outcome: "no-subscriber" });
    expect(openFormationSource(bus, link).message).toMatch(/not available/);
    const handler = vi.fn(() => false);
    bus.subscribe({ openSource: handler });
    const unhandled = openFormationSource(bus, link);
    expect(handler).toHaveBeenCalledWith(expect.objectContaining({ source: { documentId: DOC, page: 7 } }));
    expect(unhandled).toMatchObject({ ok: false, outcome: "unhandled" });
    expect(unhandled.message).toMatch(/could not be opened/);
    const ok = createExploreCommandBus();
    ok.subscribe({ openSource: () => true });
    expect(openFormationSource(ok, link)).toEqual({ ok: true, message: null, outcome: "handled" });
    expect(openFormationSource(null, link)).toMatchObject({ ok: false, outcome: "no-bus" });
    expect(openFormationSource(bus, { ...link, document_id: null, locator: { kind: "derivation" } as never }).outcome).toBe("no-document");
  });

  it("dispatches focusFormation and reports stale and missing camera", () => {
    const bus = createExploreCommandBus();
    // Focus commands queue when no camera listens yet (bounded, TTL) instead of reporting no-subscriber.
    expect(requestFocusFormation(bus, WB, B1)).toMatchObject({ ok: false, outcome: "queued" });
    expect(requestFocusFormation(null, WB, B1).message).toMatch(/camera is not available/);
    bus.subscribe({ focusFormation: (p) => p.formationId === B1 });
    expect(requestFocusFormation(bus, WB, B1)).toEqual({ ok: true, message: null, outcome: "handled" });
    expect(requestFocusFormation(bus, WB, "gone").message).toMatch(/stale or missing/);
  });
});

describe("labels", () => {
  const scene = buildFormationScene(richSet(), { origin: ORIGIN });
  it("honours label modes and keeps selected/hovered first", () => {
    expect(pickLabels(scene.markers, scene.planes, "off", B1, null)).toEqual([]);
    expect(pickLabels(scene.markers, scene.planes, "selected", null, null)).toEqual([]);
    expect(pickLabels(scene.markers, scene.planes, "selected", B1, B3).map((l) => l.id)).toEqual([B1, B3]);
    const all = pickLabels(scene.markers, scene.planes, "all", B3, null);
    expect(all[0]!.id).toBe(B3);
    expect(all).toHaveLength(scene.markers.length + scene.planes.length);
  });

  it("shows plane source detail only when selected and bounds the label count", () => {
    expect(pickLabels(scene.markers, scene.planes, "all", null, null).find((l) => l.kind === "plane")!.lines).toHaveLength(2);
    expect(pickLabels(scene.markers, scene.planes, "all", planeId("alpha"), null)[0]!.lines).toHaveLength(4);
    const many = Array.from({ length: MAX_LABELS + 20 }, (_, i) => ({ ...scene.markers[0]!, id: `m${i}` }));
    expect(pickLabels(many, [], "all", null, null)).toHaveLength(MAX_LABELS);
  });
});

describe("presentation store", () => {
  it("toggles, clamps opacity, notifies only on change and unsubscribes", () => {
    const s = createFormationStore();
    const l = vi.fn();
    const off = s.subscribe(l);
    s.setVisible(true);
    expect(l).not.toHaveBeenCalled();
    s.toggleSurface("alpha");
    expect(isSurfaceShown(s.getState(), "alpha")).toBe(false);
    s.toggleSurface("alpha");
    expect(isSurfaceShown(s.getState(), "alpha")).toBe(true);
    s.setPlaneOpacity(9);
    expect(s.getState().planeOpacity).toBe(0.6);
    s.setPlaneOpacity(Number.NaN);
    expect(s.getState().planeOpacity).toBe(0.22);
    s.setVisible(false);
    expect(isSurfaceShown(s.getState(), "alpha")).toBe(false);
    s.select("a");
    s.hover("b");
    s.setLabelMode("off");
    expect(s.getState()).toMatchObject({ selectedId: "a", hoverId: "b", labelMode: "off" });
    const n = l.mock.calls.length;
    off();
    s.select(null);
    expect(l.mock.calls.length).toBe(n);
  });
});

describe("normalizeLayerSet", () => {
  it("fills server defaults the generated types mark optional", () => {
    const raw = { project_id: "p", wellbore_id: null, frame: richSet().frame, empty_reason: null, generated_from_revision: "r" } as RawFormationLayerSet;
    const n = normalizeLayerSet(raw);
    expect(n).toMatchObject({ surfaces: [], conflicts: [], unsupported: [], blocked: [] });
    const s = normalizeLayerSet({ ...raw, surfaces: [{ ...surface("a", "A"), picks: undefined, blocked: undefined, evidence: undefined } as never] });
    expect(s.surfaces[0]).toMatchObject({ picks: [], blocked: [], evidence: [] });
  });
});
