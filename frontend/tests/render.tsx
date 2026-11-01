import { render as baseRender, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { DesignProvider } from "../src/design";

/** Renders inside the project theme (Mantine components need its provider; `test` env: no portals). */
export function render(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">): RenderResult {
  return baseRender(ui, { wrapper: ({ children }) => <DesignProvider test>{children}</DesignProvider>, ...options });
}
