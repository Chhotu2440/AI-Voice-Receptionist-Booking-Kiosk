import "@fontsource/inter/400.css";
import "@fontsource/inter/600.css";
import "@fontsource/noto-sans-devanagari/400.css";
import "@fontsource/noto-sans-devanagari/600.css";
import "@fontsource/orbitron/600.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { CrashGuard } from "./components/CrashGuard";
import { registerServiceWorker } from "./lib/resilience";

// Kiosk hardening: no context menu, no pinch zoom.
window.addEventListener("contextmenu", (e) => e.preventDefault());
document.addEventListener("gesturestart", (e) => e.preventDefault());

registerServiceWorker();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <CrashGuard>
      <App />
    </CrashGuard>
  </StrictMode>,
);
