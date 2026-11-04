import type { MutableRefObject } from "react";
import type { SceneLayerContext } from "./sceneLayers";

/** Pose the camera should frame for a formation (render space, metres). */
export interface FormationPose {
  target: readonly [number, number, number];
  radius: number;
}

export type ResolveFormationFocus = (wellboreId: string, formationId: string, ctx: SceneLayerContext) => FormationPose | null;

interface PointCommands {
  focusPoint(target: readonly [number, number, number], radius: number): void;
}

/**
 * Camera-side `focusFormation` handler shared by both viewers (CM-1 + FO-6). Refuses (false, no motion) when the
 * wellbore is not this viewer's or the pose cannot be resolved (unknown/other-wellbore/unplaceable formation); defers
 * while the imperative commands are not set up; otherwise frames the formation and acts.
 */
export function makeFocusFormationHandler(opts: {
  accepts: (wellboreId: string) => boolean;
  resolve: ResolveFormationFocus;
  ctx: SceneLayerContext;
  commands: MutableRefObject<PointCommands | null>;
}): (p: { wellboreId: string; formationId: string }) => boolean | "defer" {
  return (p) => {
    if (!opts.accepts(p.wellboreId)) return false;
    const pose = opts.resolve(p.wellboreId, p.formationId, opts.ctx);
    if (pose === null) return false;
    if (opts.commands.current === null) return "defer";
    opts.commands.current.focusPoint(pose.target, pose.radius);
    return true;
  };
}
