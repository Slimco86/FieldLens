/** True when the browser can create a WebGL2 context (the only path the viewer supports). */
let cached: boolean | null = null;
export function webgl2Available(): boolean {
  if (cached !== null) return cached;
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2");
    // Release the probe context immediately so it does not count against the page's context budget.
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
    cached = gl !== null;
  } catch {
    cached = false;
  }
  return cached;
}
