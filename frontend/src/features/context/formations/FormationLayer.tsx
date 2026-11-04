import { Html } from "@react-three/drei";
import { useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore } from "react";
import * as THREE from "three";
import { formationChipLineStyle, formationChipMutedStyle, formationChipStyle, formationHotColor } from "../../../design/formationPalette";
import type { SceneLayerContext } from "../../scene/sceneLayers";
import {
  buildFormationScene,
  markerRadius,
  MARKER_SHAPES,
  pickLabels,
  planeOpacity,
  type LabelItem,
  type MarkerPlacement,
  type MarkerShape,
} from "./formationModel";
import { isSurfaceShown, type FormationStore } from "./formationStore";
import type { FormationLayerSet } from "./formationTypes";

/*
 * Formation layer (TASK-098): T1 pick markers on the wellbore and T2 level planes, rendered inside the viewer's Canvas
 * through the `layers` slot. Everything drawable is derived by the pure `buildFormationScene`; this file only owns GPU
 * resources. Pointer events and store updates are discrete (no per-frame React state); the demand frame loop is
 * invalidated when anything visible changes. Planes are physical-scale: only marker size follows the exaggeration
 * display factor, never plane elevation, footprint or any depth.
 */

export interface FormationLayerProps {
  ctx: SceneLayerContext;
  data: FormationLayerSet | null;
  store: FormationStore;
}

const RENDER_ORDER_PLANE = 10;
const RENDER_ORDER_OUTLINE = 60;
const RENDER_ORDER_MARKER = 100;

function makeMarkerGeometries(): Record<MarkerShape, THREE.BufferGeometry> {
  return {
    sphere: new THREE.SphereGeometry(1, 14, 10),
    diamond: new THREE.OctahedronGeometry(1.25),
    box: new THREE.BoxGeometry(1.6, 1.6, 1.6),
    cone: new THREE.ConeGeometry(1.2, 2.4, 14),
  };
}

export function FormationLayer({ ctx, data, store }: FormationLayerProps) {
  const opts = useSyncExternalStore(store.subscribe, store.getState, store.getState);
  const invalidate = useThree((s) => s.invalidate);
  const [ox, oy, oz] = ctx.origin;
  const scene = useMemo(() => buildFormationScene(data, { origin: [ox, oy, oz] }), [data, ox, oy, oz]);

  const geometries = useMemo(makeMarkerGeometries, []);
  const markerMaterial = useMemo(() => new THREE.MeshBasicMaterial({ toneMapped: false }), []);
  const fillGeometry = useMemo(() => new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), []);
  useEffect(
    () => () => {
      for (const g of Object.values(geometries)) g.dispose();
      markerMaterial.dispose();
      fillGeometry.dispose();
    },
    [geometries, markerMaterial, fillGeometry],
  );

  // Per-plane resources: rebuilt only when the plane set changes, disposed when it does.
  const planeResources = useMemo(
    () =>
      scene.planes.map((p) => {
        const hw = p.width / 2;
        const hd = p.depth / 2;
        const outline = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(-hw, 0, -hd),
          new THREE.Vector3(hw, 0, -hd),
          new THREE.Vector3(hw, 0, hd),
          new THREE.Vector3(-hw, 0, hd),
        ]);
        const fill = new THREE.MeshBasicMaterial({ color: p.color, transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
        const dash = Math.max(4, Math.min(p.width, p.depth) / 30);
        const line = new THREE.LineDashedMaterial({ color: p.color, dashSize: dash, gapSize: dash * 0.6, transparent: true, depthWrite: false, toneMapped: false });
        return { outline, fill, line };
      }),
    [scene.planes],
  );
  useEffect(
    () => () => {
      for (const r of planeResources) {
        r.outline.dispose();
        r.fill.dispose();
        r.line.dispose();
      }
    },
    [planeResources],
  );

  const shown = (key: string) => isSurfaceShown(opts, key);
  const markers = useMemo(() => scene.markers.filter((m) => isSurfaceShown(opts, m.surfaceKey)), [scene.markers, opts]);
  const byShape = useMemo(() => {
    const g: Record<MarkerShape, MarkerPlacement[]> = { sphere: [], diamond: [], box: [], cone: [] };
    for (const m of markers) g[m.shape].push(m);
    return g;
  }, [markers]);
  const radius = markerRadius(ctx.exaggeration);

  useLayoutEffect(() => {
    scene.planes.forEach((p, i) => {
      const r = planeResources[i];
      if (!r) return;
      const selected = opts.selectedId === p.id || opts.hoverId === p.id;
      r.fill.opacity = Math.min(0.9, planeOpacity(opts.planeOpacity, ctx.cutaway) * (selected ? 1.6 : 1));
      r.line.opacity = ctx.cutaway ? 1 : 0.9;
      r.outline.computeBoundingSphere();
    });
    invalidate();
  }, [scene.planes, planeResources, opts, ctx.cutaway, invalidate]);

  const labels = useMemo(() => pickLabels(markers, scene.planes.filter((p) => isSurfaceShown(opts, p.surfaceKey)), opts.labelMode, opts.selectedId, opts.hoverId), [markers, scene.planes, opts]);

  if (data === null || !opts.visible) return null;
  return (
    <group name="formation-layer" userData={{ layer: "formations", planesScale: "physical", markerExaggeration: ctx.exaggeration }}>
      {scene.planes.map((p, i) => {
        const r = planeResources[i];
        if (!r || !shown(p.surfaceKey)) return null;
        return (
          <group key={p.id} position={p.center as unknown as THREE.Vector3Tuple}>
            {/* Not pickable: a large translucent plane must never steal clicks from the wellbore; select via its label chip or the legend. */}
            <mesh geometry={fillGeometry} material={r.fill} scale={[p.width, 1, p.depth]} renderOrder={RENDER_ORDER_PLANE + i} raycast={() => null} />
            <lineLoop
              geometry={r.outline}
              material={r.line}
              renderOrder={RENDER_ORDER_OUTLINE + i}
              raycast={() => null}
              onUpdate={(l) => l.computeLineDistances()}
            />
          </group>
        );
      })}
      {MARKER_SHAPES.map((shape) => {
        const items = byShape[shape];
        if (items.length === 0) return null;
        return <MarkerGroup key={`${shape}:${items.length}`} items={items} geometry={geometries[shape]} material={markerMaterial} radius={radius} store={store} selectedId={opts.selectedId} hoverId={opts.hoverId} />;
      })}
      {labels.map((l) => (
        <Html key={l.id} position={l.position as unknown as THREE.Vector3Tuple} zIndexRange={[30, 0]} style={{ pointerEvents: "none" }}>
          <LabelChip item={l} store={store} />
        </Html>
      ))}
    </group>
  );
}

interface MarkerGroupProps {
  items: MarkerPlacement[];
  geometry: THREE.BufferGeometry;
  material: THREE.Material;
  radius: number;
  store: FormationStore;
  selectedId: string | null;
  hoverId: string | null;
}

function MarkerGroup({ items, geometry, material, radius, store, selectedId, hoverId }: MarkerGroupProps) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const invalidate = useThree((s) => s.invalidate);
  useLayoutEffect(() => {
    const m = ref.current;
    if (!m) return;
    const dummy = new THREE.Object3D();
    const c = new THREE.Color();
    const white = new THREE.Color(formationHotColor);
    items.forEach((it, i) => {
      const hot = it.id === selectedId || it.id === hoverId;
      dummy.position.set(it.position[0], it.position[1], it.position[2]);
      dummy.scale.setScalar(radius * (hot ? 1.5 : 1));
      dummy.updateMatrix();
      m.setMatrixAt(i, dummy.matrix);
      c.set(it.color);
      if (hot) c.lerp(white, 0.45);
      m.setColorAt(i, c);
    });
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    m.computeBoundingSphere();
    invalidate();
  }, [items, radius, selectedId, hoverId, invalidate]);
  const idOf = (e: ThreeEvent<PointerEvent | MouseEvent>) => (e.instanceId === undefined ? undefined : items[e.instanceId]?.id);
  return (
    <instancedMesh
      ref={ref}
      args={[geometry, material, items.length]}
      renderOrder={RENDER_ORDER_MARKER}
      onPointerOver={(e) => {
        const id = idOf(e);
        if (id !== undefined) {
          e.stopPropagation();
          store.hover(id);
        }
      }}
      onPointerOut={() => store.hover(null)}
      onClick={(e) => {
        const id = idOf(e);
        if (id !== undefined) {
          e.stopPropagation();
          store.select(id);
        }
      }}
    />
  );
}

function LabelChip({ item, store }: { item: LabelItem; store: FormationStore }) {
  const [first, ...rest] = item.lines;
  return (
    <button type="button" style={formationChipStyle(item.selected)} onClick={() => store.select(item.id)} aria-label={item.lines.join(". ")}>
      <span style={formationChipLineStyle(item.kind === "plane" || item.selected)}>{first}</span>
      {rest.map((r) => (
        <span key={r} style={formationChipMutedStyle}>
          {r}
        </span>
      ))}
    </button>
  );
}
