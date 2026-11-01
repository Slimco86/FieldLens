// UI-7: every status vocabulary renders through one chip with a text label and an icon.
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvidenceClassChip, StatusChip, chipVocabulary } from "../src/design";
import { render } from "./render";

describe("status chips", () => {
  it("renders text plus an aria-hidden icon for every value of every vocabulary", () => {
    for (const [kind, table] of Object.entries(chipVocabulary)) {
      for (const value of Object.keys(table)) {
        const { container, unmount } = render(
          <StatusChip kind={kind as "storage"} value={value as "stored"} label={`${kind}:${value}`} />,
        );
        expect(screen.getByText(`${kind}:${value}`)).toBeInTheDocument();
        const icon = container.querySelector("svg");
        expect(icon, `${kind}:${value} has an icon`).not.toBeNull();
        expect(icon).toHaveAttribute("aria-hidden", "true");
        unmount();
      }
    }
  });

  it("covers the generated enums exactly", () => {
    expect(Object.keys(chipVocabulary.storage).sort()).toEqual(["pending_verification", "quarantined", "stored"]);
    expect(Object.keys(chipVocabulary.job).sort()).toEqual([
      "cancelled",
      "failed",
      "interrupted",
      "partial",
      "queued",
      "running",
      "succeeded",
    ]);
    expect(Object.keys(chipVocabulary.validation).sort()).toEqual([
      "conflicting",
      "invalid",
      "unreviewed",
      "unsupported",
      "unverified",
      "valid",
    ]);
  });

  it("evidence classes carry icon and text", () => {
    for (const value of ["source_record", "catalog_derived", "derived", "interpolated", "generic", "model_proposal"] as const) {
      const { container, unmount } = render(<EvidenceClassChip value={value} />);
      expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
      expect(container.textContent?.length).toBeGreaterThan(3);
      unmount();
    }
  });
});
