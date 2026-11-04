import { getJson, sendJson } from "../../api/client";
import type { components } from "../../api/generated";

type S = components["schemas"];
export type ChatTurn = S["ChatTurn"];
export type ChatRunState = S["ChatRunState"];
export type ChatContext = S["ChatContext"];
export type ChatMessage = S["ChatMessage"];
export type ChatAnswer = S["ChatAnswer"];
export type AnswerBlock = S["AnswerBlock"];
export type AppLink = S["AppLink"];
export type Citation = S["Citation"];
export type ChartSpec = S["ChartSpec"];
export type Conversation = S["Conversation"];
export type ConversationList = S["ConversationList"];
export type ConversationDetail = S["ConversationDetail"];
export type CreateTurnRequest = S["CreateTurnRequest"];

/**
 * Thin typed client for the TASK-103 chat routes. The route paths are an assumption until that
 * branch merges (routes.py was not available when this was written); only this file knows them.
 */
const base = (projectId: string) => `/api/v1/projects/${projectId}/chat/conversations`;

export const listConversations = (projectId: string, signal: AbortSignal) =>
  getJson<ConversationList>(`${base(projectId)}?limit=50`, signal);

export const createConversation = (projectId: string, title: string | null = null, signal?: AbortSignal) =>
  sendJson<Conversation>(base(projectId), "POST", { title }, signal);

export const getConversation = (projectId: string, conversationId: string, signal: AbortSignal) =>
  getJson<ConversationDetail>(`${base(projectId)}/${conversationId}`, signal);

export const postTurn = (
  projectId: string,
  conversationId: string,
  message: string,
  context: ChatContext | undefined,
  idempotencyKey: string,
  signal?: AbortSignal,
) =>
  sendJson<ChatTurn>(
    `${base(projectId)}/${conversationId}/turns`,
    "POST",
    { message, context: context ?? {}, idempotency_key: idempotencyKey },
    signal,
  );

export const getTurn = (projectId: string, conversationId: string, turnId: string, signal: AbortSignal) =>
  getJson<ChatTurn>(`${base(projectId)}/${conversationId}/turns/${turnId}`, signal);

export const cancelTurn = (projectId: string, conversationId: string, turnId: string, signal?: AbortSignal) =>
  sendJson<ChatTurn>(`${base(projectId)}/${conversationId}/turns/${turnId}/cancel`, "POST", {}, signal);
