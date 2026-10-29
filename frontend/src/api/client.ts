import type { components } from "./generated";

export type ReadinessResponse = components["schemas"]["ReadinessResponse"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly requestId: string | null;
  /** Sanitized server details (e.g. `reason`, `limit`); never trusted as engineering evidence. */
  readonly details: Record<string, unknown> | null;
  constructor(
    status: number,
    code: string | null,
    message: string,
    requestId: string | null,
    details: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.details = details;
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export async function toApiError(res: Response): Promise<ApiError> {
  let code: string | null = null;
  let message = `Request failed (${res.status})`;
  let requestId: string | null = res.headers.get("x-request-id");
  let details: Record<string, unknown> | null = null;
  try {
    const body = (await res.json()) as Partial<ErrorEnvelope>;
    const err = body.error as
      | { code?: string; message?: string; request_id?: string; details?: Record<string, unknown> | null }
      | undefined;
    code = err?.code ?? null;
    message = err?.message ?? message;
    requestId = err?.request_id ?? requestId;
    details = err?.details ?? null;
  } catch {
    /* non-JSON body */
  }
  return new ApiError(res.status, code, message, requestId, details);
}

/** Readiness: 200 => ready; anything else (incl. network failure) rejects. */
export async function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  const res = await fetch("/ready", { signal, headers: { accept: "application/json" } });
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as ReadinessResponse;
}

let token: string | null = null;

async function bootstrap(): Promise<string> {
  const res = await fetch("/api/v1/session", { cache: "no-store" });
  if (!res.ok) throw await toApiError(res);
  token = ((await res.json()) as { csrf_token: string }).csrf_token;
  return token;
}

/** The in-memory session token for guarded requests that cannot use fetch (XHR upload). */
export async function sessionToken(): Promise<string> {
  return token ?? (await bootstrap());
}

/** Forget the token after the server rejected it; the next guarded call re-bootstraps. */
export function discardSessionToken(): void {
  token = null;
}

/**
 * Guarded mutation. The token lives in memory only. On SESSION_TOKEN_INVALID the token is
 * re-bootstrapped but the mutation is NOT replayed; the caller must decide to retry.
 */
export async function mutate(
  path: string,
  init: { method: string; body?: unknown; signal?: AbortSignal },
): Promise<Response> {
  const current = token ?? (await bootstrap());
  const res = await fetch(path, {
    method: init.method,
    headers: { "content-type": "application/json", "x-fieldlens-token": current },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    signal: init.signal,
  });
  if (res.ok) return res;
  const err = await toApiError(res);
  if (err.code === "SESSION_TOKEN_INVALID") {
    token = null;
    await bootstrap();
  }
  throw err;
}

/** Guarded JSON read: a non-2xx answer or an unreadable body rejects; nothing is defaulted. */
export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal, headers: { accept: "application/json" } });
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

export async function sendJson<T>(
  path: string,
  method: "POST" | "PATCH",
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const res = await mutate(path, { method, body, signal });
  return (await res.json()) as T;
}
