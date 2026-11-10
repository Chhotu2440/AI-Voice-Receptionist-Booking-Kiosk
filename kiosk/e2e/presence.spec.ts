import { expect, test } from "@playwright/test";

import { ADMIN } from "../playwright.config";

// Chrome's synthetic camera (a moving test pattern, no face) exercises the real MediaPipe pipeline:
// the model and WASM load from our own origin, frames are processed, and nobody gets "greeted".
test.use({
  permissions: ["camera"],
  launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
});

test("CAM-01: presence pipeline runs on-device and does not false-trigger without a face", async ({ page, request }) => {
  const login = await request.post("/api/v1/auth/login", { data: ADMIN });
  const token = (await login.json()).access_token as string;
  const auth = { Authorization: `Bearer ${token}` };
  const created = await request.post("/api/v1/admin/kiosks", { data: { name: `Presence ${Date.now()}` }, headers: auth });
  const { pairing_code: code, kiosk } = await created.json();
  await request.patch(`/api/v1/admin/kiosks/${kiosk.id}`, { data: { config: { presence_debug: true } }, headers: auth });

  const external: string[] = [];
  page.on("request", (r) => {
    const url = new URL(r.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) external.push(r.url());
  });

  await page.goto("/");
  for (const ch of code as string) await page.getByTestId(/[0-9-]/.test(ch) ? `key-${ch}` : `kb-${ch}`).tap();
  await page.getByTestId("pair-submit").tap();
  await expect(page.getByTestId("tap-to-start")).toBeEnabled();

  // Heartbeat brings the per-kiosk config (presence_debug) within a minute; reload to apply immediately.
  await page.reload();
  await expect(page.getByTestId("presence-debug")).toContainText("cam ok", { timeout: 30_000 });
  await page.waitForTimeout(3000);
  await expect(page.getByTestId("presence-debug")).toContainText("faces 0");
  await expect(page.getByTestId("tap-to-start")).toBeVisible(); // still idle: no greeting without a person
  expect(external).toEqual([]); // nothing leaves the kiosk: model + runtime are served locally

  const list = await request.get("/api/v1/admin/kiosks", { headers: auth });
  const me = (await list.json()).find((k: { id: string }) => k.id === kiosk.id);
  expect(me.health.camera_ok).toBe(true);
});

test("CAM-02: without camera permission the kiosk stays tap-to-start", async ({ browser, request }) => {
  const context = await browser.newContext({ permissions: [] , viewport: { width: 1920, height: 1080 }, hasTouch: true, baseURL: test.info().project.use.baseURL });
  const page = await context.newPage();
  const login = await request.post("/api/v1/auth/login", { data: ADMIN });
  const token = (await login.json()).access_token as string;
  const created = await request.post("/api/v1/admin/kiosks", {
    data: { name: `NoCam ${Date.now()}` },
    headers: { Authorization: `Bearer ${token}` },
  });
  const code = (await created.json()).pairing_code as string;
  await page.goto("/");
  for (const ch of code) await page.getByTestId(/[0-9-]/.test(ch) ? `key-${ch}` : `kb-${ch}`).tap();
  await page.getByTestId("pair-submit").tap();
  await expect(page.getByTestId("tap-to-start")).toBeEnabled();
  await page.getByTestId("tap-to-start").tap();
  await expect(page.getByTestId("lets-go")).toBeVisible();
  await context.close();
});
