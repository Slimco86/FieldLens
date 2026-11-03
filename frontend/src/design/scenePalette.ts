// Colours of the 3D scene (design tokens for the viewer; literal values live in this folder only).
// Paints are industrial and slightly muted so the metal reads as metal under the neutral studio light.

export const scenePalette = {
  // Stage backdrop (vertical gradient behind a transparent canvas) and fog tint.
  backdropTop: "#0d1726",
  backdropBottom: "#1f3350",
  fog: "#14223a",
  groundDisc: "#2a3b55",
  gridMajor: "#4a6283",
  gridMinor: "#2f4260",
  trayFill: "#5b4a2a",
  trayEdge: "#e3b04b",
  trajectory: "#8fb6ff",
  trajectoryPlaceholder: "#e3b04b",
  depthMark: "#9fb3cf",
  labelBg: "#0b1626",
  labelText: "#f1f5fa",
  labelBorder: "#6f89ad",
  labelMuted: "#b8c7dc",
  // Selection / attention accent (matches the design attention colour family).
  highlight: "#ffb347",
  // Field view (TASK-080): pads under each wellbore and the colour of markers; never engineering state.
  fieldPad: "#3a5379",
  fieldPadMissing: "#4d4838",
  fieldPadError: "#5e3a3a",
  fieldPadLoading: "#34455f",
  fieldMarkerDocumented: "#6fe0c0",
  fieldMarkerIllustrative: "#9aa6b4",
  // Materials.
  steel: "#a9b3bd",
  steelDark: "#5c6670",
  steelBright: "#cfd6dc",
  casing: "#7d8994",
  rubber: "#1d2024",
  brass: "#c9973a",
  paintBlue: "#2c68b4",
  paintRed: "#b8362b",
  paintYellow: "#d9a62b",
  paintGreen: "#2f8a6b",
  paintCream: "#d8d4c4",
  paintOrange: "#d9692b",
  paintGrey: "#8a96a3",
  perforation: "#ff7a2f",
  concrete: "#6c7480",
  genericGrey: "#9aa6b4",
  genericMix: "#8d98a6",
} as const;

export type MaterialRole =
  | "steel"
  | "steelDark"
  | "steelBright"
  | "casing"
  | "rubber"
  | "brass"
  | "paintBlue"
  | "paintRed"
  | "paintYellow"
  | "paintGreen"
  | "paintCream"
  | "paintOrange"
  | "paintGrey"
  | "perforation"
  | "concrete"
  | "genericGrey";
