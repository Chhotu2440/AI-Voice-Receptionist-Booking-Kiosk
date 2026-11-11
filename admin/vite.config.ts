import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// The admin app talks to the backend through the dev-server proxy (same origin: the refresh cookie and
// API calls need no CORS). In production Nginx serves the admin build and /api on one origin.
// Override the target with ADMIN_BACKEND_URL (env or .env.local).
export default defineConfig(({ mode }) => {
  const backend = loadEnv(mode, process.cwd(), "").ADMIN_BACKEND_URL ?? "http://127.0.0.1:8000";
  const proxy = { "/api": { target: backend, changeOrigin: true } };
  return {
    plugins: [react()],
    server: { port: 5175, proxy },
    preview: { port: 4174, proxy },
    test: { environment: "jsdom", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
  };
});
