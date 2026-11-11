import { defineConfig, devices } from "@playwright/test";

// End-to-end: real backend (throwaway SQLite, seeded owner) + real admin UI.
const BACKEND_PORT = 8014;
const ADMIN_PORT = 5176;
const python = process.env.E2E_PYTHON ?? "python";
export const OWNER = {
  email: "e2e-owner@example.com",
  password: process.env.E2E_ADMIN_PASSWORD ?? "e2e-only-password-0123",
};
const backendEnv = {
  DATABASE_URL: "sqlite+aiosqlite:///./e2e-admin.db",
  APP_ENV: "dev",
  REFRESH_COOKIE_SECURE: "false",
  E2E_ADMIN_PASSWORD: OWNER.password,
  PUBLIC_RATE_LIMIT_PER_MINUTE: "10000",
  BOOKING_RATE_LIMIT_PER_MINUTE: "10000",
  LOGIN_RATE_LIMIT_PER_MINUTE: "100",
  // Isolate from a developer's backend/.env: no origin restriction, no real voice or WhatsApp calls.
  CORS_ORIGINS: "[]",
  OPENAI_API_KEY: "",
  GEMINI_API_KEY: "",
  INTERAKT_API_KEY: "",
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["junit", { outputFile: "e2e-results.xml" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${ADMIN_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}),
  },
  projects: [{ name: "admin-desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: `${python} scripts/e2e_setup.py && ${python} -m uvicorn app.main:create_app --factory --port ${BACKEND_PORT}`,
      cwd: "../backend",
      env: backendEnv,
      url: `http://127.0.0.1:${BACKEND_PORT}/healthz`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${ADMIN_PORT} --strictPort`,
      env: { ADMIN_BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}` },
      url: `http://127.0.0.1:${ADMIN_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
