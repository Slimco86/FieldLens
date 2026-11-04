import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, type MutableRefObject } from "react";
import { describe, expect, it, vi } from "vitest";
import { FlyOverControls } from "../src/features/scene/FlyOverControls";
import { IDLE_FLY_STATUS, type FlyOverStatus } from "../src/features/scene/flyOverPlan";
import type { ViewerCommands } from "../src/features/scene/Viewer3D";
import { render } from "./render";

function fakeCommands() {
  const c = {
    fitAll: vi.fn(),
    fitWellhead: vi.fn(),
    focus: vi.fn(),
    focusPoint: vi.fn(),
    zoom: vi.fn(),
    flyOver: vi.fn(() => true),
    stopFlyOver: vi.fn(() => true),
    pauseFlyOver: vi.fn(),
    resumeFlyOver: vi.fn(),
    stepFlyOver: vi.fn(),
    setFlySpeed: vi.fn(),
  } satisfies ViewerCommands;
  const ref = createRef<ViewerCommands | null>() as MutableRefObject<ViewerCommands | null>;
  ref.current = c;
  return { c, ref };
}

const playing: FlyOverStatus = {
  state: "playing",
  stopIndex: 1,
  stopCount: 3,
  stop: { id: "packer", label: "Packer", md: 2101 },
  speed: 1,
  announcement: "Stop 2 of 3: Packer, 2,101 m MD.",
  unlocated: [{ id: "g", label: "Ghost valve" }],
  totalS: 40,
};

describe("FlyOverControls (CM-4)", () => {
  it("starts with the chosen speed and is keyboard operable", async () => {
    const user = userEvent.setup();
    const { c, ref } = fakeCommands();
    render(<FlyOverControls commands={ref} status={IDLE_FLY_STATUS} />);
    await user.selectOptions(screen.getByLabelText("Fly-over speed"), "2");
    expect(c.setFlySpeed).toHaveBeenLastCalledWith(2);
    screen.getByRole("button", { name: "Fly over" }).focus();
    await user.keyboard("{Enter}");
    expect(c.flyOver).toHaveBeenCalledOnce();
  });

  it("shows pause/stop/step, the current element card and an aria-live announcement", async () => {
    const user = userEvent.setup();
    const { c, ref } = fakeCommands();
    render(<FlyOverControls commands={ref} status={playing} />);
    expect(screen.getByTestId("fly-over-card")).toHaveTextContent("Packer · 2,101 m MD · 2/3");
    const live = screen.getByRole("status");
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(live).toHaveTextContent("Stop 2 of 3: Packer, 2,101 m MD.");
    expect(screen.getByText(/Not located, not visited: Ghost valve/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(c.pauseFlyOver).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Next stop" }));
    expect(c.stepFlyOver).toHaveBeenCalledWith(1);
    await user.click(screen.getByRole("button", { name: "Previous stop" }));
    expect(c.stepFlyOver).toHaveBeenCalledWith(-1);
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(c.stopFlyOver).toHaveBeenCalled();
  });

  it("offers Play when paused, and disables the start when there is nothing to visit", async () => {
    const user = userEvent.setup();
    const { c, ref } = fakeCommands();
    const { rerender } = render(<FlyOverControls commands={ref} status={{ ...playing, state: "paused" }} />);
    await user.click(screen.getByRole("button", { name: "Play" }));
    expect(c.resumeFlyOver).toHaveBeenCalled();
    rerender(<FlyOverControls commands={ref} status={IDLE_FLY_STATUS} disabled />);
    expect(screen.getByRole("button", { name: "Fly over" })).toBeDisabled();
  });
});
