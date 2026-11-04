import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChartBlock } from "../charts";
import { ExploreCommandsProvider } from "../scene/ExploreCommandsContext";
import type { ExploreCommand, ExploreCommandBus, ExploreCommandOutcome } from "../scene/exploreCommands";
import type { Section } from "../projects/keys";
import type { ChatContext } from "./api";
import { AssistantPanel, type AssistantApi } from "./AssistantPanel";
import { useExploreBridge, getExploreBridge } from "./exploreBridge";
import { dispatchCommand } from "./links";
import styles from "./Assistant.module.css";

/** How long a link waits for the Explore workspace to mount before it is explicitly refused. */
export const EXPLORE_WAIT_MS = 3000;
const NO_EXPLORE = "Explore is not available for this project, so that link could not be opened.";

const hasPage = (c: ExploreCommand) => c.type === "openSource" && typeof c.source.page === "number";

interface Props {
  projectId: string;
  section: Section;
  onSection: (section: Section) => void;
  /** Sources-tab handling for a document without a page (ProjectView.openSource). */
  onOpenSource: (documentId: string) => void;
  api?: AssistantApi;
  pollIntervalMs?: number;
}

/**
 * The one project-level assistant: mounted by ProjectView outside the tab panels, so it keeps its conversation across
 * tabs. Links use the live Explore bus when it is mounted; otherwise the Explore tab is opened first and the command
 * runs once the bus appears (bounded wait, then an explicit message).
 */
export function ProjectAssistant({ projectId, section, onSection, onOpenSource, api, pollIntervalMs }: Props) {
  const bridge = useExploreBridge();
  const [notice, setNotice] = useState<string | null>(null);
  const pending = useRef<{ command: ExploreCommand; timer: number } | null>(null);
  const handlers = useRef({ onSection, onOpenSource });
  handlers.current = { onSection, onOpenSource };

  const live = bridge.context !== null && bridge.context.projectId === projectId ? bridge.context : null;
  const context = useMemo<ChatContext>(
    () =>
      section === "explore" && live !== null
        ? { wellbore_id: live.wellboreId, selected_element_id: live.selectedElementId, selected_surface_key: null, view: live.view, as_of: live.asOf, chart_key: null }
        : { wellbore_id: null, selected_element_id: null, selected_surface_key: null, view: "3d", as_of: null, chart_key: null },
    [section, live],
  );

  const clearPending = useCallback(() => {
    if (pending.current !== null) window.clearTimeout(pending.current.timer);
    pending.current = null;
  }, []);
  useEffect(() => clearPending, [clearPending]);
  useEffect(() => clearPending(), [projectId, clearPending]);

  // Run the waiting command as soon as the Explore bus is published.
  useEffect(() => {
    const p = pending.current;
    if (p === null || bridge.bus === null) return;
    clearPending();
    const r = dispatchCommand(bridge.bus, p.command);
    setNotice(r.ok ? null : r.message);
  }, [bridge.bus, clearPending]);

  const proxy = useMemo<ExploreCommandBus>(
    () => ({
      subscribe: () => () => undefined,
      replay: () => undefined,
      size: 0,
      pending: 0,
      dispatch(command): ExploreCommandOutcome {
        setNotice(null);
        const bus = getExploreBridge().bus;
        if (bus !== null) return bus.dispatch(command);
        if (command.type === "openSource" && !hasPage(command) && command.source.documentId !== "") {
          handlers.current.onOpenSource(command.source.documentId);
          return "handled";
        }
        clearPending();
        const timer = window.setTimeout(() => {
          pending.current = null;
          setNotice(NO_EXPLORE);
        }, EXPLORE_WAIT_MS);
        pending.current = { command, timer };
        handlers.current.onSection("explore");
        return "queued";
      },
    }),
    [clearPending],
  );

  return (
    <div className={styles.host} data-testid="project-assistant" data-placement="fixed-bottom-right">
      <ExploreCommandsProvider bus={proxy}>
        <AssistantPanel
          projectId={projectId}
          context={context}
          renderChart={(spec) => <ChartBlock spec={spec} wellboreId={live?.wellboreId ?? null} />}
          {...(api === undefined ? {} : { api })}
          {...(pollIntervalMs === undefined ? {} : { pollIntervalMs })}
        />
      </ExploreCommandsProvider>
      {notice !== null ? (
        <p role="alert" className={styles.notice}>
          {notice}{" "}
          <button type="button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </p>
      ) : null}
    </div>
  );
}
