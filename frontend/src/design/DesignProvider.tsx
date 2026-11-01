import type { ReactNode } from "react";
import { MantineProvider } from "@mantine/core";
import { cssVariablesResolver, theme } from "./theme";

/** Mantine provider with the project theme. `test` disables portals and transitions in jsdom. */
export function DesignProvider({ children, test = false }: { children: ReactNode; test?: boolean }) {
  return (
    <MantineProvider
      theme={theme}
      cssVariablesResolver={cssVariablesResolver}
      defaultColorScheme="light"
      forceColorScheme="light"
      env={test ? "test" : "default"}
    >
      {children}
    </MantineProvider>
  );
}
