import { defineConfig, devices } from "@playwright/test";

// End-to-end: real backend (throwaway SQLite) + real kiosk UI, driven by touch-style clicks at kiosk size.
const BACKEND_PORT = 8012;
const KIOSK_PORT = 5174;
const PROD_PORT = 5178; // production build (service worker active) for KIOSK-06 resilience tests
const python = process.env.E2E_PYTHON ?? "python";
export const ADMIN = {
  email: "e2e-owner@example.com",
  password: process.env.E2E_ADMIN_PASSWORD ?? "e2e-only-password-0123",
};
const backendEnv = {
  DATABASE_URL: "sqlite+aiosqlite:///./e2e.db",
  APP_ENV: "dev",
  REFRESH_COOKIE_SECURE: "false",
  E2E_ADMIN_PASSWORD: ADMIN.password,
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
    baseURL: `http://127.0.0.1:${KIOSK_PORT}`,
    viewport: { width: 1920, height: 1080 },
    hasTouch: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}),
  },
  projects: [
    {
      name: "kiosk-1080p",
      testIgnore: /resilience.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 }, hasTouch: true },
    },
    {
      name: "kiosk-prod-build",
      testMatch: /resilience.*\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1920, height: 1080 },
        hasTouch: true,
        baseURL: `http://127.0.0.1:${PROD_PORT}`,
      },
    },
  ],
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
      command: `node scripts/copy-mediapipe.mjs && npx vite --host 127.0.0.1 --port ${KIOSK_PORT} --strictPort`,
      env: { KIOSK_BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}` },
      url: `http://127.0.0.1:${KIOSK_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `node scripts/copy-mediapipe.mjs && npx vite build && npx vite preview --host 127.0.0.1 --port ${PROD_PORT} --strictPort`,
      env: { KIOSK_BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}` },
      url: `http://127.0.0.1:${PROD_PORT}`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
