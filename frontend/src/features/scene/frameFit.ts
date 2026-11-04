import * as THREE from "three";

/**
 * Camera-fit helpers (UX-1). Fits use ONLY wellbore/equipment/field-layout bounds; objects of the
 * `layers` slot (formation planes and markers are huge and deep) are flagged `userData.fitIgnore`
 * and are skipped by `boundsExcludingLayers`, so they can never move the camera framing.
 */

/** Flag set on the root group of any `layers` content to keep it out of fit/bounds computations. */
export const FIT_IGNORE_KEY = "fitIgnore";

/** Box of `root` and its descendants, skipping any subtree whose root has `userData.fitIgnore`. */
export function boundsExcludingLayers(root: THREE.Object3D): THREE.Box3 {
  const box = new THREE.Box3();
  root.updateWorldMatrix(true, true);
  const add = (o: THREE.Object3D): void => {
    if (o.userData[FIT_IGNORE_KEY] === true) return;
    const mesh = o as THREE.Mesh;
    if (mesh.geometry !== undefined) {
      const g = mesh.geometry;
      if (g.boundingBox === null) g.computeBoundingBox();
      if (g.boundingBox !== null) box.union(g.boundingBox.clone().applyMatrix4(o.matrixWorld));
    }
    for (const c of o.children) add(c);
  };
  add(root);
  return box;
}

/** Orbit distance that frames a sphere; clamps the narrow-aspect widening and ignores a 0-sized canvas. */
export function fitDistance(radius: number, fovDeg: number, width: number, height: number, margin: number): number {
  const fov = (fovDeg * Math.PI) / 180;
  const aspect = width > 0 && height > 0 ? width / height : 1;
  const fit = Math.max(1, 1 / Math.min(1, aspect));
  return Math.max(2.5, (radius / Math.sin(fov / 2)) * margin * Math.min(fit, 1.6));
}

/** True when the framing should be recomputed after a plan/data change: only before the user moved the camera. */
export function shouldAutoFit(userMoved: boolean, controlsReady: boolean): boolean {
  return controlsReady && !userMoved;
}
