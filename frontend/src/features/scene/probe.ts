import * as THREE from "three";
import type { ViewerProbe } from "./Viewer3D";

/**
 * Profiling/test probe shared by viewers that render with a plain camera orbit: frame timings and
 * renderer counters for AG-8. Registered only when the page sets `__FIELDLENS_SCENE_PROBE__`.
 */
export function createViewerProbe(gl: THREE.WebGLRenderer, scene: THREE.Scene, cam: THREE.PerspectiveCamera, target: () => THREE.Vector3): ViewerProbe {
  return {
    measure(frames) {
      const times: number[] = [];
      const gl2 = gl.getContext();
      const base = cam.position.clone();
      const tgt = target().clone();
      gl.info.reset();
      const autoReset = gl.info.autoReset;
      gl.info.autoReset = false;
      for (let i = 0; i < frames; i += 1) {
        const off = base.clone().sub(tgt).applyAxisAngle(new THREE.Vector3(0, 1, 0), (i / frames) * Math.PI * 2);
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
      const ctx = gl.getContext() as WebGL2RenderingContext;
      const px = new Uint8Array(c.width * c.height * 4);
      ctx.readPixels(0, 0, c.width, c.height, ctx.RGBA, ctx.UNSIGNED_BYTE, px);
      let different = 0;
      for (let i = 0; i < px.length; i += 16) {
        if (px[i] !== px[0] || px[i + 1] !== px[1] || px[i + 2] !== px[2] || px[i + 3] !== px[3]) different += 1;
      }
      return { total: Math.floor(px.length / 16), different };
    },
  };
}
