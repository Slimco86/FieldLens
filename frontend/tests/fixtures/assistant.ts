import type { AnswerBlock, ChartSpec, ChatAnswer, ChatTurn, Conversation } from "../../src/features/assistant/api";

const U = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const PROJECT = U(1);
export const CONV = U(2);

export const conversation = (over: Partial<Conversation> = {}): Conversation => ({
  conversation_id: CONV,
  project_id: PROJECT,
  title: "Production",
  turn_count: 1,
  created_at: "2026-11-03T10:00:00Z",
  updated_at: "2026-11-03T10:00:00Z",
  ...over,
});

export const answer = (blocks: AnswerBlock[], over: Partial<ChatAnswer> = {}): ChatAnswer => ({
  blocks,
  citations: [],
  dropped_blocks: [],
  verification: "verified",
  ...over,
});

export function turn(state: ChatTurn["state"], over: Partial<ChatTurn> = {}, n = 10): ChatTurn {
  const msg = (role: "user" | "assistant", text: string | null, a: ChatAnswer | null) => ({
    conversation_id: CONV,
    created_at: "2026-11-03T10:00:00Z",
    message_id: U(n + (role === "user" ? 1 : 2)),
    role,
    text,
    turn_id: U(n),
    answer: a,
  });
  return {
    assistant_message: null,
    completed_at: null,
    context: {} as ChatTurn["context"],
    conversation_id: CONV,
    created_at: "2026-11-03T10:00:00Z",
    failure: null,
    project_id: PROJECT,
    started_at: null,
    state,
    tool_calls: [],
    turn_id: U(n),
    usage: {} as ChatTurn["usage"],
    user_message: msg("user", "What is the oil rate?", null),
    ...over,
    ...(over.assistant_message === undefined && state === "completed"
      ? { assistant_message: msg("assistant", null, answer([{ kind: "text", text: "Rate is **120** sm3/d." }])) }
      : {}),
  };
}

export const chartSpec = (over: Partial<ChartSpec> = {}): ChartSpec =>
  ({
    as_of: null,
    axes: [],
    cache_key: "k",
    chart_id: "c1",
    empty: null,
    evidence: [],
    excluded_series: [],
    key: "production_rates",
    kind: "line",
    notes: [],
    reference_lines: [],
    scope: { ambiguity: null, scope: "wellbore", scope_label: "W-1" },
    series: [
      {
        aggregates: {},
        axis_id: "a",
        downsample: {},
        evidence: [],
        gap_count: 2,
        kind: "line",
        name: "Oil rate",
        points: [{ x: "2026-01-01", y: 1 }],
        scope: { ambiguity: null, scope: "wellbore", scope_label: "W-1" },
        series_key: "s1",
        series_revision: null,
        source_series_id: null,
        stack_group: null,
        unit: "sm3/d",
        unit_status: "stated",
        x_axis_id: null,
      },
    ],
    title: "Oil rate",
    window: null,
    ...over,
  }) as unknown as ChartSpec;
