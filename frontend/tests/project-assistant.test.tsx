// TASK-114: one project-level assistant, fixed at the bottom-right on every project tab.
// Stubbed fetch / fake chat api: proves UI behaviour, not the live backend.
import { act, cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "./render";
import { ProjectView } from "../src/features/projects/ProjectView";
import type { Section } from "../src/features/projects/keys";
import { conversationStorageKey, type AssistantApi } from "../src/features/assistant/AssistantPanel";
import { ProjectAssistant } from "../src/features/assistant/ProjectAssistant";
import { publishExploreBus, publishExploreContext } from "../src/features/assistant/exploreBridge";
import { createExploreCommandBus } from "../src/features/scene/exploreCommands";
import { CONV, PROJECT, answer, conversation, turn } from "./fixtures/assistant";

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
const PROJ = {
  project_id: PROJECT, name: "Volve subset", description: "d", created_at: "2026-10-28T12:00:00Z", updated_at: "2026-10-28T12:00:00Z",
  latest_source_revision_id: null, active_model_revision_id: null,
};

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  cleanup();
  publishExploreBus(null);
  publishExploreContext(null);
  vi.unstubAllGlobals();
});

describe("project-level assistant launcher", () => {
  it("is rendered by ProjectView on a non-Explore tab, fixed at the bottom-right", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => json(String(input) === `/api/v1/projects/${PROJECT}` ? PROJ : {})));
    function H() {
      const [s, set] = useState<Section>("reconstruction");
      return <ProjectView projectId={PROJECT} section={s} onSection={set} onBack={() => undefined} onMissing={() => undefined} />;
    }
    render(<H />);
    const launcher = await screen.findByRole("button", { name: "Ask the assistant" });
    expect(launcher).toBeInTheDocument();
    expect(screen.getByTestId("project-assistant")).toHaveAttribute("data-placement", "fixed-bottom-right");
  });
});

describe("assistant link on a non-Explore tab", () => {
  it("switches to Explore, waits for the bus, then dispatches; context is project-only off Explore", async () => {
    const link = { label: "Open W9", target: { kind: "wellbore", wellbore_id: "w9" }, tool_call_id: null };
    const done = turn("completed", {
      assistant_message: {
        ...turn("completed").user_message,
        role: "assistant",
        text: null,
        answer: answer([{ kind: "link", link } as never]),
      },
    });
    const api = {
      listConversations: vi.fn(),
      createConversation: vi.fn(async () => conversation()),
      getConversation: vi.fn(async () => ({ conversation: conversation(), turns: [done] })),
      postTurn: vi.fn(async () => turn("queued")),
      cancelTurn: vi.fn(),
    } as unknown as AssistantApi;
    window.localStorage.setItem(conversationStorageKey(PROJECT), CONV);
    function H() {
      const [s, set] = useState<Section>("sources");
      return (
        <>
          <output data-testid="section">{s}</output>
          <ProjectAssistant projectId={PROJECT} section={s} onSection={set} onOpenSource={() => undefined} api={api} />
        </>
      );
    }
    render(<H />);
    await userEvent.click(screen.getByRole("button", { name: "Ask the assistant" }));
    await userEvent.click(await screen.findByRole("button", { name: "Open W9" }));
    expect(screen.getByTestId("section")).toHaveTextContent("explore");

    const bus = createExploreCommandBus();
    const focusWellbore = vi.fn(() => true);
    bus.subscribe({ focusWellbore });
    act(() => publishExploreBus(bus));
    await waitFor(() => expect(focusWellbore).toHaveBeenCalledWith(expect.objectContaining({ wellboreId: "w9" })));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
