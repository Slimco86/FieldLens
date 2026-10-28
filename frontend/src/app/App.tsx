import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchReadiness, type ReadinessResponse } from "../api/client";

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: ReadinessResponse }
  | { kind: "unavailable"; message: string; requestId: string | null };

export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const controller = useRef<AbortController | null>(null);
  const main = useRef<HTMLElement | null>(null);

  const check = useCallback(() => {
    controller.current?.abort();
    const ctl = new AbortController();
    controller.current = ctl;
    setState({ kind: "loading" });
    fetchReadiness(ctl.signal).then(
      (data) => {
        if (!ctl.signal.aborted) setState({ kind: "ready", data });
      },
      (err: unknown) => {
        if (ctl.signal.aborted) return;
        if (err instanceof ApiError) {
          setState({ kind: "unavailable", message: err.message, requestId: err.requestId });
        } else {
          setState({ kind: "unavailable", message: "The local API is unreachable.", requestId: null });
        }
      },
    );
  }, []);

  useEffect(() => {
    check();
    return () => controller.current?.abort();
  }, [check]);

  return (
    <>
      <a className="skip" href="#main">
        Skip to main content
      </a>
      <header>
        <h1>FieldLens</h1>
      </header>
      <main ref={main} id="main" tabIndex={-1} aria-busy={state.kind === "loading"}>
        {state.kind === "loading" && (
          <p role="status">Checking local services…</p>
        )}
        {state.kind === "unavailable" && (
          <section role="alert" aria-labelledby="unavailable-title">
            <h2 id="unavailable-title">Local services unavailable</h2>
            <p>{state.message}</p>
            {state.requestId && <p>Request ID: {state.requestId}</p>}
            <button type="button" onClick={() => { main.current?.focus(); check(); }}>
              Retry
            </button>
          </section>
        )}
        {state.kind === "ready" && (
          <section aria-labelledby="workspace-title">
            <h2 id="workspace-title">Workspace</h2>
            <p role="status">Local services ready.</p>
            <p>No project is open yet. Import sources to begin.</p>
          </section>
        )}
      </main>
    </>
  );
}
