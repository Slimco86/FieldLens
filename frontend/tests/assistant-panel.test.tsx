import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantPanel, conversationStorageKey, resetAssistantPulseForTests, type AssistantApi } from "../src/features/assistant/AssistantPanel";
import { PersonaAvatar } from "../src/features/assistant/PersonaAvatar";
import type { ChatTurn } from "../src/features/assistant/api";
import { announcementFor, avatarStateFor } from "../src/features/assistant/turnState";
import { CONV, PROJECT, conversation, turn } from "./fixtures/assistant";

type Fake = AssistantApi & { [K in keyof AssistantApi]: AssistantApi[K] & ReturnType<typeof vi.fn> };
function fakeApi(turns: () => ChatTurn[]): Fake {
  return {
    listConversations: vi.fn(async () => ({ items: [conversation()], total: 1, limit: 50, offset: 0, next_offset: null })),
    createConversation: vi.fn(async () => conversation()),
    getConversation: vi.fn(async () => ({ conversation: conversation(), turns: turns() })),
    postTurn: vi.fn(async () => turn("queued")),
    cancelTurn: vi.fn(async () => turn("cancelled")),
  } as never;
}

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("assistant panel modes and focus (AV-7)", () => {
  it("launcher opens docked, Expand/Dock switch modes, Esc steps down and returns focus", async () => {
    const api = fakeApi(() => []);
    render(<AssistantPanel projectId={PROJECT} api={api} />);
    const launcher = screen.getByRole("button", { name: /ask the assistant/i });
    expect(launcher).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(launcher);
    const region = screen.getByRole("region", { name: "Project assistant" });
    expect(region).toHaveAttribute("data-mode", "docked");
    expect(screen.getByRole("heading", { name: "Project assistant" })).toHaveFocus();

    await userEvent.click(screen.getByRole("button", { name: "Expand" }));
    expect(screen.getByRole("dialog", { name: "Project assistant" })).toHaveAttribute("data-mode", "expanded");
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("region", { name: "Project assistant" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Project assistant" })).toBeNull();
    expect(screen.getByRole("button", { name: /ask the assistant/i })).toHaveFocus();
  });

  it("collapsed launcher is a pulsing round button that stops pulsing once opened; Close returns focus", async () => {
    resetAssistantPulseForTests();
    const api = fakeApi(() => []);
    const { unmount } = render(<AssistantPanel projectId={PROJECT} api={api} />);
    const launcher = screen.getByRole("button", { name: "Ask the assistant" });
    expect(launcher).toHaveAttribute("data-pulse", "true");
    await userEvent.click(launcher);
    expect(screen.getByRole("region", { name: "Project assistant" })).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    const again = screen.getByRole("button", { name: "Ask the assistant" });
    expect(again).toHaveFocus();
    expect(again).toHaveAttribute("data-pulse", "false");
    unmount();
  });

  it("composer is labelled, sends a turn, creates a conversation and stores only its id", async () => {
    const api = fakeApi(() => []);
    render(<AssistantPanel projectId={PROJECT} api={api} defaultMode="docked" context={{ wellbore_id: "w1" } as never} />);
    const input = screen.getByLabelText("Message");
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    await userEvent.type(input, "Hello there");
    await userEvent.click(send);
    await waitFor(() => expect(api.postTurn).toHaveBeenCalled());
    expect(api.createConversation).toHaveBeenCalled();
    expect(api.postTurn.mock.calls[0]?.[2]).toBe("Hello there");
    expect(api.postTurn.mock.calls[0]?.[3]).toEqual({ wellbore_id: "w1" });
    await waitFor(() => expect(input).toHaveValue(""));
    expect(window.localStorage.getItem(conversationStorageKey(PROJECT))).toBe(CONV);
    expect(JSON.stringify({ ...window.localStorage })).not.toContain("Hello there");
  });

  it("a failed send keeps the draft and shows an alert", async () => {
    const api = fakeApi(() => []);
    api.postTurn.mockRejectedValue(new Error("boom"));
    render(<AssistantPanel projectId={PROJECT} api={api} defaultMode="docked" />);
    await userEvent.type(screen.getByLabelText("Message"), "keep me");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not send/i);
    expect(screen.getByLabelText("Message")).toHaveValue("keep me");
  });

  it("lists conversations and selects one", async () => {
    const api = fakeApi(() => [turn("completed")]);
    render(<AssistantPanel projectId={PROJECT} api={api} defaultMode="docked" />);
    await userEvent.click(screen.getByRole("button", { name: "Conversations" }));
    await userEvent.click(await screen.findByRole("button", { name: /Production/ }));
    expect(await screen.findByText(/120/)).toBeInTheDocument();
    expect(api.getConversation).toHaveBeenCalled();
  });
});

describe("turn state rendering (no fake success)", () => {
  const cases: [ChatTurn["state"], Partial<ChatTurn>, RegExp][] = [
    ["queued", {}, /queued/i],
    ["running", {}, /working/i],
    ["failed", { failure: { code: "provider_outage", message: "down", retryable: true } }, /provider is unavailable/i],
    ["refused", { failure: { code: "provider_refusal", message: "policy", retryable: false } }, /refused/i],
    ["cancelled", {}, /cancelled/i],
    ["truncated", { failure: { code: "truncated", message: "limit", retryable: false } }, /incomplete/i],
  ];
  it.each(cases)("%s is shown explicitly", async (state, over, text) => {
    const t = turn(state, over);
    render(<AssistantPanel projectId={PROJECT} api={fakeApi(() => [t])} defaultMode="docked" />);
    window.localStorage.setItem(conversationStorageKey(PROJECT), CONV);
    // select via list so the stored id path is exercised without remounting
    await userEvent.click(screen.getByRole("button", { name: "Conversations" }));
    await userEvent.click(await screen.findByRole("button", { name: /Production/ }));
    expect((await screen.findAllByText(text)).length).toBeGreaterThan(0);
    expect(screen.queryByText("Answered")).toBeNull();
    expect(screen.getByTestId("assistant-live")).toHaveTextContent(announcementFor(t));
  });

  it("polls an active turn until it completes, announces it, and cancel posts a cancel", async () => {
    let current: ChatTurn = turn("running");
    const api = fakeApi(() => [current]);
    window.localStorage.setItem(conversationStorageKey(PROJECT), CONV);
    render(<AssistantPanel projectId={PROJECT} api={api} defaultMode="docked" pollIntervalMs={20} />);
    expect(await screen.findByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByTestId("assistant-live")).toHaveTextContent(/working/i);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(api.cancelTurn).toHaveBeenCalled();
    current = turn("completed");
    await waitFor(() => expect(screen.getByTestId("assistant-live")).toHaveTextContent("Assistant finished answering."));
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    const calls = api.getConversation.mock.calls.length;
    await new Promise((r) => setTimeout(r, 100));
    expect(api.getConversation.mock.calls.length).toBe(calls); // polling stopped on terminal state
  });
});

describe("persona avatar", () => {
  it("maps turn states to avatar states", () => {
    expect(avatarStateFor(null)).toBe("idle");
    expect(avatarStateFor(turn("running"))).toBe("thinking");
    expect(avatarStateFor(turn("completed"))).toBe("answering");
    expect(avatarStateFor(turn("failed"))).toBe("refusal-error");
    expect(avatarStateFor(turn("refused"))).toBe("refusal-error");
    expect(avatarStateFor(turn("cancelled"))).toBe("idle");
  });

  it("is a labelled SVG image per state", () => {
    const { rerender } = render(<PersonaAvatar state="thinking" />);
    expect(screen.getByRole("img", { name: "Assistant thinking" })).toHaveAttribute("data-state", "thinking");
    rerender(<PersonaAvatar state="refusal-error" />);
    expect(screen.getByRole("img", { name: "Assistant could not answer" })).toBeInTheDocument();
  });

  it("is static when the user prefers reduced motion", () => {
    window.matchMedia = ((q: string) => ({ matches: true, media: q, addEventListener() {}, removeEventListener() {} })) as never;
    render(<PersonaAvatar state="thinking" />);
    expect(screen.getByRole("img")).toHaveAttribute("data-motion", "static");
  });

  it("animates otherwise", () => {
    window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as never;
    render(<PersonaAvatar state="thinking" />);
    expect(screen.getByRole("img")).toHaveAttribute("data-motion", "animated");
  });
});
