import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { ADMIN } from "../playwright.config";

// KIOSK-06 against the real production build (service worker active).

async function pairedKiosk(page: Page, request: APIRequestContext) {
  const login = await request.post("/api/v1/auth/login", { data: ADMIN });
  const token = (await login.json()).access_token as string;
  const created = await request.post("/api/v1/admin/kiosks", {
    data: { name: `Resilience ${Date.now()}` },
    headers: { Authorization: `Bearer ${token}` },
  });
  const code = (await created.json()).pairing_code as string;
  const creds = await (await request.post("/api/v1/kiosk/register", { data: { pairing_code: code } })).json();
  await page.addInitScript((c) => localStorage.setItem("plt.kiosk.device", JSON.stringify(c)), creds);
  await page.goto("/");
  await expect(page.getByTestId("tap-to-start")).toBeEnabled();
  // The service worker installs and takes control of the page (offline shell cached).
  await page.waitForFunction(() => !!navigator.serviceWorker.controller, null, { timeout: 30_000 });
}

test("REL-K-001: reload with no network shows the kiosk (offline shell) and recovers when back online", async ({ page, request, context }) => {
  await pairedKiosk(page, request);

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByTestId("tap-to-start")).toBeVisible(); // app shell from the cache, not a browser error page
  await expect(page.getByTestId("offline")).toBeVisible();

  await context.setOffline(false);
  await expect(page.getByTestId("offline")).toBeHidden({ timeout: 20_000 });
  await expect(page.getByTestId("tap-to-start")).toBeEnabled();
});

test("REL-K-002: a frozen page is reloaded by the watchdog", async ({ page, request }) => {
  test.setTimeout(90_000);
  await pairedKiosk(page, request);
  await page.evaluate(() => ((window as unknown as { __beforeFreeze: number }).__beforeFreeze = 1));
  await page.waitForTimeout(3_000); // a couple of "alive" signals reach the service worker

  // Block the main thread for 20 s (longer than the 12 s watchdog). The service worker must reload the page.
  const reloaded = page.waitForEvent("load", { timeout: 45_000 });
  const frozeAt = Date.now();
  await page
    .evaluate(() => {
      const until = Date.now() + 20_000;
      while (Date.now() < until) {
        /* frozen */
      }
    })
    .catch(() => undefined); // the reload destroys this execution context
  await reloaded;
  expect(Date.now() - frozeAt).toBeLessThan(25_000);
  expect(await page.evaluate(() => (window as unknown as { __beforeFreeze?: number }).__beforeFreeze ?? 0)).toBe(0);
  await expect(page.getByTestId("tap-to-start")).toBeEnabled();
});
