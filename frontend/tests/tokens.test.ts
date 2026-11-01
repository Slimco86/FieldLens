// UI-1 (style scan) and UI-3 (contrast of every token pair used for text and UI parts).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";
import { contrastPairs, contrastRatio, cssVariables } from "../src/design/tokens";

const SRC = join(import.meta.dirname, "..", "src");
const SKIP = [join(SRC, "api", "generated.ts")];

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name: string) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

// Every application source file outside the design folder and the generated client.
const files: [string, string][] = walk(SRC)
  .filter((f) => /\.(css|ts|tsx)$/.test(f) && !SKIP.includes(f) && !f.startsWith(join(SRC, "design") + sep))
  .map((f): [string, string] => [relative(SRC, f), readFileSync(f, "utf8")]);

const HEX = /(?<![\w&/])#[0-9a-fA-F]{3,8}\b/;
const FUNCTIONAL_COLOR = /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(/;
const PX = /(?<![\w.-])-?\d*\.?\d+px\b/;
const NAMED_COLOR =
  /:\s*(?:white|black|red|green|blue|gray|grey|orange|yellow|purple|pink|teal|navy)\b|color:\s*(?:white|black)\b/i;
const STYLE_LITERAL = /\b(?:fontSize|padding|margin|gap|width|height|borderRadius|color|background)\s*:\s*(?:["'`]?\d|["'`]#)/;

function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

describe("UI-1 design token style scan", () => {
  it("scans the application sources (guards against an empty scan)", () => {
    expect(files.length).toBeGreaterThan(20);
    expect(files.some(([f]) => f.endsWith("Shell.module.css"))).toBe(true);
  });

  it.each(files)("%s has no literal colors or off-scale pixels", (file, source) => {
    const text = stripComments(source);
    const offenders = text.split("\n").filter((line) => {
      return (
        HEX.test(line) ||
        FUNCTIONAL_COLOR.test(line) ||
        PX.test(line) ||
        (file.endsWith(".css") && NAMED_COLOR.test(line)) ||
        (file.endsWith(".tsx") && STYLE_LITERAL.test(line))
      );
    });
    expect(offenders).toEqual([]);
  });

  it("the scan itself rejects a violation", () => {
    for (const bad of ["color: #1b5fd6;", "color: rgb(1, 2, 3);", "margin: 13px;", "style={{ fontSize: 13 }}"]) {
      expect(HEX.test(bad) || FUNCTIONAL_COLOR.test(bad) || PX.test(bad) || STYLE_LITERAL.test(bad), bad).toBe(true);
    }
  });
});

describe("UI-3 token contrast", () => {
  it.each(contrastPairs().map((p) => [p.name, p] as const))("%s meets WCAG 2.2 AA", (_name, pair) => {
    expect(contrastRatio(pair.fg, pair.bg)).toBeGreaterThanOrEqual(pair.min);
  });

  it("publishes every tone as CSS variables (text, background, border)", () => {
    const vars = cssVariables();
    for (const tone of ["neutral", "info", "success", "warning", "danger", "unknown"]) {
      for (const part of ["fg", "bg", "border"]) expect(vars[`--fl-tone-${tone}-${part}`]).toMatch(/^#/);
    }
  });

  it("grayscale legibility: chip text keeps 3:1 against its background by luminance", () => {
    // WCAG contrast is computed from relative luminance, so equal luminance contrast means the same
    // legibility with color removed; the 4.5:1 text pairs above already exceed 3:1.
    const chipPairs = contrastPairs().filter((p) => /^(tone|evidence) .* text$/.test(p.name));
    expect(chipPairs.length).toBeGreaterThanOrEqual(11);
    for (const p of chipPairs) expect(contrastRatio(p.fg, p.bg)).toBeGreaterThanOrEqual(3);
  });
});
