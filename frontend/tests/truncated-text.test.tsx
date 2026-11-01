// Repair D5: long identifiers are keyboard reachable (focusable, full value in the DOM, copyable).
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TruncatedText } from "../src/design";
import { render } from "./render";

const SHA = "a".repeat(64);

describe("TruncatedText", () => {
  it("is a focusable button with the full value in its name and text, and copies on activation", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<TruncatedText value={SHA} label="SHA-256" maxCh={16} />);
    const button = screen.getByRole("button", { name: `Copy SHA-256: ${SHA}` });
    expect(button).toHaveTextContent(SHA);
    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(writeText).toHaveBeenCalledWith(SHA);
  });
});
