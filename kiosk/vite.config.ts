import { createHash } from "node:crypto";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";

import react from "@vitejs/plugin-react";
import { loadEnv, type Plugin } from "vite";
import { defineConfig } from "vitest/config";

/** Emits dist/sw.js (KIOSK-06) with this build's id and hashed files filled in. Production builds only. */
function kioskServiceWorker(): Plugin {
  return {
    name: "kiosk-service-worker",
    apply: "build",
    generateBundle(_options, bundle) {
      const files = Object.keys(bundle)
        .filter((f) => !f.endsWith(".map") && !f.endsWith(".woff") && f !== "index.html") // Chrome uses woff2
        .map((f) => `/${f}`)
        .sort();
      const buildId = createHash("sha256").update(files.join(",")).digest("hex").slice(0, 12);
      const source = readFileSync(new URL("./src/sw/sw.js", import.meta.url), "utf8")
        .replace('"__BUILD_ID__"', JSON.stringify(buildId))
        .replace("/*__PRECACHE__*/ []", JSON.stringify(files));
      this.emitFile({ type: "asset", fileName: "sw.js", source });
    },
  };
}

/** "0.1.0+<git sha>" (or "+dev"), reported in heartbeats so the admin can see which build a kiosk runs. */
function appVersion(): string {
  const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string };
  let sha = "dev";
  try {
    sha = execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim() || "dev";
  } catch {
    /* not a git checkout */
  }
  return `${pkg.version}+${sha}`.slice(0, 32);
}

// The kiosk talks to the backend through the dev-server proxy, so the browser only ever sees one origin
// (no CORS, same-origin WebSocket). Override the target with KIOSK_BACKEND_URL (env or .env.local).
export default defineConfig(({ mode }) => {
  const backend = loadEnv(mode, process.cwd(), "").KIOSK_BACKEND_URL ?? "http://127.0.0.1:8000";
  return {
  plugins: [react(), kioskServiceWorker()],
  define: { __APP_VERSION__: JSON.stringify(appVersion()) },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
};
});
