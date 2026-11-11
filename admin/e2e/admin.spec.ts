import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { OWNER } from "../playwright.config";

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

function nextMonday(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + 1);
  while (d.getUTCDay() !== 1) d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

async function ownerToken(request: APIRequestContext): Promise<string> {
  const r = await request.post("/api/v1/auth/login", { data: OWNER });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).access_token as string;
}

test("ADM-E2E-001: owner signs in, books at the front desk, cancels; session survives reload", async ({ page }) => {
  await signIn(page, "e2e-owner@example.com", "wrong-password-123");
  await expect(page.getByRole("alert")).toContainText("Wrong email or password");

  await signIn(page, OWNER.email, OWNER.password);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByTestId("stat-today")).toBeVisible();

  // Front-desk booking: hold -> book through the real API.
  await page.getByRole("link", { name: "Bookings" }).click();
  await page.getByTestId("new-booking").click();
  await page.getByLabel("Package").selectOption({ label: "Beginner · 30 min · 1–20 players" });
  await page.getByLabel("Players").fill("6");
  const day = nextMonday();
  await page.getByLabel("Date", { exact: true }).fill(day);
  await page.getByTestId("slot-18:00").click();
  await page.getByLabel("Customer name").fill("Asha Verma");
  await page.getByLabel("Mobile").fill("9811122233");
  await page.getByTestId("create-booking").click();

  const detail = page.getByTestId("booking-detail");
  await expect(detail).toContainText("Asha Verma");
  await expect(detail).toContainText("6 players");
  await expect(detail).toContainText("Confirmed");
  await expect(detail).toContainText("₹1,800"); // 6 x ₹300 weekday, GST included
  await expect(page.getByTestId("mark-completed")).toHaveCount(0); // not before the game starts

  // The slot is now taken for this date.
  await page.getByTestId("cancel-booking").click();
  await page.getByLabel("Reason").fill("Customer called to cancel");
  await page.getByTestId("confirm-cancel").click();
  await expect(detail).toContainText("Cancelled");
  await expect(detail).toContainText("Customer called to cancel");

  // Access token lives in memory only; a reload restores the session from the httpOnly refresh cookie.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Bookings" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("ADM-E2E-002: front-desk staff only see what their role allows", async ({ page, request }) => {
  const token = await ownerToken(request);
  const staff = { email: `desk-${Date.now()}@example.com`, password: "desk-e2e-password-0123" };
  const created = await request.post("/api/v1/admin/users", {
    headers: { Authorization: `Bearer ${token}` },
    data: { ...staff, name: "Front Desk", roles: ["STAFF"] },
  });
  expect(created.status()).toBe(201);

  await signIn(page, staff.email, staff.password);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Bookings" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Kiosks" })).toHaveCount(0);
  await page.goto("/kiosks");
  await expect(page.getByText("No access")).toBeVisible();
});
