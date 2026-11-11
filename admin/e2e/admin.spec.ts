import { expect, test, type Page } from "@playwright/test";

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

test("ADM-E2E-001: owner books at the front desk, cancels, exports and erases the customer; session survives reload", async ({ page }) => {
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

  // Customer record: export (right of access), then erase (right to erasure) now nothing is upcoming.
  await detail.getByRole("link", { name: "Asha Verma" }).click();
  const customer = page.getByTestId("customer-detail");
  await expect(customer).toContainText("+919811122233");
  await expect(customer).toContainText("WhatsApp booking messages: Yes");
  const download = page.waitForEvent("download");
  await page.getByTestId("export-customer").click();
  expect((await download).suggestedFilename()).toMatch(/^customer-.*\.json$/);
  await page.getByTestId("anonymize-customer").click();
  await page.getByLabel("Reason").fill("Customer asked us to delete their data");
  await expect(page.getByTestId("confirm-anonymize")).toBeDisabled();
  await page.getByLabel("Type ANONYMIZE to confirm").fill("ANONYMIZE");
  await page.getByTestId("confirm-anonymize").click();
  await expect(customer).toContainText("Personal data was erased");
  await expect(customer).not.toContainText("9811122233");

  // Access token lives in memory only; a reload restores the session from the httpOnly refresh cookie.
  await page.reload();
  await expect(page.getByTestId("customer-detail")).toContainText("Personal data was erased"); // panel reopens from the URL
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("ADM-E2E-002: owner adds front-desk staff, who only see what their role allows; audit records it", async ({ page }) => {
  const staff = { email: `desk-${Date.now()}@example.com`, password: "desk-e2e-password-0123" };
  await signIn(page, OWNER.email, OWNER.password);
  await page.getByRole("link", { name: "Staff accounts" }).click();
  await page.getByTestId("add-user").click();
  await page.getByLabel("Name").fill("Front Desk");
  await page.getByLabel("Email (used to sign in)").fill(staff.email);
  await page.getByLabel("Front desk").check();
  await page.getByLabel("Temporary password").fill(staff.password);
  await page.getByTestId("save-user").click();
  await expect(page.getByTestId(`user-row-${staff.email}`)).toContainText("Front desk");

  await page.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByRole("cell", { name: "user.create" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, staff.email, staff.password);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Customers" })).toBeVisible();
  for (const hidden of ["Kiosks", "Staff accounts", "Audit log"]) {
    await expect(page.getByRole("link", { name: hidden })).toHaveCount(0);
  }
  await page.goto("/users");
  await expect(page.getByText("No access")).toBeVisible();
});
