// Literal colours and pixel sizes of the formation layer (TASK-098) live here, like `scenePalette`: feature code
// imports them and carries no literals of its own (UI-1 token scan).
import type { CSSProperties } from "react";
import { scenePalette } from "./scenePalette";

/** Okabe-Ito based, colour-blind-safe hues that keep contrast on the dark stage. Meaning is also carried by shape and text. */
export const formationSurfaceColors = ["#e69f00", "#56b4e9", "#009e73", "#f0e442", "#6ea8ff", "#d55e00", "#cc79a7", "#d9e2ee"] as const;

/** Selected/hovered marker is lifted toward this colour. */
export const formationHotColor = "#ffffff";

const chipBase: CSSProperties = {
  pointerEvents: "auto",
  background: scenePalette.labelBg,
  color: scenePalette.labelText,
  border: `1px solid ${scenePalette.labelBorder}`,
  borderRadius: 4,
  padding: "2px 6px",
  font: "12px/1.3 system-ui, sans-serif",
  textAlign: "left",
  cursor: "pointer",
  whiteSpace: "nowrap",
  marginLeft: 10,
};

/** In-scene label chip (a button, so it is keyboard and screen-reader reachable). */
export const formationChipStyle = (selected: boolean): CSSProperties => ({
  ...chipBase,
  outline: selected ? `2px solid ${scenePalette.highlight}` : "none",
});

export const formationChipLineStyle = (strong: boolean): CSSProperties => ({ display: "block", fontWeight: strong ? 600 : 400 });
export const formationChipMutedStyle: CSSProperties = { display: "block", color: scenePalette.labelMuted, fontSize: 11 };
