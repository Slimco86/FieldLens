import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { useScopedResource, useActionScope, type Failure } from "../projects/scope";
import { usePolled } from "../uploads/usePolled";
import * as realApi from "./api";
import type { ChatContext, ChartSpec, ChatTurn, Conversation, ConversationDetail, ConversationList } from "./api";
import { AssistantChartRendererProvider, TurnView } from "./blocks";
import { PersonaAvatar } from "./PersonaAvatar";
import { announcementFor, avatarStateFor, failureHeadline, isActiveTurn, STATE_LABEL } from "./turnState";
import styles from "./Assistant.module.css";

export type AssistantMode = "collapsed" | "docked" | "expanded";

/** The chat client surface the panel needs; tests and fixtures inject a fake. */
export interface AssistantApi {
  listConversations(projectId: string, signal: AbortSignal): Promise<ConversationList>;
  createConversation(projectId: string, title?: string | null, signal?: AbortSignal): Promise<Conversation>;
  getConversation(projectId: string, conversationId: string, signal: AbortSignal): Promise<ConversationDetail>;
  postTurn(
    projectId: string,
    conversationId: string,
    message: string,
    context: ChatContext | undefined,
    idempotencyKey: string,
    signal?: AbortSignal,
  ): Promise<ChatTurn>;
  cancelTurn(projectId: string, conversationId: string, turnId: string, signal?: AbortSignal): Promise<ChatTurn>;
}

export interface AssistantPanelProps {
  projectId: string;
  /** UI selection sent with each turn; it narrows, never widens, scope (AV-1). */
  context?: ChatContext;
  /** Injected chart renderer (TASK-102 ChartBlock); a summary table is used when absent. */
  renderChart?: (spec: ChartSpec) => ReactNode;
  defaultMode?: AssistantMode;
  api?: AssistantApi;
  pollIntervalMs?: number;
}

/** Only the conversation id is persisted locally, never message content. */
export const conversationStorageKey = (projectId: string) => `fieldlens.assistant.conversation.${projectId}`;

function readStoredId(projectId: string): string | null {
  try {
    return window.localStorage.getItem(conversationStorageKey(projectId));
  } catch {
    return null;
  }
}
function writeStoredId(projectId: string, id: string | null): void {
  try {
    if (id === null) window.localStorage.removeItem(conversationStorageKey(projectId));
    else window.localStorage.setItem(conversationStorageKey(projectId), id);
  } catch {
    /* storage unavailable: the conversation is simply not restored */
  }
}

let openedThisSession = false;
/** Test seam: forget that the assistant was opened (new page session). */
export function resetAssistantPulseForTests(): void {
  openedThisSession = false;
}

const newKey = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `k${Date.now()}${Math.random()}`);

export function AssistantPanel({ projectId, context, renderChart, defaultMode = "collapsed", api = realApi, pollIntervalMs }: AssistantPanelProps) {
  const [mode, setMode] = useState<AssistantMode>(defaultMode);
  const [conversationId, setConversationId] = useState<string | null>(() => readStoredId(projectId));
  const [showList, setShowList] = useState(false);
  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<Failure | string | null>(null);
  const [sending, setSending] = useState(false);
  const [version, setVersion] = useState(0);
  const run = useActionScope(projectId);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const prevMode = useRef<AssistantMode>(defaultMode);
  const open = mode !== "collapsed";
  // The attention pulse stops for the rest of the session once the assistant has been opened (CSS also honours reduced motion).
  if (open) openedThisSession = true;
  const pulse = !openedThisSession;

  // Focus management: into the panel when it opens/resizes, back to the launcher when it closes.
  useEffect(() => {
    const prev = prevMode.current;
    prevMode.current = mode;
    if (prev === mode) return;
    if (mode === "collapsed") launcherRef.current?.focus();
    else if (prev === "collapsed") headingRef.current?.focus();
  }, [mode]);

  useEffect(() => {
    setConversationId(readStoredId(projectId));
    setDraft("");
    setSendError(null);
  }, [projectId]);

  const list = useScopedResource<ConversationList>(open && showList ? `assistant-list:${projectId}` : null, (s) => api.listConversations(projectId, s));
  const detailKey = open && conversationId !== null ? `${projectId}:${conversationId}` : null;
  const detail = usePolled<ConversationDetail>(
    detailKey,
    (s) => api.getConversation(projectId, conversationId as string, s),
    (d) => (d.turns ?? []).some(isActiveTurn),
    String(version),
    pollIntervalMs,
  );

  const turns: ChatTurn[] = detail.state.kind === "ready" ? (detail.state.data.turns ?? []) : [];
  const latest = turns.length > 0 ? (turns[turns.length - 1] ?? null) : null;
  const busy = turns.some(isActiveTurn);
  const announcement = announcementFor(latest);

  const select = useCallback(
    (id: string | null) => {
      setConversationId(id);
      writeStoredId(projectId, id);
      setShowList(false);
      setSendError(null);
    },
    [projectId],
  );

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "Escape") return;
    e.stopPropagation();
    setMode(mode === "expanded" ? "docked" : "collapsed");
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const message = draft.trim();
    if (message === "" || sending || busy) return;
    setSending(true);
    setSendError(null);
    const out = await run(async (signal) => {
      let id = conversationId;
      if (id === null) {
        id = (await api.createConversation(projectId, null, signal)).conversation_id;
        select(id);
      }
      await api.postTurn(projectId, id, message, context, newKey(), signal);
    });
    setSending(false);
    if (out.status === "ok") {
      setDraft("");
      setVersion((v) => v + 1);
    } else if (out.status === "error") setSendError(out.error);
  };

  const cancel = async (turn: ChatTurn) => {
    if (conversationId === null) return;
    const out = await run((signal) => api.cancelTurn(projectId, conversationId, turn.turn_id, signal));
    if (out.status === "error") setSendError(out.error);
    setVersion((v) => v + 1);
  };

  const avatar = useMemo(() => avatarStateFor(latest), [latest]);

  if (!open) {
    return (
      <button
        ref={launcherRef}
        type="button"
        className={`${styles.launcher} ${pulse ? styles.pulse : ""}`}
        data-pulse={pulse}
        aria-label="Ask the assistant"
        aria-expanded={false}
        aria-controls="fl-assistant-panel"
        onClick={() => setMode("docked")}
      >
        <PersonaAvatar state="idle" size={28} />
        {busy ? <span className={styles.srOnly}>An answer is in progress</span> : null}
      </button>
    );
  }

  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- Esc steps the panel down; bubbles from focused children
    <section
      id="fl-assistant-panel"
      className={mode === "expanded" ? `${styles.panel} ${styles.expanded}` : styles.panel}
      role={mode === "expanded" ? "dialog" : "region"}
      aria-modal={mode === "expanded" ? false : undefined}
      aria-label="Project assistant"
      data-mode={mode}
      onKeyDown={onKeyDown}
    >
      <header className={styles.header}>
        <PersonaAvatar state={avatar} />
        <h2 ref={headingRef} tabIndex={-1} className={styles.title}>
          Project assistant
        </h2>
        <div className={styles.toolbar}>
          <button type="button" onClick={() => setShowList((v) => !v)} aria-expanded={showList}>
            Conversations
          </button>
          <button type="button" onClick={() => select(null)}>
            New conversation
          </button>
          {mode === "docked" ? (
            <button type="button" onClick={() => setMode("expanded")}>
              Expand
            </button>
          ) : (
            <button type="button" onClick={() => setMode("docked")}>
              Dock
            </button>
          )}
          <button type="button" onClick={() => setMode("collapsed")}>
            Close
          </button>
        </div>
      </header>

      <p role="status" aria-live="polite" className={styles.srOnly} data-testid="assistant-live">
        {announcement}
      </p>

      {showList ? (
        <nav aria-label="Conversations" className={styles.list}>
          {list.state.kind === "loading" ? <p>Loading conversations…</p> : null}
          {list.state.kind === "error" ? <p role="alert">Could not load conversations: {list.state.error.message}</p> : null}
          {list.state.kind === "ready" && list.state.data.items.length === 0 ? <p>No conversations yet.</p> : null}
          {list.state.kind === "ready" ? (
            <ul>
              {list.state.data.items.map((c) => (
                <li key={c.conversation_id}>
                  <button type="button" aria-current={c.conversation_id === conversationId ? "true" : undefined} onClick={() => select(c.conversation_id)}>
                    {c.title ?? "Untitled conversation"} ({c.turn_count})
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </nav>
      ) : null}

      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- keyboard-scrollable region */}
      <div className={styles.log} role="log" aria-label="Conversation" aria-live="off" tabIndex={0}>
        {conversationId === null ? <p className={styles.hint}>Ask about this project. Answers cite sources and say when data is not available.</p> : null}
        {detail.state.kind === "loading" && conversationId !== null ? <p>Loading conversation…</p> : null}
        {detail.state.kind === "error" ? <p role="alert">Could not load the conversation: {detail.state.error.message}</p> : null}
        {detail.state.kind === "ready" && detail.state.refreshError !== null ? (
          <p role="alert">Refresh failed: {detail.state.refreshError.message}. Showing the last known state.</p>
        ) : null}
        {turns.map((t) => (
          <article key={t.turn_id} className={styles.turn} aria-label={`Turn: ${STATE_LABEL[t.state]}`}>
            <p className={styles.user}>{t.user_message.text}</p>
            <div className={styles.assistant}>
              <p className={styles.stateBadge} data-state={t.state}>
                {STATE_LABEL[t.state]}
              </p>
              {t.state === "failed" || t.state === "refused" || t.state === "cancelled" || t.state === "truncated" ? (
                <div role="note" className={styles.failure}>
                  <p>{failureHeadline(t)}</p>
                  {t.failure !== null ? (
                    <p>
                      {t.failure.message} ({t.failure.code}
                      {t.failure.retryable ? ", you can retry" : ""})
                    </p>
                  ) : null}
                </div>
              ) : null}
              <AssistantChartRendererProvider value={renderChart ?? null}>
                <TurnView turn={t} />
              </AssistantChartRendererProvider>
              {isActiveTurn(t) ? (
                <button type="button" onClick={() => void cancel(t)}>
                  Cancel
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>

      {sendError !== null ? (
        <p role="alert" className={styles.warn}>
          Could not send: {typeof sendError === "string" ? sendError : sendError.message}
        </p>
      ) : null}
      <form className={styles.composer} onSubmit={(e) => void submit(e)}>
        <label htmlFor="fl-assistant-input">Message</label>
        <textarea
          id="fl-assistant-input"
          value={draft}
          rows={2}
          maxLength={8000}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void submit(e);
          }}
        />
        <button type="submit" disabled={draft.trim() === "" || sending || busy}>
          {sending ? "Sending…" : "Send"}
        </button>
      </form>
    </section>
  );
}
