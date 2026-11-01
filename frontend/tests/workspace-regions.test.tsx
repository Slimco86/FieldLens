// UI-11: dummy panels mount in each Explore region without changing shell code; an absent region
// renders nothing; collapsing releases space (the toggle is labelled and keeps content mounted).
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ExploreWorkspace } from "../src/app/shell/ExploreWorkspace";
import { render } from "./render";

describe("Explore workspace regions", () => {
  it("mounts a dummy panel in each of tree, stage, inspector and dock", () => {
    render(
      <ExploreWorkspace
        tree={<p>dummy tree</p>}
        stage={<p>dummy stage</p>}
        inspector={<p>dummy inspector</p>}
        dock={<p>dummy dock</p>}
      />,
    );
    for (const [region, text] of [
      ["Tree", "dummy tree"],
      ["Stage", "dummy stage"],
      ["Inspector", "dummy inspector"],
      ["Dock", "dummy dock"],
    ] as const) {
      expect(within(screen.getByRole("region", { name: region })).getByText(text)).toBeVisible();
    }
  });

  it("renders nothing for an absent region, not even a heading or toggle", () => {
    render(<ExploreWorkspace stage={<p>only stage</p>} />);
    expect(screen.getByRole("region", { name: "Stage" })).toBeInTheDocument();
    for (const region of ["Tree", "Inspector", "Dock"]) {
      expect(screen.queryByRole("region", { name: region })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("collapses and expands with a labelled toggle; the stage never collapses", async () => {
    const user = userEvent.setup();
    render(
      <ExploreWorkspace tree={<p>dummy tree</p>} stage={<p>dummy stage</p>} inspector={<p>dummy inspector</p>} dock={<p>dummy dock</p>} />,
    );
    for (const [name, text] of [
      ["tree", "dummy tree"],
      ["inspector", "dummy inspector"],
      ["dock", "dummy dock"],
    ] as const) {
      const collapse = screen.getByRole("button", { name: `Collapse ${name}` });
      expect(collapse).toHaveAttribute("aria-expanded", "true");
      await user.click(collapse);
      const expand = screen.getByRole("button", { name: `Expand ${name}` });
      expect(expand).toHaveAttribute("aria-expanded", "false");
      expect(screen.getByText(text)).not.toBeVisible();
      await user.click(expand);
      expect(screen.getByText(text)).toBeVisible();
    }
    expect(screen.queryByRole("button", { name: /stage/i })).not.toBeInTheDocument();
    expect(screen.getByText("dummy stage")).toBeVisible();
  });
});
