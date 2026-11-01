import { useCallback, useEffect, useRef, useState } from "react";
import { Title } from "@mantine/core";
import { CircleCheck } from "lucide-react";
import { ApiError, fetchReadiness, type ReadinessResponse } from "../api/client";
import { ErrorState, LoadingState } from "../design";
import { ProjectSidebar } from "../features/projects/ProjectSidebar";
import { ProjectWorkspace } from "../features/projects/ProjectWorkspace";
import { Shell } from "./shell/Shell";
import styles from "./shell/Shell.module.css";

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

  const ready = state.kind === "ready";
  return (
    <Shell
      mainRef={main}
      title={ready ? "Workspace" : undefined}
      busy={state.kind === "loading"}
      sidebar={ready ? <ProjectSidebar /> : undefined}
      status={
        ready ? (
          <p role="status" className={styles.ready}>
            <CircleCheck size={14} aria-hidden="true" />
            Local services ready.
          </p>
        ) : undefined
      }
    >
      {state.kind === "loading" && <LoadingState label="Checking local services…" status />}
      {state.kind === "unavailable" && (
        <section aria-labelledby="unavailable-title">
          <Title order={3} id="unavailable-title" mb="md">
            Local services unavailable
          </Title>
          <ErrorState
            message={state.message}
            requestId={state.requestId}
            onRetry={() => {
              main.current?.focus();
              check();
            }}
          />
        </section>
      )}
      {ready && <ProjectWorkspace />}
    </Shell>
  );
}
