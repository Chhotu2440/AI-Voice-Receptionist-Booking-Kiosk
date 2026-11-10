import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { ADMIN } from "../playwright.config";

async function adminToken(request: APIRequestContext): Promise<string> {
  const r = await request.post("/api/v1/auth/login", { data: ADMIN });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).access_token as string;
}

async function pairKiosk(page: Page, request: APIRequestContext): Promise<string> {
  const token = await adminToken(request);
  const r = await request.post("/api/v1/admin/kiosks", {
    data: { name: `E2E ${Date.now()}` },
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.status()).toBe(201);
  const code = (await r.json()).pairing_code as string;

  await page.goto("/");
  await expect(page.getByText("Kiosk setup")).toBeVisible();
  for (const ch of code) {
    await page.getByTestId(/[0-9-]/.test(ch) ? `key-${ch}` : `kb-${ch}`).tap();
  }
  await expect(page.getByTestId("pair-code")).toHaveText(code);
  await page.getByTestId("pair-submit").tap();
  await expect(page.getByTestId("tap-to-start")).toBeEnabled();
  return token;
}

async function typeName(page: Page, name: string) {
  for (const ch of name.toUpperCase()) await page.getByTestId(ch === " " ? "kb-space" : `kb-${ch}`).tap();
}

test("E2E-001: touch-only booking from idle to confirmation, then reset", async ({ page, request }) => {
  const token = await pairKiosk(page, request);

  await page.getByTestId("tap-to-start").tap();
  await page.getByTestId("lets-go").tap();
  await typeName(page, "Riya");
  await expect(page.getByTestId("name-value")).toHaveText("Riya");
  await page.getByTestId("name-next").tap();

  for (const d of "9876543210") await page.getByTestId(`key-${d}`).tap();
  await page.getByTestId("key-✓").tap();
  await expect(page.getByTestId("phone-readback")).toHaveText("98765 43210");
  await page.getByTestId("phone-confirm").tap();

  await page.getByTestId("guests-6").tap();
  await page.getByTestId("occasion-FRIENDS_FAMILY").tap();
  await expect(page.getByTestId("package-EXPERT")).toBeVisible();
  await page.getByTestId("choose-INTERMEDIATE").tap();

  // Third open date shown (avoids same-day cut-off edge cases), first available time.
  const dates = page.locator('[data-testid^="date-"]:not([disabled])');
  await dates.nth(2).tap();
  const slots = page.locator('[data-testid^="slot-"]');
  await expect(slots.first()).toBeVisible();
  const start = (await slots.first().getAttribute("data-testid"))!.replace("slot-", "");
  await slots.first().tap();

  await expect(page.getByTestId("prompt")).toHaveText("Review your booking");
  await expect(page.getByTestId("countdown")).toBeVisible();
  const total = await page.getByTestId("total").innerText();
  expect(["₹2,700", "₹3,300"]).toContain(total); // 6 × ₹450 weekday or 6 × ₹550 weekend
  await page.getByTestId("whatsapp-consent").tap();
  await page.getByTestId("confirm-booking").tap();

  await expect(page.getByTestId("confirmed-title")).toBeVisible();
  const reference = await page.getByTestId("booking-reference").innerText();
  expect(reference).toMatch(/^PLT-[0-9A-Z]{6}$/);

  // The booking exists in the backend, made by the kiosk channel, at the chosen time.
  const r = await request.get(`/api/v1/admin/bookings?reference=${reference}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const found = (await r.json()).items[0];
  expect(found.channel).toBe("KIOSK");
  expect(found.start_time).toBe(start);
  expect(found.guest_count).toBe(6);

  // E2E-002: done -> idle, and no customer data left on screen.
  await page.getByTestId("done").tap();
  await expect(page.getByTestId("tap-to-start")).toBeEnabled();
  await expect(page.locator("body")).not.toContainText("Riya");
});

test("E2E-003: reloading mid-booking returns to idle without the previous customer's details", async ({ page, request }) => {
  await pairKiosk(page, request);
  await page.getByTestId("tap-to-start").tap();
  await page.getByTestId("lets-go").tap();
  await typeName(page, "Amit");
  await page.getByTestId("name-next").tap();
  await expect(page.getByTestId("prompt")).toHaveText("What's the best mobile number to reach you?");

  await page.reload();
  await expect(page.getByTestId("tap-to-start")).toBeEnabled();
  await expect(page.locator("body")).not.toContainText("Amit");
});

test("corporate events are routed to an enquiry", async ({ page, request }) => {
  await pairKiosk(page, request);
  await page.getByTestId("tap-to-start").tap();
  await page.getByTestId("lets-go").tap();
  await typeName(page, "Neha");
  await page.getByTestId("name-next").tap();
  for (const d of "9811122233") await page.getByTestId(`key-${d}`).tap();
  await page.getByTestId("key-✓").tap();
  await page.getByTestId("phone-confirm").tap();
  await page.getByTestId("guests-more").tap();
  for (let i = 0; i < 12; i++) await page.getByTestId("guests-plus").tap();
  await expect(page.getByTestId("guests-value")).toHaveText("25");
  await page.getByTestId("guests-next").tap();
  await page.getByTestId("occasion-CORPORATE").tap();
  await expect(page.getByTestId("prompt")).toHaveText("Tell us about your event");
  await page.getByTestId("send-enquiry").tap();
  await expect(page.getByTestId("enquiry-reference")).toHaveText(/^ENQ-[0-9A-Z]{6}$/);
});

test("Hindi language switch", async ({ page, request }) => {
  await pairKiosk(page, request);
  await page.getByTestId("tap-to-start").tap();
  await page.getByTestId("language").tap();
  await expect(page.getByTestId("prompt")).toHaveText("Play Laser Tag में आपका स्वागत है!");
});
