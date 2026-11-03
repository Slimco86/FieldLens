import { scenePalette } from "./scenePalette";

// Single source of design values (UI-1). Application styles reference these only through the
// Mantine theme or the `--fl-*` CSS variables generated below; literal colors and off-scale pixel
// values outside this folder fail `tests/tokens.test.ts`.

/** Cobalt brand ramp; index 6 is the primary (about 5.9:1 against white). */
export const brand = [
  "#eef4ff",
  "#dce8ff",
  "#bdd2fb",
  "#93b5f5",
  "#6592ea",
  "#3e73dd",
  "#1b5fd6",
  "#1750b6",
  "#133f91",
  "#0f3170",
] as const;

/** Cool neutral ramp. */
export const gray = [
  "#f8fafc",
  "#f1f4f8",
  "#e6ebf1",
  "#d4dbe5",
  "#b5bfcd",
  "#818da0",
  "#5d6a7e",
  "#4b586b",
  "#344054",
  "#1d2939",
] as const;

export const color = {
  white: "#ffffff",
  text: gray[9],
  textMuted: gray[6],
  textOnBrand: "#ffffff",
  surface: "#ffffff",
  surfaceSunken: gray[0],
  surfaceHover: gray[1],
  border: gray[3],
  borderStrong: gray[5],
  brand: brand[6],
  brandHover: brand[7],
  brandSoft: brand[0],
  brandSoftBorder: brand[2],
  brandText: brand[7],
  focusRing: brand[6],
  // Selection / attention accent reserved for the 3D scene and charts.
  attention: "#b87000",
  // Attention-coloured text on light surfaces (same value as the warning tone text; AA 4.5:1+).
  attentionText: "#7a4a00",
} as const;

export type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "unknown";

/** Status tones: text, tinted background and border. Always rendered with an icon and a label. */
export const tone: Record<Tone, { fg: string; bg: string; border: string }> = {
  neutral: { fg: gray[8], bg: gray[1], border: gray[4] },
  info: { fg: brand[8], bg: brand[0], border: brand[3] },
  success: { fg: "#0b5d32", bg: "#e8f6ee", border: "#7fc79f" },
  warning: { fg: "#7a4a00", bg: "#fff4dc", border: "#e3b04b" },
  danger: { fg: "#a1191f", bg: "#fdecee", border: "#e8939a" },
  unknown: { fg: gray[7], bg: color.white, border: gray[5] },
};

/** Colorblind-safe evidence-class palette (Okabe-Ito derived); every use pairs icon and text. */
export const evidence: Record<string, { fg: string; bg: string; border: string }> = {
  source_record: { fg: "#00406b", bg: "#e3f1fa", border: "#56a3d6" },
  catalog_derived: { fg: "#5c3d00", bg: "#fff1d6", border: "#d9a441" },
  derived: { fg: "#00573f", bg: "#e1f5ee", border: "#4fb592" },
  interpolated: { fg: "#6b2c4f", bg: "#f9e8f1", border: "#d58ab4" },
  generic: { fg: gray[8], bg: gray[1], border: gray[5] },
  model_proposal: { fg: "#43308a", bg: "#efeafb", border: "#9a86d8" },
};

export const font = {
  family: "'Inter Variable', Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  mono: "ui-monospace, 'SFMono-Regular', Menlo, Consolas, 'Liberation Mono', monospace",
} as const;

/** 14 px base, modest scale (px values only here). */
export const fontSize = { xs: 12, sm: 13, md: 14, lg: 16, xl: 20, xxl: 24 } as const;
export const lineHeight = { tight: 1.25, body: 1.5 } as const;

/** 8 px grid with a 4 px half step. */
export const space = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;
export const radius = { xs: 2, sm: 4, md: 6, lg: 8 } as const;

export const shadow = {
  sm: "0 1px 2px rgba(16, 24, 40, 0.06)",
  md: "0 4px 12px rgba(16, 24, 40, 0.08)",
} as const;

export const motion = { fast: 120, base: 160, slow: 200 } as const;
export const layout = {
  sidebar: 300,
  header: 56,
  content: 1680,
  tree: 280,
  inspector: 340,
  rail: 44,
  stageMin: 520,
  ring: 2,
  ringOffset: 2,
  tableMin: 960,
  hairline: 1,
  strokeStrong: 2,
} as const;

const px = (n: number) => `${n}px`;

/** Every `--fl-*` variable, derived from the values above. */
export function cssVariables(): Record<string, string> {
  const v: Record<string, string> = {
    "--fl-font-family": font.family,
    "--fl-font-mono": font.mono,
    "--fl-line-body": String(lineHeight.body),
    "--fl-line-tight": String(lineHeight.tight),
    "--fl-focus-ring-width": px(layout.ring),
    "--fl-focus-ring-offset": px(layout.ringOffset),
    "--fl-border-width": px(layout.hairline),
    "--fl-border-width-strong": px(layout.strokeStrong),
    "--fl-layout-sidebar": px(layout.sidebar),
    "--fl-layout-header": px(layout.header),
    "--fl-layout-content": px(layout.content),
    "--fl-layout-tree": px(layout.tree),
    "--fl-layout-inspector": px(layout.inspector),
    "--fl-layout-rail": px(layout.rail),
    "--fl-layout-stage-min": px(layout.stageMin),
    "--fl-layout-table-min": px(layout.tableMin),
  };
  for (const [k, val] of Object.entries(color)) {
    v[`--fl-color-${k.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`] = val;
  }
  for (const [name, t] of Object.entries(tone)) {
    v[`--fl-tone-${name}-fg`] = t.fg;
    v[`--fl-tone-${name}-bg`] = t.bg;
    v[`--fl-tone-${name}-border`] = t.border;
  }
  for (const [name, t] of Object.entries(evidence)) {
    const key = name.replace(/_/g, "-");
    v[`--fl-evidence-${key}-fg`] = t.fg;
    v[`--fl-evidence-${key}-bg`] = t.bg;
    v[`--fl-evidence-${key}-border`] = t.border;
  }
  for (const [k, val] of Object.entries(scenePalette)) {
    v[`--fl-scene-${k.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}`] = val;
  }
  for (const [k, val] of Object.entries(fontSize)) v[`--fl-font-size-${k}`] = px(val);
  for (const [k, val] of Object.entries(space)) v[`--fl-space-${k}`] = px(val);
  for (const [k, val] of Object.entries(radius)) v[`--fl-radius-${k}`] = px(val);
  for (const [k, val] of Object.entries(shadow)) v[`--fl-shadow-${k}`] = val;
  for (const [k, val] of Object.entries(motion)) v[`--fl-motion-${k}`] = `${val}ms`;
  return v;
}

/** Text/background pairs that must meet WCAG 2.2 AA. `min` is 4.5 for text, 3 for UI parts. */
export interface ContrastPair {
  name: string;
  fg: string;
  bg: string;
  min: 4.5 | 3;
}

export function contrastPairs(): ContrastPair[] {
  const pairs: ContrastPair[] = [
    { name: "text on surface", fg: color.text, bg: color.surface, min: 4.5 },
    { name: "text on sunken surface", fg: color.text, bg: color.surfaceSunken, min: 4.5 },
    { name: "text on hover surface", fg: color.text, bg: color.surfaceHover, min: 4.5 },
    { name: "muted text on surface", fg: color.textMuted, bg: color.surface, min: 4.5 },
    { name: "muted text on sunken surface", fg: color.textMuted, bg: color.surfaceSunken, min: 4.5 },
    { name: "muted text on hover surface", fg: color.textMuted, bg: color.surfaceHover, min: 4.5 },
    { name: "text on brand", fg: color.textOnBrand, bg: color.brand, min: 4.5 },
    { name: "text on brand hover", fg: color.textOnBrand, bg: color.brandHover, min: 4.5 },
    { name: "brand text on surface", fg: color.brandText, bg: color.surface, min: 4.5 },
    { name: "brand text on soft brand", fg: color.brandText, bg: color.brandSoft, min: 4.5 },
    { name: "brand link on surface", fg: color.brand, bg: color.surface, min: 4.5 },
    { name: "focus ring on surface", fg: color.focusRing, bg: color.surface, min: 3 },
    { name: "strong border on surface", fg: color.borderStrong, bg: color.surface, min: 3 },
    { name: "attention accent on surface", fg: color.attention, bg: color.surface, min: 3 },
  ];
  for (const [name, t] of Object.entries(tone)) {
    pairs.push({ name: `tone ${name} text`, fg: t.fg, bg: t.bg, min: 4.5 });
  }
  for (const [name, t] of Object.entries(evidence)) {
    pairs.push({ name: `evidence ${name} text`, fg: t.fg, bg: t.bg, min: 4.5 });
  }
  return pairs;
}

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}
export function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255);
}
export function contrastRatio(fg: string, bg: string): number {
  const a = luminance(fg);
  const b = luminance(bg);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
