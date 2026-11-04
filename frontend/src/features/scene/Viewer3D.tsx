import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { Canvas, invalidate, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { scenePalette } from "../../design/scenePalette";
import { layoutLabels, type LabelInput } from "./labelLayout";
import { buildElement, elementBounds, type BuildContext } from "./primitives";
import { SceneResources, setHighlighted } from "./resources";
import { buildTubeGeometry } from "./tube";
import type { SceneElement, SceneModel } from "./sceneModel";
import { useExploreCommandBus, useExploreCommandHandlers } from "./ExploreCommandsContext";
import { arrivalPose, normalize, type OrbitPose, type V3 } from "./cameraPath";
import { CameraRig } from "./cameraRig";
import { buildFlyOverPlan, FlyOverPlayer, type FlyOverStatus } from "./flyOverPlan";
import { RENDER_ORIGIN, renderLayers, type SceneLayerContext, type SceneLayers } from "./sceneLayers";
import { makeFocusFormationHandler, type ResolveFormationFocus } from "./formationFocus";
import styles from "./Scene.module.css";
export { webgl2Available } from "./webgl";

export type LabelMode = "all" | "selected" | "off";

export interface ViewerOptions {
  exaggeration: number;
  surfaceScale: number;
  cutaway: boolean;
  labels: LabelMode;
  depthMarks: boolean;
}

export interface ViewerCommands {
  fitAll(): void;
  /** Wellhead, surface facilities and the top of the hole (the default first view). */
  fitWellhead(): void;
  focus(id: string): void;
  /** Frame a render-space point (metres) with the given radius, keeping the viewing direction (formation focus). */
  focusPoint(target: readonly [number, number, number], radius: number): void;
  zoom(factor: number): void;
  /** Start the single-wellbore fly-over (CM-3); false when there is nothing located to visit. */
  flyOver(): boolean;
  /** Stop a running or paused fly-over and hand the camera back at its current pose; true when one was active. */
  stopFlyOver(): boolean;
  pauseFlyOver(): void;
  resumeFlyOver(): void;
  /** Jump (with a short flight) to the next/previous stop. */
  stepFlyOver(direction: 1 | -1): void;
  setFlySpeed(speed: number): void;
}

export interface ViewerProbe {
  /** Render `frames` orbit frames and report timings and renderer counters (profiling/tests only). */
  measure(frames: number): { frames: number; meanMs: number; p95Ms: number; maxMs: number; drawCalls: number; triangles: number; geometries: number; textures: number };
  /** Render once and count pixels that differ from the first (backdrop) pixel. */
  nonBlank(): { total: number; different: number };
}

declare global {
  interface Window {
    /** Test/profiling hook: when set to `true` before load the viewer registers `__fieldlensSceneProbe`. */
    __FIELDLENS_SCENE_PROBE__?: boolean;
    __fieldlensSceneProbe?: ViewerProbe;
  }
}

interface Props {
  model: SceneModel;
  options: ViewerOptions;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  commands: MutableRefObject<ViewerCommands | null>;
  /** Called when the WebGL context is lost so the page can offer a reload. */
  onContextLost: () => void;
  /** Wellbore this viewer shows; lets the Explore command bus ignore commands for other wellbores. */
  wellboreId?: string;
  /** Optional scene content mounted inside the Canvas (empty by default); see `SceneLayerContext`. */
  layers?: SceneLayers;
  /**
   * Pose request for `focusFormation` (pure lookup owned by the formation layer). Returns null when the formation is
   * unknown, belongs to another wellbore or cannot be placed: the command is then refused (no motion) and announced.
   */
  resolveFormationFocus?: ResolveFormationFocus;
  /** Fly-over state changes (stop changes, play/pause/stop/finish); never called per frame. */
  onFlyOverStatus?: (status: FlyOverStatus) => void;
}

interface Anchor {
  id: string;
  text: string;
  position: THREE.Vector3;
  /** 0 = most important. */
  priority: number;
  kind: "element" | "depth" | "area";
  illustrative: boolean;
}

const DEFAULT_DIR = new THREE.Vector3(1, 0.42, 1).normalize();

const reducedMotion = (): boolean => typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function idOf(obj: THREE.Object3D | null): string | null {
  let o: THREE.Object3D | null = obj;
  while (o !== null) {
    const id = o.userData["elementId"] as string | undefined;
    if (id !== undefined) return id;
    o = o.parent;
  }
  return null;
}

/** Round a span to a readable step (1, 2, 5 x 10^n). */
function niceStep(span: number, target = 6): number {
  const raw = span / target;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const f = raw / pow;
  return (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * pow;
}

// ------------------------------------------------------------------ contents inside the Canvas

export function Environment(): null {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const room = new RoomEnvironment();
    const rt = pmrem.fromScene(room, 0.04);
    scene.environment = rt.texture;
    scene.environmentIntensity = 0.85;
    scene.fog = new THREE.Fog(new THREE.Color(scenePalette.fog), 100, 10000);
    invalidate();
    return () => {
      scene.environment = null;
      scene.fog = null;
      rt.dispose();
      pmrem.dispose();
      room.dispose();
    };
  }, [gl, scene]);
  return null;
}

function Ground({ model }: { model: SceneModel }) {
  const size = useMemo(() => {
    const v = model.path.vertices();
    let reach = 0;
    for (const p of v) reach = Math.max(reach, Math.hypot(p.position[0], p.position[2]));
    const depth = Math.abs(v[v.length - 1]?.position[1] ?? 0);
    return Math.max(240, reach * 2.6, depth * 0.35);
  }, [model]);
  const { coarse, fine, disc } = useMemo(() => {
    const c = new THREE.GridHelper(size, 20, new THREE.Color(scenePalette.gridMajor), new THREE.Color(scenePalette.gridMinor));
    const f = new THREE.GridHelper(200, 20, new THREE.Color(scenePalette.gridMajor), new THREE.Color(scenePalette.gridMinor));
    f.position.y = 0.03;
    for (const g of [c, f]) {
      const m = g.material as THREE.LineBasicMaterial;
      m.transparent = true;
      m.opacity = g === c ? 0.55 : 0.7;
      m.fog = true;
    }
    const d = new THREE.Mesh(
      new THREE.CircleGeometry(size / 2, 64),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(scenePalette.groundDisc), transparent: true, opacity: 0.28, side: THREE.DoubleSide, depthWrite: false }),
    );
    d.rotation.x = -Math.PI / 2;
    d.position.y = -0.05;
    return { coarse: c, fine: f, disc: d };
  }, [size]);
  useEffect(
    () => () => {
      for (const o of [coarse, fine]) {
        o.geometry.dispose();
        (o.material as THREE.Material).dispose();
      }
      disc.geometry.dispose();
      (disc.material as THREE.Material).dispose();
    },
    [coarse, fine, disc],
  );
  return (
    <>
      <primitive object={disc} />
      <primitive object={coarse} />
      <primitive object={fine} />
    </>
  );
}

interface BuiltAssets {
  root: THREE.Group;
  lib: SceneResources;
  anchors: Anchor[];
  bounds: THREE.Box3;
}

export function buildAssets(model: SceneModel, options: ViewerOptions): BuiltAssets {
  const lib = new SceneResources();
  const ctx: BuildContext = { lib, path: model.path, exaggeration: options.exaggeration, surfaceScale: options.surfaceScale, cutaway: options.cutaway };
  const root = new THREE.Group();
  root.name = "asset-root";
  const anchors: Anchor[] = [];
  const bounds = new THREE.Box3();

  // Trajectory centre line (display radius is a labelled exaggeration, never a hole size).
  const verts = model.path.vertices();
  const traj = new THREE.Mesh(
    lib.track(buildTubeGeometry(verts, { outerRadius: Math.max(0.05, options.exaggeration * 0.035), innerRadius: null, cutaway: false, radialSegments: 10 })),
    new THREE.MeshStandardMaterial({
      color: new THREE.Color(model.path.available ? scenePalette.trajectory : scenePalette.trajectoryPlaceholder),
      emissive: new THREE.Color(model.path.available ? scenePalette.trajectory : scenePalette.trajectoryPlaceholder),
      emissiveIntensity: 0.55,
      roughness: 0.4,
    }),
  );
  traj.name = "trajectory";
  root.add(traj);
  lib.own(traj.material as THREE.Material);
  const mid = verts[Math.floor(verts.length / 2)]!;
  anchors.push({
    id: "trajectory",
    text: model.path.available ? `Trajectory (display radius ×${options.exaggeration})` : "Trajectory unavailable — vertical placeholder, not a survey",
    position: new THREE.Vector3(...mid.position),
    priority: 30,
    kind: "area",
    illustrative: !model.path.available,
  });
  for (const v of verts) bounds.expandByPoint(new THREE.Vector3(...v.position));
  bounds.expandByPoint(new THREE.Vector3(0, 0, 0));

  // Unlocated components are listed (list + inspector) but never drawn: they have no place in the well.
  model.elements.forEach((el, index) => {
    if (el.zone === "unlocated") return;
    const g = buildElement(el, ctx);
    root.add(g);
    const b = elementBounds(g);
    if (!b.isEmpty()) bounds.union(b);
    const c = b.isEmpty() ? new THREE.Vector3(...el.position) : b.getCenter(new THREE.Vector3());
    if (el.zone === "downhole" && el.mdTopM !== null && el.mdBottomM !== null && (el.kind === "casing" || el.kind === "liner" || el.kind === "tubing" || el.kind === "perforation_interval")) {
      c.set(...model.path.at((el.mdTopM + el.mdBottomM) / 2).position);
    } else if (el.zone !== "downhole") {
      c.y = b.isEmpty() ? c.y : b.max.y;
    }
    anchors.push({ id: el.id, text: el.label, position: c, priority: 1 + index * 0.01 + (el.zone === "downhole" ? 0.5 : 0), kind: "element", illustrative: el.illustrative });
  });

  // The wellhead is always present at the well hole: the generic default when the spec has none placed.
  const dw = model.defaultWellhead;
  if (dw !== null) {
    const g = buildElement(dw, ctx);
    root.add(g);
    const b = elementBounds(g);
    if (!b.isEmpty()) {
      bounds.union(b);
      const c = b.getCenter(new THREE.Vector3());
      c.y = b.max.y;
      anchors.push({ id: dw.id, text: dw.label, position: c, priority: 1.9, kind: "element", illustrative: true });
    }
  }

  // The derived tie-in (wellhead to the first surveyed station) is drawn as part of the same tube.
  if (model.path.available && model.path.tieInKind !== null) {
    const m = model.path.at(model.path.firstStationMd / 2);
    anchors.push({
      id: "tie-in",
      text: `Derived ${model.path.tieInKind} tie-in, display only (not surveyed)`,
      position: new THREE.Vector3(...m.position),
      priority: 31,
      kind: "area",
      illustrative: true,
    });
  }

  // Depth marks along the path (MD), a ring perpendicular to the path and a label.
  if (options.depthMarks) {
    const step = niceStep(model.path.mdMax - model.path.mdMin);
    const ringR = Math.max(1, Math.max(...model.elements.filter((e) => e.scaleClass === "exaggerated" && e.zone === "downhole").map((e) => e.outerRadiusM), 0.15) * options.exaggeration * 1.55);
    const ringMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(scenePalette.depthMark), transparent: true, opacity: 0.55, fog: true });
    lib.own(ringMat);
    for (let md = Math.ceil(model.path.mdMin / step) * step; md <= model.path.mdMax + 1e-6; md += step) {
      if (md <= model.path.mdMin + 1e-6) continue;
      const p = model.path.at(md);
      const ring = new THREE.Mesh(lib.torus(0.012), ringMat);
      ring.scale.setScalar(ringR);
      ring.position.set(...p.position);
      ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), new THREE.Vector3(...p.tangent));
      ring.name = `depth-${md}`;
      root.add(ring);
      anchors.push({
        id: `depth-${md}`,
        text: `${md.toLocaleString("en-US")} m ${model.path.available ? "MD" : "MD (placeholder)"}`,
        position: new THREE.Vector3(p.position[0] + ringR, p.position[1], p.position[2]),
        priority: 50 + md / 1e6,
        kind: "depth",
        illustrative: false,
      });
    }
  }

  root.updateMatrixWorld(true);
  return { root, lib, anchors, bounds };
}

const WELLHEAD_VIEW_DEPTH_M = 45;

interface ViewTarget {
  center: THREE.Vector3;
  radius: number;
  keepDirection: boolean;
  /** MD on the trajectory the target sits at: the arrival then faces the trajectory (CM-2). */
  md?: number;
}

const toV3 = (v: THREE.Vector3): V3 => [v.x, v.y, v.z];

function SceneContents({ model, options, selectedId, onSelect, commands, onFlyOverStatus, onAnchors, anchorsRef, layerRef, labelModeRef, selectedRef }: Props & {
  onAnchors: (a: Anchor[]) => void;
  anchorsRef: MutableRefObject<Anchor[]>;
  layerRef: MutableRefObject<HTMLDivElement | null>;
  labelModeRef: MutableRefObject<LabelMode>;
  selectedRef: MutableRefObject<string | null>;
}) {
  const { exaggeration, surfaceScale, cutaway, depthMarks } = options;
  const built = useMemo(
    () => buildAssets(model, { ...options, exaggeration, surfaceScale, cutaway, depthMarks }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only geometry-affecting options rebuild
    [model, exaggeration, surfaceScale, cutaway, depthMarks],
  );
  const { camera, gl, scene, controls, size } = useThree();
  const rig = useMemo(() => new CameraRig(), []);
  const tour = useRef<FlyOverPlayer | null>(null);
  /** While a seek/entry flight runs, the tour clock waits (the rig owns the camera). */
  const hold = useRef(false);
  const tourFit = useRef<(() => void) | null>(null);
  const speedRef = useRef(1);
  const statusRef = useRef(onFlyOverStatus);
  statusRef.current = onFlyOverStatus;
  const bus = useExploreCommandBus();
  const first = useRef(true);
  const lastNear = useRef(0);

  useEffect(() => {
    onAnchors(built.anchors);
    invalidate();
    return () => built.lib.dispose();
  }, [built, onAnchors]);

  // Selection highlight (material swap, no React state per frame).
  useEffect(() => {
    const group = selectedId === null ? undefined : built.root.children.find((c) => c.userData["elementId"] === selectedId);
    if (group !== undefined) setHighlighted(group, built.lib, true);
    invalidate();
    return () => {
      if (group !== undefined) setHighlighted(group, built.lib, false);
    };
  }, [selectedId, built]);

  const ctl = controls as unknown as { target: THREE.Vector3; update: () => void } | null;

  const publish = (state: FlyOverStatus | null, announcement?: string) => {
    if (state === null) return;
    statusRef.current?.(announcement === undefined ? state : { ...state, announcement });
  };

  /** Stop the tour (if any) and hand the camera back at its current pose. */
  const endTour = (announcement = "Fly-over stopped.") => {
    const p = tour.current;
    if (p === null || p.state === "idle") return false;
    p.stop();
    hold.current = false;
    rig.cancel();
    publish(p.status(), announcement);
    return true;
  };

  const frame = useMemo(
    () => ({
      go(t: ViewTarget, opts: { keepTour?: boolean; durationS?: number } = {}) {
        if (ctl === null) return;
        if (opts.keepTour !== true) {
          const p = tour.current;
          if (p !== null && p.state !== "idle") {
            p.stop();
            hold.current = false;
            statusRef.current?.({ ...p.status(), announcement: "Fly-over stopped." });
          }
        }
        const cam = camera as THREE.PerspectiveCamera;
        const here = cam.position.clone().sub(ctl.target);
        const preferred = t.keepDirection && here.lengthSq() > 1e-12 ? toV3(here.normalize()) : toV3(DEFAULT_DIR);
        const fov = (cam.fov * Math.PI) / 180;
        const aspect = size.width / Math.max(1, size.height);
        const fit = Math.max(1, 1 / Math.min(1, aspect));
        const fitRange = Math.max(2.5, (t.radius / Math.sin(fov / 2)) * 1.15 * Math.min(fit, 1.6));
        let to: OrbitPose;
        if (t.md !== undefined && model.path.available) {
          // CM-2: face the trajectory (>= 35 degrees off its tangent) with a window of it in view.
          const half = Math.max(t.radius * 1.2, 10);
          const window: V3[] = [];
          for (let k = -6; k <= 6; k += 1) window.push(model.path.at(t.md + (half * k) / 6).position);
          to = arrivalPose({ target: toV3(t.center), fitRange, preferredDir: preferred, tangent: model.path.at(t.md).tangent, window, view: { fovDeg: cam.fov, aspect } });
        } else {
          to = { target: toV3(t.center), dir: normalize(preferred), range: fitRange };
        }
        rig.sync({ position: toV3(cam.position), target: toV3(ctl.target) });
        const instant = reducedMotion() || first.current;
        first.current = false;
        const applied = rig.fly(to, { instant, ...(opts.durationS === undefined ? {} : { durationS: opts.durationS }) });
        if (applied !== null) {
          cam.position.set(...applied.position);
          ctl.target.set(...applied.target);
          ctl.update();
        }
        invalidate();
      },
    }),
    [camera, ctl, size.width, size.height, model.path, rig],
  );

  useEffect(() => {
    const sphereOf = (b: THREE.Box3): ViewTarget => {
      const s = b.getBoundingSphere(new THREE.Sphere());
      return { center: s.center, radius: Math.max(s.radius, 1), keepDirection: false };
    };
    const boundsOf = (pred: (e: SceneElement) => boolean): THREE.Box3 => {
      const box = new THREE.Box3();
      for (const el of model.elements) {
        if (!pred(el)) continue;
        const g = built.root.children.find((c) => c.userData["elementId"] === el.id);
        if (g !== undefined) box.union(elementBounds(g));
      }
      return box;
    };
    tourFit.current = () => frame.go(sphereOf(built.bounds), { keepTour: true });
    commands.current = {
      fitAll: () => frame.go(sphereOf(built.bounds)),
      fitWellhead: () => {
        const b = boundsOf((e) => e.zone === "surface" || e.kind === "wellhead" || e.kind === "christmas_tree");
        const dwGroup = built.root.children.find((c) => c.userData["elementId"] === model.defaultWellhead?.id);
        if (dwGroup !== undefined) b.union(elementBounds(dwGroup));
        if (b.isEmpty()) b.set(new THREE.Vector3(-10, 0, -10), new THREE.Vector3(10, 6, 10));
        // Include the top of the hole so the first cased metres are in view.
        b.expandByPoint(new THREE.Vector3(0, -WELLHEAD_VIEW_DEPTH_M, 0));
        frame.go({ ...sphereOf(b), keepDirection: false });
      },
      focusPoint: (target, radius) => frame.go({ center: new THREE.Vector3(target[0], target[1], target[2]), radius: Math.max(radius, 1), keepDirection: true }),
      focus: (id) => {
        const el = model.byId.get(id);
        const g = built.root.children.find((c) => c.userData["elementId"] === id);
        if (g === undefined || el === undefined) return;
        const b = elementBounds(g);
        const t = sphereOf(b);
        let md: number = model.path.mdMin;
        if (el.zone === "downhole" && el.mdTopM !== null) md = el.mdBottomM !== null ? (el.mdTopM + el.mdBottomM) / 2 : el.mdTopM;
        // Long tubes: frame a window of the pipe, not its whole length.
        if (el.mdTopM !== null && el.mdBottomM !== null && (el.kind === "casing" || el.kind === "liner" || el.kind === "tubing" || el.kind === "perforation_interval")) {
          const mid = model.path.at((el.mdTopM + el.mdBottomM) / 2).position;
          t.center = new THREE.Vector3(...mid);
          t.radius = Math.min(t.radius, Math.max(el.outerRadiusM * options.exaggeration * 4, 30));
        }
        frame.go({ ...t, keepDirection: true, md });
      },
      zoom: (factor) => {
        if (ctl === null) return;
        endTour();
        const cam = camera as THREE.PerspectiveCamera;
        const dir = cam.position.clone().sub(ctl.target);
        const range = Math.max(dir.length() * factor, 1e-3);
        rig.sync({ position: toV3(cam.position), target: toV3(ctl.target) });
        const to: OrbitPose = { target: toV3(ctl.target), dir: normalize(toV3(dir)), range };
        const applied = rig.fly(to, { instant: reducedMotion(), durationS: 0.35 });
        if (applied !== null) {
          cam.position.set(...applied.position);
          ctl.update();
        }
        invalidate();
      },
      flyOver: () => {
        if (ctl === null) return false;
        const cam = camera as THREE.PerspectiveCamera;
        const radii = new Map<string, number>();
        for (const el of model.elements) {
          const g = built.root.children.find((c) => c.userData["elementId"] === el.id);
          if (g === undefined) continue;
          let r = Math.max(elementBounds(g).getBoundingSphere(new THREE.Sphere()).radius, 1);
          if (el.mdTopM !== null && el.mdBottomM !== null && (el.kind === "casing" || el.kind === "liner" || el.kind === "tubing" || el.kind === "perforation_interval")) {
            r = Math.min(r, Math.max(el.outerRadiusM * options.exaggeration * 4, 30));
          }
          radii.set(el.id, r);
        }
        const plan = buildFlyOverPlan(model.path, model.elements, { view: { fovDeg: cam.fov, aspect: size.width / Math.max(1, size.height) }, radii });
        if (plan.stops.length === 0 || !model.path.available) return false;
        const player = new FlyOverPlayer(plan, reducedMotion());
        player.setSpeed(speedRef.current);
        player.play();
        tour.current = player;
        // Enter smoothly from wherever the camera is; the tour clock waits until it arrives.
        const start = plan.poseAtMd(model.path.mdMin, plan.stops[0]!.pose.range);
        rig.sync({ position: toV3(cam.position), target: toV3(ctl.target) });
        const applied = rig.fly(start, { instant: reducedMotion() });
        hold.current = applied === null;
        if (applied !== null) {
          cam.position.set(...applied.position);
          ctl.target.set(...applied.target);
          ctl.update();
        }
        publish(player.status(), "Fly-over started.");
        invalidate();
        return true;
      },
      stopFlyOver: () => {
        const was = endTour();
        invalidate();
        return was;
      },
      pauseFlyOver: () => {
        const p = tour.current;
        if (p === null || p.state !== "playing") return;
        p.pause();
        publish(p.status(), "Fly-over paused.");
      },
      resumeFlyOver: () => {
        const p = tour.current;
        if (p === null || p.state !== "paused") return;
        p.play();
        publish(p.status(), "Fly-over resumed.");
        invalidate();
      },
      stepFlyOver: (direction) => {
        const p = tour.current;
        if (p === null || ctl === null || p.state === "idle") return;
        const pose = direction === 1 ? p.next() : p.prev();
        if (pose === null) return;
        const cam = camera as THREE.PerspectiveCamera;
        rig.sync({ position: toV3(cam.position), target: toV3(ctl.target) });
        const applied = rig.fly(pose, { instant: reducedMotion() });
        hold.current = applied === null;
        if (applied !== null) {
          cam.position.set(...applied.position);
          ctl.target.set(...applied.target);
          ctl.update();
        }
        publish(p.status());
        invalidate();
      },
      setFlySpeed: (speed) => {
        speedRef.current = Math.min(4, Math.max(0.5, speed));
        const p = tour.current;
        if (p !== null) {
          p.setSpeed(speed);
          if (p.state !== "idle") publish(p.status(), `Speed ${p.speed}x.`);
        }
      },
    };
    return () => {
      endTour();
      commands.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- publish/endTour only read refs
  }, [built, model, commands, frame, camera, ctl, options.exaggeration, rig, size.width, size.height]);

  // Initial framing once the controls exist, and whenever a new model is loaded; then let the bus
  // replay any focus command that arrived before this viewer was ready (S-1).
  useEffect(() => {
    if (ctl === null) return;
    first.current = true;
    commands.current?.fitWellhead();
    bus?.replay();
  }, [model.path, ctl, commands, bus]);

  // Pointer, wheel and key input cancel a flight or the tour and hand control back; Esc anywhere too.
  const { domElement } = gl;
  useEffect(() => {
    const cancel = () => {
      rig.cancel();
      hold.current = false;
      endTour();
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape" && tour.current !== null && tour.current.state !== "idle") cancel();
    };
    domElement.addEventListener("pointerdown", cancel);
    domElement.addEventListener("wheel", cancel, { passive: true });
    domElement.addEventListener("keydown", cancel);
    document.addEventListener("keydown", esc);
    return () => {
      domElement.removeEventListener("pointerdown", cancel);
      domElement.removeEventListener("wheel", cancel);
      domElement.removeEventListener("keydown", cancel);
      document.removeEventListener("keydown", esc);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- endTour only reads refs
  }, [domElement, rig]);

  // Profiling/test probe (only when the page sets the flag before load).
  useEffect(() => {
    if (!window.__FIELDLENS_SCENE_PROBE__) return;
    const cam = camera as THREE.PerspectiveCamera;
    window.__fieldlensSceneProbe = {
      measure(frames) {
        const times: number[] = [];
        const gl2 = gl.getContext();
        const base = cam.position.clone();
        const tgt = ctl?.target.clone() ?? new THREE.Vector3();
        gl.info.reset();
        const autoReset = gl.info.autoReset;
        gl.info.autoReset = false;
        for (let i = 0; i < frames; i += 1) {
          const a = (i / frames) * Math.PI * 2;
          const off = base.clone().sub(tgt);
          off.applyAxisAngle(new THREE.Vector3(0, 1, 0), a);
          cam.position.copy(tgt).add(off);
          cam.lookAt(tgt);
          cam.updateMatrixWorld();
          const t0 = performance.now();
          gl.render(scene, cam);
          gl2.finish();
          times.push(performance.now() - t0);
        }
        gl.info.autoReset = autoReset;
        cam.position.copy(base);
        cam.lookAt(tgt);
        const sorted = [...times].sort((x, y) => x - y);
        const info = gl.info;
        return {
          frames,
          meanMs: times.reduce((s, x) => s + x, 0) / times.length,
          p95Ms: sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))]!,
          maxMs: sorted[sorted.length - 1]!,
          drawCalls: Math.round(info.render.calls / frames),
          triangles: Math.round(info.render.triangles / frames),
          geometries: info.memory.geometries,
          textures: info.memory.textures,
        };
      },
      nonBlank() {
        gl.render(scene, cam);
        const c = gl.domElement;
        const w = c.width;
        const h = c.height;
        const ctx2 = gl.getContext() as WebGL2RenderingContext;
        const px = new Uint8Array(w * h * 4);
        ctx2.readPixels(0, 0, w, h, ctx2.RGBA, ctx2.UNSIGNED_BYTE, px);
        let different = 0;
        const r0 = px[0]!;
        const g0 = px[1]!;
        const b0 = px[2]!;
        const a0 = px[3]!;
        for (let i = 0; i < px.length; i += 16) {
          if (px[i] !== r0 || px[i + 1] !== g0 || px[i + 2] !== b0 || px[i + 3] !== a0) different += 1;
        }
        return { total: Math.floor(px.length / 16), different };
      },
    };
    return () => {
      delete window.__fieldlensSceneProbe;
    };
  }, [gl, scene, camera, ctl]);

  const labelCache = useRef<{ anchors: Anchor[]; els: Map<string, HTMLElement>; sizes: Map<string, { w: number; h: number }>; lines: Map<string, SVGLineElement>; version: string | undefined } | null>(null);
  const tmp = useMemo(() => new THREE.Vector3(), []);

  useFrame((_, delta) => {
    const cam = camera as THREE.PerspectiveCamera;
    // Camera flights and the fly-over tour (refs only, no React state per frame).
    if (ctl !== null) {
      const flown = rig.step(delta);
      if (flown !== null) {
        cam.position.set(...flown.position);
        ctl.target.set(...flown.target);
        ctl.update();
        invalidate();
      } else if (hold.current) {
        hold.current = false;
      }
      const p = tour.current;
      if (p !== null && p.state === "playing" && !hold.current && flown === null) {
        const f = p.advance(delta);
        if (f.pose !== null && (f.phase !== "dwell" || f.stopChanged || !p.plan.stops.length)) {
          const pos: V3 = [f.pose.target[0] + f.pose.dir[0] * f.pose.range, f.pose.target[1] + f.pose.dir[1] * f.pose.range, f.pose.target[2] + f.pose.dir[2] * f.pose.range];
          cam.position.set(...pos);
          ctl.target.set(...f.pose.target);
          ctl.update();
        }
        if (f.stopChanged) publish(p.status());
        if (f.fitAllNow) {
          tourFit.current?.();
          statusRef.current?.({ ...p.status(), announcement: "Fly-over: fitting the whole well." });
        }
        if (f.finished) publish(p.status());
        invalidate();
      } else if (p !== null && p.state === "playing") {
        invalidate();
      }
    }
    // Clip planes and fog follow the orbit distance (depth cue; keeps near detail at 3 km depth).
    const dist = ctl === null ? cam.position.length() : cam.position.distanceTo(ctl.target);
    const near = Math.min(Math.max(dist * 0.01, 0.05), 100);
    if (Math.abs(near - lastNear.current) / near > 0.02) {
      lastNear.current = near;
      cam.near = near;
      cam.far = Math.max(dist * 12, 8000) + built.bounds.getSize(tmp).length() * 3;
      cam.updateProjectionMatrix();
    }
    if (scene.fog instanceof THREE.Fog) {
      scene.fog.near = dist * 0.9;
      scene.fog.far = dist * 3 + built.bounds.getSize(tmp).length() * 0.35;
    }
    // Labels.
    const layer = layerRef.current;
    if (layer === null) return;
    let cache = labelCache.current;
    if (cache === null || cache.version !== layer.dataset["version"] || cache.anchors !== anchorsRef.current) {
      const els = new Map<string, HTMLElement>();
      const sizes = new Map<string, { w: number; h: number }>();
      const lines = new Map<string, SVGLineElement>();
      layer.querySelectorAll<HTMLElement>("[data-label-id]").forEach((el) => {
        const id = el.dataset["labelId"]!;
        els.set(id, el);
        const r = el.getBoundingClientRect();
        sizes.set(id, { w: r.width, h: r.height });
      });
      layer.querySelectorAll<SVGLineElement>("[data-line-id]").forEach((l) => lines.set(l.dataset["lineId"]!, l));
      cache = { anchors: anchorsRef.current, els, sizes, lines, version: layer.dataset["version"] };
      labelCache.current = cache;
    }
    const mode = labelModeRef.current;
    const sel = selectedRef.current;
    const inputs: LabelInput[] = [];
    for (const an of cache.anchors) {
      const sz = cache.sizes.get(an.id) ?? { w: 120, h: 22 };
      tmp.copy(an.position).project(cam);
      const visible = tmp.z < 1 && tmp.z > -1 && (mode === "all" ? true : mode === "selected" ? an.id === sel : false);
      inputs.push({
        id: an.id,
        x: ((tmp.x + 1) / 2) * size.width,
        y: ((1 - tmp.y) / 2) * size.height,
        visible: an.id === sel ? tmp.z < 1 : visible && (an.kind !== "depth" || an.id === sel || mode === "all"),
        w: sz.w,
        h: sz.h,
        priority: an.id === sel ? -1 : an.priority,
      });
    }
    const placed = layoutLabels(inputs, { w: size.width, h: size.height });
    placed.forEach((p, i) => {
      const el = cache.els.get(p.id);
      if (el === undefined) return;
      el.style.visibility = p.shown ? "visible" : "hidden";
      if (p.shown) el.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px)`;
      const line = cache.lines.get(p.id);
      if (line !== undefined) {
        const inp = inputs[i]!;
        const sz = cache.sizes.get(p.id) ?? { w: 120, h: 22 };
        if (p.shown && p.leader) {
          const lx = p.x > inp.x ? p.x : p.x + sz.w;
          line.setAttribute("x1", inp.x.toFixed(1));
          line.setAttribute("y1", inp.y.toFixed(1));
          line.setAttribute("x2", lx.toFixed(1));
          line.setAttribute("y2", (p.y + sz.h / 2).toFixed(1));
          line.style.visibility = "visible";
        } else {
          line.style.visibility = "hidden";
        }
      }
    });
  });

  const onClick = (e: ThreeEvent<MouseEvent>) => {
    const id = idOf(e.object);
    if (id === null) return;
    e.stopPropagation();
    onSelect(id);
  };
  const onOver = (e: ThreeEvent<PointerEvent>) => {
    if (idOf(e.object) !== null) {
      e.stopPropagation();
      gl.domElement.style.cursor = "pointer";
    }
  };
  const onOut = () => {
    gl.domElement.style.cursor = "";
  };

  return (
    <>
      <Environment />
      <hemisphereLight args={[0xdfe9ff, 0x1a2436, 0.55]} />
      <directionalLight position={[60, 120, 80]} intensity={1.7} color={0xfff2e0} />
      <directionalLight position={[-80, 40, -60]} intensity={0.55} color={0x9db8ff} />
      <Ground model={model} />
      <primitive object={built.root} onClick={onClick} onPointerOver={onOver} onPointerOut={onOut} />
      <OrbitControls makeDefault enableDamping dampingFactor={0.14} zoomToCursor screenSpacePanning minDistance={1.5} maxDistance={200000} keyEvents />
    </>
  );
}

// ------------------------------------------------------------------ DOM overlay + Canvas

export default function Viewer3D(props: Props) {
  const { options, selectedId, onSelect } = props;
  const [anchors, setAnchors] = useState<Anchor[]>([]);
  const anchorsRef = useRef<Anchor[]>([]);
  const layerRef = useRef<HTMLDivElement | null>(null);
  const labelModeRef = useRef<LabelMode>(options.labels);
  const selectedRef = useRef<string | null>(selectedId);
  const [lost, setLost] = useState(false);

  // Explore command bus: handlers read the latest props through a ref inside the hook. Without a
  // `wellboreId` the viewer cannot tell which wellbore a command targets, so it refuses them (S-2).
  const { commands, model, wellboreId } = props;
  const mine = (id: string): boolean => wellboreId !== undefined && id === wellboreId;
  const layerCtx = useMemo<SceneLayerContext>(
    () => ({ scope: "wellbore", origin: RENDER_ORIGIN, exaggeration: options.exaggeration, cutaway: options.cutaway }),
    [options.exaggeration, options.cutaway],
  );
  useExploreCommandHandlers({
    focusWellbore: (p) => {
      if (!mine(p.wellboreId)) return false;
      if (commands.current === null) return "defer";
      commands.current.fitAll();
      return true;
    },
    focusElement: (p) => {
      if (!mine(p.wellboreId) || !model.byId.has(p.elementId)) return false;
      if (commands.current === null) return "defer";
      commands.current.focus(p.elementId);
      return true;
    },
    flyOver: (p) => {
      if (!mine(p.wellboreId)) return false;
      if (commands.current === null) return "defer";
      return commands.current.flyOver();
    },
    stopFlyOver: () => commands.current?.stopFlyOver() ?? false,
    ...(props.resolveFormationFocus === undefined
      ? {}
      : { focusFormation: makeFocusFormationHandler({ accepts: mine, resolve: props.resolveFormationFocus, ctx: layerCtx, commands }) }),
  });

  useEffect(() => {
    labelModeRef.current = options.labels;
    selectedRef.current = selectedId;
    invalidate();
  }, [options.labels, selectedId]);

  const domVersion = useRef(0);
  useEffect(() => {
    if (layerRef.current !== null) layerRef.current.dataset["version"] = String((domVersion.current += 1));
    invalidate();
  }, [anchors]);

  const onAnchors = useMemo(
    () => (a: Anchor[]) => {
      anchorsRef.current = a;
      setAnchors(a);
    },
    [],
  );

  return (
    <div className={styles.canvasWrap} data-testid="scene-canvas-wrap">
      <Canvas
        frameloop="demand"
        dpr={[1, 2]}
        camera={{ fov: 38, near: 0.1, far: 30000, position: [200, 100, 200] }}
        gl={{ antialias: true, powerPreference: "high-performance", alpha: true }}
        tabIndex={0}
        role="group"
        aria-label="3D view of the wellbore equipment. Use the component list to select items by keyboard."
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
        onPointerMissed={() => onSelect(null)}
        className={styles.canvas}
        data-testid="scene-canvas"
      >
        <SceneContents {...props} onAnchors={onAnchors} anchorsRef={anchorsRef} layerRef={layerRef} labelModeRef={labelModeRef} selectedRef={selectedRef} />
        {renderLayers(props.layers, layerCtx)}
      </Canvas>
      <div className={styles.labelLayer} ref={layerRef} aria-hidden="true" data-testid="scene-label-layer">
        <svg className={styles.leaders}>
          {anchors.map((a) => (
            <line key={a.id} data-line-id={a.id} className={styles.leader} />
          ))}
        </svg>
        {anchors.map((a) => (
          <button
            key={a.id}
            type="button"
            tabIndex={-1}
            data-label-id={a.id}
            data-testid={`scene-label-${a.id}`}
            data-kind={a.kind}
            data-selected={a.id === selectedId}
            className={`${styles.label} ${a.kind === "depth" ? styles.labelDepth : ""} ${a.kind === "area" ? styles.labelArea : ""}`}
            onClick={() => a.kind === "element" && onSelect(a.id)}
          >
            {a.text}
            {a.kind === "element" && a.illustrative && <span className={styles.labelTag}> · illustrative</span>}
          </button>
        ))}
      </div>
      {lost && (
        <p className={styles.lost} role="alert">
          The graphics context was lost. Reload the view from the toolbar; the component list still works.
        </p>
      )}
    </div>
  );
}
