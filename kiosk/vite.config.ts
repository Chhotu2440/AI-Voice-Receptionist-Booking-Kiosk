import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// The kiosk talks to the backend through the dev-server proxy, so the browser only ever sees one origin
// (no CORS, same-origin WebSocket). Override the target with KIOSK_BACKEND_URL (env or .env.local).
export default defineConfig(({ mode }) => {
  const backend = loadEnv(mode, process.cwd(), "").KIOSK_BACKEND_URL ?? "http://127.0.0.1:8000";
  return {
  plugins: [react()],
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
