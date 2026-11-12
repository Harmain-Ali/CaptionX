import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "@fontsource/noto-nastaliq-urdu/arabic-500.css";
import "./styles.css";
import App from "./App";
import { startPresence } from "./lib/presence";

startPresence();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
