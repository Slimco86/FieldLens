import type { ReactNode } from "react";

/**
 * `layers` slot contract (TASK-095). Later lanes (formations, charts links, camera) mount scene
 * content inside the Canvas through this slot without editing the viewers' internals.
 *
 * - `origin` is the local render origin in render coordinates (metres, +y up, depth negative).
 *   Engineering results stay double precision outside the renderer; layers subtract this origin
 *   before converting to float32. Wellbore view: the wellhead, `[0, 0, 0]`. Field view: the
 *   field frame origin, `[0, 0, 0]`; wells are positioned relative to it (`FieldPlan`).
 * - `exaggeration` is the display radius factor of the wellbore view; `null` in the field view,
 *   where widths are per-well and illustrative.
 * - `cutaway` mirrors the equipment cutaway state.
 * Values are stable references per change; layers must not store them in per-frame React state.
 */
export interface SceneLayerContext {
  scope: "wellbore" | "field";
  origin: readonly [number, number, number];
  exaggeration: number | null;
  cutaway: boolean;
}

export type SceneLayers = ReactNode | ((ctx: SceneLayerContext) => ReactNode);

export const RENDER_ORIGIN: SceneLayerContext["origin"] = Object.freeze([0, 0, 0]) as unknown as SceneLayerContext["origin"];

export function renderLayers(layers: SceneLayers | undefined, ctx: SceneLayerContext): ReactNode {
  if (layers === undefined || layers === null) return null;
  return typeof layers === "function" ? layers(ctx) : layers;
}
