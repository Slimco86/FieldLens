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
  // Materials: distinct hues per element family (casing blue-grey, tubing light, cement sand, hole brown, rubber charcoal).
  steel: "#b4bdc6",
  steelDark: "#4b545e",
  steelBright: "#e3e9ee",
  casing: "#6f8296",
  rubber: "#2a2c31",
  brass: "#d1a03c",
  paintBlue: "#2f6fd0",
  paintRed: "#c43a2d",
  paintYellow: "#e0b030",
  paintGreen: "#2f9a72",
  paintCream: "#e2dcc6",
  paintOrange: "#e0702a",
  paintGrey: "#8a96a3",
  perforation: "#ff6a3d",
  concrete: "#6c7480",
  cement: "#a89a82",
  openHole: "#6b4f3a",
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
  | "cement"
  | "openHole"
  | "genericGrey";
