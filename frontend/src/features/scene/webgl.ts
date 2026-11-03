/** True when the browser can create a WebGL2 context (the only path the viewer supports). */
export function webgl2Available(): boolean {
  try {
    const c = document.createElement("canvas");
    return c.getContext("webgl2") !== null;
  } catch {
    return false;
  }
}
