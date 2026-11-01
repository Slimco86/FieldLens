import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@mantine/core/styles.css";
import "@mantine/dropzone/styles.css";
import "./design/global.css";
import { App } from "./app/App";
import { DesignProvider } from "./design";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");
createRoot(root).render(
  <StrictMode>
    <DesignProvider>
      <App />
    </DesignProvider>
  </StrictMode>,
);
