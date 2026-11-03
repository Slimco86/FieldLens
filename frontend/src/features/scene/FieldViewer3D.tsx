import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { Canvas, invalidate, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { scenePalette } from "../../design/scenePalette";
import { Environment } from "./Viewer3D";
import { layoutLabels, type LabelInput } from "./labelLayout";
import { buildElement } from "./primitives";
import { createViewerProbe } from "./probe";
import { SceneResources } from "./resources";
import { buildTubeGeometry } from "./tube";
import { buildTubeCompanion, createCompanionMaterial, createCompanionMesh, wellOfSegment, type CompanionWell } from "./tubeLine";
import type { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { defaultExaggeration } from "./sceneModel";
import { instanceCounts, lodFor, type FieldPlan, type FieldWell, type Lod } from "./fieldModel";
import styles from "./Scene.module.css";

export interface FieldCommands {
  /** Fly to the wellhead close-up of one wellbore (instant under reduced motion). */
  flyTo(id: string): void;
  fitAll(): void;
  zoom(factor: number): void;
}

export interface FieldStats {
  wells: number;
  focusedId: string | null;
  glyphs: number;
  placeholders: number;
  markersShown: number;
  farDrawCalls: number;
}

declare global {
  interface Window {
    /** Test/profiling hook next to `__fieldlensSceneProbe`: the instancing state of the field scene. */
    __fieldlensFieldStats?: () => FieldStats;
    /** Test hook: canvas-relative pixel position of a wellbore's pad (null when off screen). */
    __fieldlensFieldScreen?: (id: string) => { x: number; y: number } | null;
    /** Test/profiling hook: forces the viewer to rebuild its GPU resources `n` times (leak check). */
    __fieldlensFieldRebuild?: (n: number) => void;
  }
}

interface Props {
  plan: FieldPlan;
  selectedId: string | null;
  onActivate: (id: string) => void;
  onClear: () => void;
  commands: MutableRefObject<FieldCommands | null>;
  onContextLost: () => void;
}

const DEFAULT_DIR = new THREE.Vector3(1, 0.62, 1).normalize();
/** Close-up framing of one wellbore scales with the pad so the camera never ends up inside it. */
const focusRadius = (plan: FieldPlan, w: FieldWell): number => Math.max(Math.min(40, Math.max(12, plan.nearestM ?? 40)), w.glyphHeightM * 2.5);
const focusDrop = (plan: FieldPlan, w: FieldWell): number => focusRadius(plan, w) * 0.15;
const reducedMotion = (): boolean => typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Owner of the instanced far set's GPU resources (one geometry per shape, one material per kind of mesh). */
class Kit {
  readonly items: { dispose(): void }[] = [];
  own<T extends { dispose(): void }>(d: T): T {
    this.items.push(d);
    return d;
  }
  dispose(): void {
    for (const i of this.items) i.dispose();
    this.items.length = 0;
  }
}

/** Wellhead "tree" glyph in unit space: base 1 wide and 1 tall; scaled per instance. */
function glyphGeometry(): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [];
  const add = (g: THREE.BufferGeometry, y: number): void => {
    g.translate(0, y, 0);
    const flat = g.toNonIndexed();
    flat.deleteAttribute("uv");
    g.dispose();
    parts.push(flat);
  };
  add(new THREE.CylinderGeometry(1, 1.15, 0.14, 14), 0.07);
  add(new THREE.CylinderGeometry(0.42, 0.42, 0.9, 12), 0.5);
  add(new THREE.BoxGeometry(1.7, 0.16, 0.16), 0.62);
  add(new THREE.SphereGeometry(0.34, 12, 8), 1.0);
  const merged = mergeGeometries(parts, false);
  for (const p of parts) p.dispose();
  return merged;
}

interface FarSet {
  group: THREE.Group;
  kit: Kit;
  pads: THREE.InstancedMesh;
  padIds: string[];
  glyphs: THREE.InstancedMesh | null;
  glyphIds: string[];
  placeholders: THREE.InstancedMesh | null;
  placeholderIds: string[];
  tube: THREE.Mesh | null;
  /** Triangle start of every tube section (ascending) and the well it belongs to. */
  tubeStarts: number[];
  tubeIds: string[];
  /** Screen-space minimum-width companion of the tube (one draw call for every well) and its picking map. */
  tubeLine: THREE.Object3D | null;
  tubeLineMaterial: LineMaterial | null;
  lineStarts: number[];
  lineIds: string[];
  markers: THREE.InstancedMesh | null;
  /** Owner of each marker instance currently shown. */
  markerOwners: string[];
  /** Candidate wells for markers. */
  markerWells: FieldWell[];
}

const colorOf = (hex: string): THREE.Color => new THREE.Color(hex);
const padColor = (w: FieldWell): string =>
  w.status === "spec" ? scenePalette.fieldPad : w.status === "missing" ? scenePalette.fieldPadMissing : w.status === "error" ? scenePalette.fieldPadError : scenePalette.fieldPadLoading;

function buildFar(plan: FieldPlan, focusedId: string | null): FarSet {
  const kit = new Kit();
  const group = new THREE.Group();
  group.name = "field-far";
  const tmp = new THREE.Object3D();
  const spec = plan.wells.filter((w) => w.status === "spec");
  // The focused well's own glyph stays when it has no surface components of its own to show.
  const focusedWell = focusedId === null ? undefined : plan.byId.get(focusedId);
  const keepGlyph = focusedWell !== undefined && (focusedWell.counts.surface === 0);
  const far = spec.filter((w) => w.id !== focusedId);
  const glyphWells = spec.filter((w) => w.id !== focusedId || keepGlyph);
  const holders = plan.wells.filter((w) => w.status !== "spec");

  // Pads: one flat box per wellbore (also the main click target), tinted by spec state.
  const padH = Math.max(0.6, plan.extentM * 0.0016);
  const padMat = kit.own(new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.05 }));
  const pads = new THREE.InstancedMesh(kit.own(new THREE.BoxGeometry(1, 1, 1)), padMat, Math.max(1, plan.wells.length));
  pads.count = plan.wells.length;
  pads.frustumCulled = false;
  pads.userData["role"] = "pad";
  plan.wells.forEach((w, i) => {
    tmp.position.set(w.position[0], padH / 2, w.position[2]);
    tmp.scale.set(w.padHalfM * 2, padH, w.padHalfM * 2);
    tmp.updateMatrix();
    pads.setMatrixAt(i, tmp.matrix);
    pads.setColorAt(i, colorOf(padColor(w)));
  });
  pads.computeBoundingSphere();
  group.add(pads);
  // The focused pad keeps its fill and gets an outline, so the wellhead and components stay visible.
  const fw = focusedId === null ? undefined : plan.byId.get(focusedId);
  if (fw !== undefined) {
    const h = fw.padHalfM * 1.25;
    const halo = new THREE.Mesh(
      kit.own(new THREE.PlaneGeometry(h * 2, h * 2)),
      kit.own(new THREE.MeshBasicMaterial({ color: colorOf(scenePalette.highlight), transparent: true, opacity: 0.3, depthWrite: false })),
    );
    halo.rotation.x = -Math.PI / 2;
    halo.position.set(fw.position[0], padH * 0.5, fw.position[2]);
    halo.frustumCulled = false;
    group.add(halo);
  }

  // Wellhead glyphs (spec wells that are not the focused one).
  let glyphs: THREE.InstancedMesh | null = null;
  if (glyphWells.length > 0) {
    glyphs = new THREE.InstancedMesh(
      kit.own(glyphGeometry()),
      kit.own(new THREE.MeshStandardMaterial({ color: scenePalette.steelBright, metalness: 0.6, roughness: 0.35 })),
      glyphWells.length,
    );
    glyphs.frustumCulled = false;
    glyphs.userData["role"] = "glyph";
    glyphWells.forEach((w, i) => {
      tmp.position.set(w.position[0], padH, w.position[2]);
      tmp.scale.set(w.glyphRadiusM, w.glyphHeightM, w.glyphRadiusM);
      tmp.updateMatrix();
      glyphs!.setMatrixAt(i, tmp.matrix);
    });
    glyphs.computeBoundingSphere();
    group.add(glyphs);
  }

  // Placeholders: a flat ring for each wellbore without a (loaded) spec, never a wellhead.
  let placeholders: THREE.InstancedMesh | null = null;
  if (holders.length > 0) {
    placeholders = new THREE.InstancedMesh(
      kit.own(new THREE.RingGeometry(0.62, 1, 40)),
      kit.own(new THREE.MeshBasicMaterial({ side: THREE.DoubleSide })),
      holders.length,
    );
    placeholders.frustumCulled = false;
    placeholders.userData["role"] = "placeholder";
    holders.forEach((w, i) => {
      tmp.position.set(w.position[0], padH + 0.3, w.position[2]);
      tmp.rotation.set(-Math.PI / 2, 0, 0);
      tmp.scale.setScalar(w.padHalfM * 0.55);
      tmp.updateMatrix();
      placeholders!.setMatrixAt(i, tmp.matrix);
      placeholders!.setColorAt(i, colorOf(w.status === "error" ? scenePalette.paintRed : w.status === "missing" ? scenePalette.trajectoryPlaceholder : scenePalette.depthMark));
    });
    tmp.rotation.set(0, 0, 0);
    placeholders.computeBoundingSphere();
    group.add(placeholders);
  }

  // Trajectories: one merged tube mesh (vertex colours carry available vs placeholder).
  let tube: THREE.Mesh | null = null;
  const tubeStarts: number[] = [];
  const tubeIds: string[] = [];
  let tubeLine: THREE.Object3D | null = null;
  let tubeLineMaterial: LineMaterial | null = null;
  let lineStarts: number[] = [];
  let lineIds: string[] = [];
  if (far.length > 0) {
    const geos: THREE.BufferGeometry[] = [];
    let tri = 0;
    for (const w of far) {
      const verts = w.model!.path.vertices();
      // Default radius = the selected-state radius (per-well rule), so traces are visible unselected;
      // selection stays distinct through the bright emissive trace, the halo and the full primitives.
      const g = buildTubeGeometry(verts, { outerRadius: w.tubeRadiusM, innerRadius: null, cutaway: false, radialSegments: 6 });
      g.translate(w.position[0], 0, w.position[2]);
      const count = g.getAttribute("position").count;
      const c = colorOf(w.trajectoryAvailable ? scenePalette.trajectory : scenePalette.trajectoryPlaceholder);
      const col = new Float32Array(count * 3);
      for (let i = 0; i < count; i += 1) col.set([c.r, c.g, c.b], i * 3);
      g.setAttribute("color", new THREE.BufferAttribute(col, 3));
      tubeStarts.push(tri);
      tubeIds.push(w.id);
      tri += (g.index?.count ?? 0) / 3;
      geos.push(g);
    }
    const companionWells: CompanionWell[] = far.map((w) => ({
      id: w.id,
      position: w.position,
      vertices: w.model!.path.vertices(),
      color: colorOf(w.trajectoryAvailable ? scenePalette.trajectory : scenePalette.trajectoryPlaceholder),
    }));
    const companion = buildTubeCompanion(companionWells);
    if (companion !== null) {
      tubeLineMaterial = kit.own(createCompanionMaterial());
      tubeLine = createCompanionMesh(companion, tubeLineMaterial);
      kit.own(companion.geometry);
      lineStarts = companion.segmentStarts;
      lineIds = companion.wellIds;
      group.add(tubeLine);
    }
    const merged = mergeGeometries(geos, false);
    for (const g of geos) g.dispose();
    tube = new THREE.Mesh(
      kit.own(merged),
      kit.own(new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.4, metalness: 0.15, emissive: new THREE.Color(0xffffff), emissiveIntensity: 0.0 })),
    );
    tube.userData["role"] = "tube";
    tube.frustumCulled = false;
    group.add(tube);
  }

  // Coarse markers: capacity for every marker of the far wells; the visible subset follows the LOD.
  let markers: THREE.InstancedMesh | null = null;
  const capacity = far.reduce((s, w) => s + w.markers.length, 0);
  if (capacity > 0) {
    markers = new THREE.InstancedMesh(
      kit.own(new THREE.SphereGeometry(1, 10, 8)),
      kit.own(new THREE.MeshStandardMaterial({ roughness: 0.45, metalness: 0.2 })),
      capacity,
    );
    markers.count = 0;
    markers.frustumCulled = false;
    markers.userData["role"] = "marker";
    group.add(markers);
  }
  return {
    group,
    kit,
    pads,
    padIds: plan.wells.map((w) => w.id),
    glyphs,
    glyphIds: glyphWells.map((w) => w.id),
    placeholders,
    placeholderIds: holders.map((w) => w.id),
    tube,
    tubeStarts,
    tubeIds,
    tubeLine,
    tubeLineMaterial,
    lineStarts,
    lineIds,
    markers,
    markerOwners: [],
    markerWells: far,
  };
}

/** Full primitives of the focused wellbore, in its own group at its grid position. */
function buildFocused(well: FieldWell): { group: THREE.Group; lib: SceneResources } | null {
  const model = well.model;
  if (model === null) return null;
  const lib = new SceneResources();
  const exaggeration = defaultExaggeration(well.depthM);
  const group = new THREE.Group();
  group.name = `focused-${well.id}`;
  group.userData["wellId"] = well.id;
  group.position.set(well.position[0], 0, well.position[2]);
  const verts = model.path.vertices();
  const traj = new THREE.Mesh(
    lib.track(buildTubeGeometry(verts, { outerRadius: well.tubeRadiusM, innerRadius: null, cutaway: false, radialSegments: 10 })),
    lib.own(
      new THREE.MeshStandardMaterial({
        color: colorOf(model.path.available ? scenePalette.trajectory : scenePalette.trajectoryPlaceholder),
        emissive: colorOf(model.path.available ? scenePalette.trajectory : scenePalette.trajectoryPlaceholder),
        emissiveIntensity: 0.55,
        roughness: 0.4,
      }),
    ),
  );
  group.add(traj);
  const ctx = { lib, path: model.path, exaggeration, surfaceScale: 1, cutaway: true };
  for (const el of [...model.downhole, ...model.surface]) group.add(buildElement(el, ctx));
  group.updateMatrixWorld(true);
  return { group, lib };
}

function wellOf(e: ThreeEvent<MouseEvent | PointerEvent>, far: FarSet): string | null {
  const o = e.object;
  let p: THREE.Object3D | null = o;
  while (p !== null) {
    const id = p.userData["wellId"] as string | undefined;
    if (id !== undefined) return id;
    p = p.parent;
  }
  const role = o.userData["role"] as string | undefined;
  const inst = e.instanceId;
  if (role === "pad" && inst !== undefined) return far.padIds[inst] ?? null;
  if (role === "glyph" && inst !== undefined) return far.glyphIds[inst] ?? null;
  if (role === "placeholder" && inst !== undefined) return far.placeholderIds[inst] ?? null;
  if (role === "marker" && inst !== undefined) return far.markerOwners[inst] ?? null;
  if (role === "tubeLine" && e.faceIndex !== undefined && e.faceIndex !== null) return wellOfSegment(far.lineStarts, far.lineIds, e.faceIndex);
  if (role === "tube" && e.faceIndex !== undefined && e.faceIndex !== null) {
    let lo = 0;
    let hi = far.tubeStarts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (far.tubeStarts[mid]! <= e.faceIndex) lo = mid;
      else hi = mid - 1;
    }
    return far.tubeIds[lo] ?? null;
  }
  return null;
}

interface Anim {
  t: number;
  dur: number;
  fromPos: THREE.Vector3;
  toPos: THREE.Vector3;
  fromTarget: THREE.Vector3;
  toTarget: THREE.Vector3;
}

function FieldContents({ plan, selectedId, onActivate, commands, layerRef, labelEls }: Props & { layerRef: MutableRefObject<HTMLDivElement | null>; labelEls: MutableRefObject<Map<string, HTMLElement>> }) {
  const { camera, gl, scene, controls, size } = useThree();
  const [rebuild, setRebuild] = useState(0);
  const far = useMemo(
    () => buildFar(plan, selectedId),
    // `rebuild` only exists for the leak probe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [plan, selectedId, rebuild],
  );
  const focused = useMemo(
    () => (selectedId === null ? null : buildFocused(plan.byId.get(selectedId) ?? ({ model: null } as unknown as FieldWell))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [plan, selectedId, rebuild],
  );
  const farRef = useRef(far);
  farRef.current = far;
  const anim = useRef<Anim | null>(null);
  const first = useRef(true);
  const userMoved = useRef(false);
  const lastNear = useRef(0);
  const lodKey = useRef("");
  const ctl = controls as unknown as { target: THREE.Vector3; update: () => void } | null;
  const tmp = useMemo(() => new THREE.Vector3(), []);
  const labelSizes = useRef(new Map<string, { w: number; h: number }>());

  useEffect(() => {
    lodKey.current = "";
    invalidate();
    return () => far.kit.dispose();
  }, [far]);
  useEffect(() => {
    if (focused === null) return;
    invalidate();
    return () => focused.lib.dispose();
  }, [focused]);

  const frame = useMemo(
    () => ({
      go(center: THREE.Vector3, radius: number, instant: boolean) {
        if (ctl === null) return;
        const cam = camera as THREE.PerspectiveCamera;
        const dir = DEFAULT_DIR.clone();
        const fov = (cam.fov * Math.PI) / 180;
        const aspect = size.width / Math.max(1, size.height);
        const fit = Math.max(1, 1 / Math.min(1, aspect));
        const dist = Math.max(2.5, (radius / Math.sin(fov / 2)) * 1.1 * Math.min(fit, 1.6));
        const toPos = center.clone().add(dir.multiplyScalar(dist));
        if (instant || reducedMotion() || first.current) {
          anim.current = null;
          cam.position.copy(toPos);
          ctl.target.copy(center);
          ctl.update();
          first.current = false;
          invalidate();
          return;
        }
        anim.current = { t: 0, dur: 0.9, fromPos: cam.position.clone(), toPos, fromTarget: ctl.target.clone(), toTarget: center.clone() };
        invalidate();
      },
    }),
    [camera, ctl, size.width, size.height],
  );

  const fieldSphere = useMemo(() => {
    // Frames the wellhead spread, the horizontal reach of the traces and the deepest trace.
    const f = plan.framing;
    return { center: new THREE.Vector3(f.center[0], f.center[1], f.center[2]), radius: f.radiusM };
  }, [plan]);

  useEffect(() => {
    commands.current = {
      flyTo: (id) => {
        const w = plan.byId.get(id);
        if (w === undefined) return;
        frame.go(new THREE.Vector3(w.position[0], -focusDrop(plan, w), w.position[2]), focusRadius(plan, w), false);
      },
      fitAll: () => frame.go(fieldSphere.center, fieldSphere.radius, false),
      zoom: (factor) => {
        if (ctl === null) return;
        const cam = camera as THREE.PerspectiveCamera;
        const toPos = ctl.target.clone().add(cam.position.clone().sub(ctl.target).multiplyScalar(factor));
        if (reducedMotion()) {
          cam.position.copy(toPos);
          ctl.update();
          invalidate();
        } else {
          anim.current = { t: 0, dur: 0.35, fromPos: cam.position.clone(), toPos, fromTarget: ctl.target.clone(), toTarget: ctl.target.clone() };
          invalidate();
        }
      },
    };
    return () => {
      commands.current = null;
    };
  }, [commands, plan, frame, fieldSphere, camera, ctl]);

  // Initial framing: the focused wellbore when returning from its view, else the whole field. The
  // framing follows the plan (specs arrive one by one) until the user moves the camera.
  const initial = useRef(selectedId);
  useEffect(() => {
    if (ctl === null || userMoved.current) return;
    const id = initial.current;
    const w = id === null ? undefined : plan.byId.get(id);
    if (w !== undefined) frame.go(new THREE.Vector3(w.position[0], -focusDrop(plan, w), w.position[2]), focusRadius(plan, w), true);
    else frame.go(fieldSphere.center, fieldSphere.radius, true);
  }, [ctl, plan, frame, fieldSphere]);
  useEffect(() => {
    if (ctl === null) return;
    const el = gl.domElement;
    const mark = () => {
      userMoved.current = true;
    };
    el.addEventListener("pointerdown", mark);
    el.addEventListener("wheel", mark, { passive: true });
    return () => {
      el.removeEventListener("pointerdown", mark);
      el.removeEventListener("wheel", mark);
    };
  }, [ctl, gl]);

  useEffect(() => {
    if (!window.__FIELDLENS_SCENE_PROBE__) return;
    const cam = camera as THREE.PerspectiveCamera;
    window.__fieldlensSceneProbe = createViewerProbe(gl, scene, cam, () => ctl?.target ?? new THREE.Vector3());
    window.__fieldlensFieldStats = () => {
      const f = farRef.current;
      const lods = new Map<string, Lod>();
      const owners = new Set(f.markerOwners);
      for (const id of owners) lods.set(id, "markers");
      const c = instanceCounts(plan, selectedId, lods);
      return { wells: plan.wells.length, focusedId: selectedId, glyphs: c.glyphs, placeholders: c.placeholders, markersShown: f.markers?.count ?? 0, farDrawCalls: c.drawCalls };
    };
    window.__fieldlensFieldRebuild = (n) => setRebuild((v) => v + n);
    window.__fieldlensFieldScreen = (wid) => {
      const w = plan.byId.get(wid);
      if (w === undefined) return null;
      const v = new THREE.Vector3(w.position[0], w.glyphHeightM * 0.4, w.position[2]).project(cam);
      if (v.z > 1 || v.z < -1) return null;
      return { x: ((v.x + 1) / 2) * size.width, y: ((1 - v.y) / 2) * size.height };
    };
    return () => {
      delete window.__fieldlensFieldScreen;
      delete window.__fieldlensSceneProbe;
      delete window.__fieldlensFieldStats;
      delete window.__fieldlensFieldRebuild;
    };
  }, [gl, scene, camera, ctl, plan, selectedId, size]);

  // Pixel-unit line width needs the canvas size: updated on resize / rebuild only (no per-frame work).
  useEffect(() => {
    far.tubeLineMaterial?.resolution.set(size.width, size.height);
    invalidate();
  }, [far, size.width, size.height]);

  useFrame((_, delta) => {
    const cam = camera as THREE.PerspectiveCamera;
    const a = anim.current;
    if (a !== null && ctl !== null) {
      a.t = Math.min(1, a.t + delta / a.dur);
      const e = a.t < 0.5 ? 2 * a.t * a.t : 1 - (-2 * a.t + 2) ** 2 / 2;
      cam.position.lerpVectors(a.fromPos, a.toPos, e);
      ctl.target.lerpVectors(a.fromTarget, a.toTarget, e);
      ctl.update();
      if (a.t >= 1) anim.current = null;
      else invalidate();
    }
    const dist = ctl === null ? cam.position.length() : cam.position.distanceTo(ctl.target);
    const near = Math.min(Math.max(dist * 0.01, 0.05), 200);
    if (Math.abs(near - lastNear.current) / near > 0.02) {
      lastNear.current = near;
      cam.near = near;
      cam.far = Math.max(dist * 12, 8000) + plan.extentM * 6;
      cam.updateProjectionMatrix();
    }
    if (scene.fog instanceof THREE.Fog) {
      scene.fog.near = dist * 1.2;
      scene.fog.far = dist * 6 + plan.extentM * 2;
    }

    // Marker LOD: wells within range show their coarse markers (refs only; rewritten only when the set changes).
    const f = farRef.current;
    if (f.markers !== null) {
      const inRange: FieldWell[] = [];
      for (const w of f.markerWells) {
        tmp.set(w.position[0], -w.depthM / 2, w.position[2]);
        if (lodFor(false, cam.position.distanceTo(tmp), w.depthM) === "markers") inRange.push(w);
      }
      const key = inRange.map((w) => w.id).join(",");
      if (key !== lodKey.current) {
        lodKey.current = key;
        const dummy = new THREE.Object3D();
        const owners: string[] = [];
        let i = 0;
        for (const w of inRange) {
          for (const m of w.markers) {
            dummy.position.set(w.position[0] + m.position[0], m.position[1], w.position[2] + m.position[2]);
            dummy.scale.setScalar(w.markerRadiusM * (m.kind === "perforation_interval" ? 1.25 : 1));
            dummy.updateMatrix();
            f.markers.setMatrixAt(i, dummy.matrix);
            f.markers.setColorAt(i, colorOf(m.kind === "perforation_interval" ? scenePalette.perforation : m.illustrative ? scenePalette.fieldMarkerIllustrative : scenePalette.fieldMarkerDocumented));
            owners.push(w.id);
            i += 1;
          }
        }
        f.markers.count = i;
        f.markerOwners = owners;
        f.markers.instanceMatrix.needsUpdate = true;
        if (f.markers.instanceColor !== null) f.markers.instanceColor.needsUpdate = true;
        if (i > 0) f.markers.computeBoundingSphere();
        invalidate();
      }
    }

    // Labels: project each wellhead; declutter; write transforms straight to the DOM (no React state).
    const layer = layerRef.current;
    if (layer === null) return;
    const inputs: LabelInput[] = [];
    for (const w of plan.wells) {
      const el = labelEls.current.get(w.id);
      if (el === undefined) continue;
      let sz = labelSizes.current.get(w.id);
      if (sz === undefined || sz.w === 0) {
        const r = el.getBoundingClientRect();
        sz = { w: r.width, h: r.height };
        labelSizes.current.set(w.id, sz);
      }
      tmp.set(w.position[0], w.glyphHeightM * 1.25, w.position[2]).project(cam);
      inputs.push({
        id: w.id,
        x: ((tmp.x + 1) / 2) * size.width,
        y: ((1 - tmp.y) / 2) * size.height,
        visible: tmp.z < 1 && tmp.z > -1,
        w: sz.w || 120,
        h: sz.h || 22,
        priority: w.id === selectedId ? -1 : w.status === "spec" ? 1 + w.index * 0.001 : 2 + w.index * 0.001,
      });
    }
    for (const p of layoutLabels(inputs, { w: size.width, h: size.height })) {
      const el = labelEls.current.get(p.id);
      if (el === undefined) continue;
      el.style.visibility = p.shown ? "visible" : "hidden";
      if (p.shown) el.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px)`;
    }
  });

  const onClick = (e: ThreeEvent<MouseEvent>) => {
    const id = wellOf(e, farRef.current);
    if (id === null) return;
    e.stopPropagation();
    onActivate(id);
  };
  const onOver = (e: ThreeEvent<PointerEvent>) => {
    if (wellOf(e, farRef.current) !== null) {
      e.stopPropagation();
      gl.domElement.style.cursor = "pointer";
    }
  };
  const onOut = () => {
    gl.domElement.style.cursor = "";
  };

  const ground = useMemo(() => {
    const size2 = Math.max(plan.extentM * 2.6, 600);
    const grid = new THREE.GridHelper(size2, 26, colorOf(scenePalette.gridMajor), colorOf(scenePalette.gridMinor));
    const m = grid.material as THREE.LineBasicMaterial;
    m.transparent = true;
    m.opacity = 0.55;
    const disc = new THREE.Mesh(
      new THREE.CircleGeometry(size2 / 2, 64),
      new THREE.MeshBasicMaterial({ color: colorOf(scenePalette.groundDisc), transparent: true, opacity: 0.3, side: THREE.DoubleSide, depthWrite: false }),
    );
    disc.rotation.x = -Math.PI / 2;
    disc.position.y = -0.1;
    return { grid, disc };
  }, [plan.extentM]);
  useEffect(
    () => () => {
      for (const o of [ground.grid, ground.disc]) {
        o.geometry.dispose();
        (o.material as THREE.Material).dispose();
      }
    },
    [ground],
  );

  return (
    <>
      <Environment />
      <hemisphereLight args={[0xdfe9ff, 0x1a2436, 0.6]} />
      <directionalLight position={[300, 600, 400]} intensity={1.6} color={0xfff2e0} />
      <directionalLight position={[-400, 200, -300]} intensity={0.5} color={0x9db8ff} />
      <primitive object={ground.disc} />
      <primitive object={ground.grid} />
      {/* Pick handlers sit on a wrapper group that owns the field scene objects added above. */}
      <group onClick={onClick} onPointerOver={onOver} onPointerOut={onOut}>
        <primitive object={far.group} />
        {focused !== null && <primitive object={focused.group} />}
      </group>
      <OrbitControls makeDefault enableDamping dampingFactor={0.14} zoomToCursor screenSpacePanning minDistance={2} maxDistance={400000} keyEvents />
    </>
  );
}

export default function FieldViewer3D(props: Props) {
  const { plan, selectedId, onActivate, onClear } = props;
  const layerRef = useRef<HTMLDivElement | null>(null);
  const labelEls = useRef(new Map<string, HTMLElement>());
  const [lost, setLost] = useState(false);

  return (
    <div className={styles.canvasWrap} data-testid="scene-canvas-wrap">
      <Canvas
        frameloop="demand"
        dpr={[1, 2]}
        camera={{ fov: 38, near: 1, far: 60000, position: [1500, 900, 1500] }}
        gl={{ antialias: true, powerPreference: "high-performance", alpha: true }}
        tabIndex={0}
        role="group"
        aria-label={`3D field view of the reconstructed wellbores (${plan.layoutKind === "surface" ? "surface-location layout" : "schematic grid, not map positions"}). Use the wellbore list to select by keyboard.`}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.05;
          gl.outputColorSpace = THREE.SRGBColorSpace;
          gl.setClearColor(0x000000, 0);
          gl.domElement.addEventListener("webglcontextlost", (e) => {
            e.preventDefault();
            setLost(true);
            props.onContextLost();
          });
        }}
        onPointerMissed={onClear}
        className={styles.canvas}
        data-testid="scene-canvas"
      >
        <FieldContents {...props} layerRef={layerRef} labelEls={labelEls} />
      </Canvas>
      <div className={styles.labelLayer} ref={layerRef} aria-hidden="true" data-testid="scene-label-layer">
        {plan.wells.map((w) => (
          <button
            key={w.id}
            type="button"
            tabIndex={-1}
            ref={(el) => {
              if (el === null) labelEls.current.delete(w.id);
              else labelEls.current.set(w.id, el);
            }}
            data-testid={`field-label-${w.id}`}
            data-status={w.status}
            data-selected={w.id === selectedId}
            className={styles.label}
            onClick={() => onActivate(w.id)}
          >
            {w.name}
            {w.status !== "spec" && <span className={styles.labelTag}> · {w.status === "missing" ? "no asset spec" : w.status === "error" ? "load failed" : "loading"}</span>}
            {w.placement === "unlocated" && <span className={styles.labelTag}> · unlocated</span>}
          </button>
        ))}
      </div>
      <p className={styles.fieldChip} data-testid="field-layout-label">
        {plan.layoutLabel} · display widths exaggerated, not to scale
      </p>
      {lost && (
        <p className={styles.lost} role="alert">
          The graphics context was lost. Switch tabs and back to reload the view; the wellbore list still works.
        </p>
      )}
    </div>
  );
}
