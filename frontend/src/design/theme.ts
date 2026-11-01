import { createTheme, rem, type CSSVariablesResolver, type MantineColorsTuple } from "@mantine/core";
import { brand, color, cssVariables, font, fontSize, gray, lineHeight, radius, shadow, space } from "./tokens";

const tuple = (values: readonly string[]): MantineColorsTuple => values as unknown as MantineColorsTuple;

/** The one Mantine theme object (light only, cobalt brand, Inter). */
export const theme = createTheme({
  primaryColor: "brand",
  primaryShade: 6,
  colors: { brand: tuple(brand), gray: tuple(gray) },
  black: color.text,
  white: color.white,
  fontFamily: font.family,
  fontFamilyMonospace: font.mono,
  fontSmoothing: true,
  fontSizes: {
    xs: rem(fontSize.xs),
    sm: rem(fontSize.sm),
    md: rem(fontSize.md),
    lg: rem(fontSize.lg),
    xl: rem(fontSize.xl),
  },
  lineHeights: { xs: String(lineHeight.tight), sm: String(lineHeight.body), md: String(lineHeight.body), lg: String(lineHeight.body), xl: String(lineHeight.tight) },
  spacing: {
    xs: rem(space.xs),
    sm: rem(space.sm),
    md: rem(space.md),
    lg: rem(space.lg),
    xl: rem(space.xl),
  },
  radius: {
    xs: rem(radius.xs),
    sm: rem(radius.sm),
    md: rem(radius.md),
    lg: rem(radius.lg),
    xl: rem(radius.lg),
  },
  defaultRadius: "sm",
  shadows: { xs: shadow.sm, sm: shadow.sm, md: shadow.md, lg: shadow.md, xl: shadow.md },
  headings: {
    fontFamily: font.family,
    fontWeight: "600",
    sizes: {
      h1: { fontSize: rem(fontSize.xxl), lineHeight: String(lineHeight.tight) },
      h2: { fontSize: rem(fontSize.xl), lineHeight: String(lineHeight.tight) },
      h3: { fontSize: rem(fontSize.xl), lineHeight: String(lineHeight.tight) },
      h4: { fontSize: rem(fontSize.lg), lineHeight: String(lineHeight.tight) },
      h5: { fontSize: rem(fontSize.md), lineHeight: String(lineHeight.body) },
      h6: { fontSize: rem(fontSize.md), lineHeight: String(lineHeight.body) },
    },
  },
  focusRing: "auto",
  components: {
    Button: { defaultProps: { fw: 500 } },
    Table: { defaultProps: { verticalSpacing: "xs", horizontalSpacing: "sm" } },
  },
});

/** Publishes the `--fl-*` variables and aligns Mantine's text and border roles with them. */
export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: cssVariables(),
  light: {
    "--mantine-color-text": color.text,
    "--mantine-color-body": color.surfaceSunken,
    "--mantine-color-dimmed": color.textMuted,
    "--mantine-color-default-border": color.border,
    "--mantine-color-anchor": color.brandText,
  },
  dark: {},
});
