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
  fitUnlocated(): void;
  focus(id: string): void;
  zoom(factor: number): void;
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

function buildAssets(model: SceneModel, options: ViewerOptions): BuiltAssets {
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

  model.elements.forEach((el, index) => {
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

  if (model.tray !== null) {
    const t = model.tray;
    const hx = t.halfX;
    const hz = t.halfZ;
    const plate = new THREE.Mesh(
      lib.track(new THREE.PlaneGeometry(hx * 2, hz * 2)),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(scenePalette.trayFill), transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false }),
    );
    plate.rotation.x = -Math.PI / 2;
    plate.position.set(t.center[0], 0.06, t.center[2]);
    plate.name = "tray";
    const edge = new THREE.LineLoop(
      lib.track(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-hx, 0, -hz), new THREE.Vector3(hx, 0, -hz), new THREE.Vector3(hx, 0, hz), new THREE.Vector3(-hx, 0, hz)])),
      new THREE.LineBasicMaterial({ color: new THREE.Color(scenePalette.trayEdge) }),
    );
    edge.position.set(t.center[0], 0.08, t.center[2]);
    root.add(plate, edge);
    lib.own(plate.material as THREE.Material);
    lib.own(edge.material as THREE.Material);
    anchors.push({
      id: "tray",
      text: "Unlocated components — not placed in the well (sizes illustrative)",
      position: new THREE.Vector3(t.center[0], 0.2, t.center[2] + hz),
      priority: 2,
      kind: "area",
      illustrative: true,
    });
    const tb = new THREE.Box3().setFromObject(plate);
    bounds.union(tb);
  }
  root.updateMatrixWorld(true);
  return { root, lib, anchors, bounds };
}

const WELLHEAD_VIEW_DEPTH_M = 45;

interface ViewTarget {
  center: THREE.Vector3;
  radius: number;
  keepDirection: boolean;
}

function SceneContents({ model, options, selectedId, onSelect, commands, onAnchors, anchorsRef, layerRef, labelModeRef, selectedRef }: Props & {
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
  const anim = useRef<{ t: number; dur: number; fromPos: THREE.Vector3; toPos: THREE.Vector3; fromTarget: THREE.Vector3; toTarget: THREE.Vector3 } | null>(null);
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

  const frame = useMemo(
    () => ({
      go(t: ViewTarget) {
        if (ctl === null) return;
        const cam = camera as THREE.PerspectiveCamera;
        const dir = t.keepDirection ? cam.position.clone().sub(ctl.target).normalize() : DEFAULT_DIR.clone();
        const fov = (cam.fov * Math.PI) / 180;
        const aspect = size.width / Math.max(1, size.height);
        const fit = Math.max(1, 1 / Math.min(1, aspect));
        const dist = Math.max(2.5, (t.radius / Math.sin(fov / 2)) * 1.15 * Math.min(fit, 1.6));
        const toPos = t.center.clone().add(dir.multiplyScalar(dist));
        if (reducedMotion() || first.current) {
          cam.position.copy(toPos);
          ctl.target.copy(t.center);
          ctl.update();
          first.current = false;
          invalidate();
          return;
        }
        anim.current = { t: 0, dur: 0.75, fromPos: cam.position.clone(), toPos, fromTarget: ctl.target.clone(), toTarget: t.center.clone() };
        invalidate();
      },
    }),
    [camera, ctl, size.width, size.height],
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
    commands.current = {
      fitAll: () => frame.go(sphereOf(built.bounds)),
      fitWellhead: () => {
        const b = boundsOf((e) => e.zone === "surface" || e.kind === "wellhead" || e.kind === "christmas_tree");
        if (b.isEmpty()) b.set(new THREE.Vector3(-10, 0, -10), new THREE.Vector3(10, 6, 10));
        // Include the top of the hole so the first cased metres are in view.
        b.expandByPoint(new THREE.Vector3(0, -WELLHEAD_VIEW_DEPTH_M, 0));
        frame.go({ ...sphereOf(b), keepDirection: false });
      },
      fitUnlocated: () => {
        const b = boundsOf((e) => e.zone === "unlocated");
        if (!b.isEmpty()) frame.go(sphereOf(b));
      },
      focus: (id) => {
        const el = model.byId.get(id);
        const g = built.root.children.find((c) => c.userData["elementId"] === id);
        if (g === undefined || el === undefined) return;
        const b = elementBounds(g);
        const t = sphereOf(b);
        // Long tubes: frame a window of the pipe, not its whole length.
        if (el.mdTopM !== null && el.mdBottomM !== null && (el.kind === "casing" || el.kind === "liner" || el.kind === "tubing" || el.kind === "perforation_interval")) {
          const mid = model.path.at((el.mdTopM + el.mdBottomM) / 2).position;
          t.center = new THREE.Vector3(...mid);
          t.radius = Math.min(t.radius, Math.max(el.outerRadiusM * options.exaggeration * 4, 30));
        }
        frame.go({ ...t, keepDirection: true });
      },
      zoom: (factor) => {
        if (ctl === null) return;
        const cam = camera as THREE.PerspectiveCamera;
        const off = cam.position.clone().sub(ctl.target).multiplyScalar(factor);
        const toPos = ctl.target.clone().add(off);
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
  }, [built, model, commands, frame, camera, ctl, options.exaggeration]);

  // Initial framing once the controls exist, and whenever a new model is loaded.
  useEffect(() => {
    if (ctl === null) return;
    first.current = true;
    commands.current?.fitWellhead();
  }, [model.path, ctl, commands]);

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
    // Fly animation: ease the camera and the orbit target (refs only, no React state).
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
