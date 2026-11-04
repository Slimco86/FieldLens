export type EchartsRuntime = typeof import("./echartsRuntime");

let pending: Promise<EchartsRuntime> | null = null;

/** Lazy, cached load of the chart chunk. A failed load is retried on the next call. */
export function loadEcharts(): Promise<EchartsRuntime> {
  pending ??= import("./echartsRuntime").catch((e: unknown) => {
    pending = null;
    throw e;
  });
  return pending;
}
