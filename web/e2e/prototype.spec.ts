import { expect, test } from "@playwright/test";

// These run against a prototype build (NEXT_PUBLIC_PROTOTYPE=1, API with PROTOTYPE_MODE=true): scripts/prototype.ps1 or .sh.

test("hub shows live data and links to every part of the prototype", async ({ page }) => {
  await page.goto("/prototype");
  await expect(page.getByRole("heading", { name: "Everything in one place." })).toBeVisible();
  await expect(page.getByText("API online")).toBeVisible();
  await expect(page.getByText("services", { exact: true })).toBeVisible();
  for (const title of ["Front page", "Online booking", "Admin calendar", "Services, staff & reports", "Presenter console", "WhatsApp simulator"]) {
    await expect(page.getByRole("link", { name: new RegExp(title) }).first()).toBeVisible();
  }
});

test("admin opens by itself (no token, no login form) and the dock switches roles", async ({ page }) => {
  await page.goto("/prototype");
  await page.evaluate(() => localStorage.clear());
  await page.getByRole("link", { name: /Admin calendar/ }).first().click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.locator("[data-testid^=booking-]").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("link", { name: "Manage" })).toBeVisible(); // owner

  await page.getByRole("button", { name: /Prototype/ }).click();
  await page.getByRole("dialog", { name: "Prototype navigation" }).getByRole("button", { name: "Front desk" }).click();
  await page.waitForLoadState("load");
  await expect(page.getByRole("link", { name: "Manage" })).toHaveCount(0, { timeout: 15_000 });
  await page.goto("/admin/manage");
  await expect(page.getByText("Owner access only")).toBeVisible();

  await page.goto("/prototype"); // leave the browser as the owner again
  await page.getByRole("button", { name: /Owner \(everything\)/ }).click();
});

test("owner can reach reports straight from the hub", async ({ page }) => {
  await page.goto("/prototype");
  await page.getByRole("button", { name: /Owner \(everything\)/ }).click();
  await page.getByRole("link", { name: /Services, staff & reports/ }).first().click();
  await expect(page.getByRole("tab", { name: "Reports" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("tab", { name: "Reports" }).click();
  await expect(page.getByTestId("kpis")).toContainText("Bookings", { timeout: 15_000 });
});

test("presenter console and WhatsApp simulator open without typing any key", async ({ page }) => {
  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: /Presenter console/ })).toBeVisible();
  await expect(page.getByTestId("booking-url")).toContainText("/b/glow-studio");
  await expect(page.locator("[role=alert]:not(#__next-route-announcer__)")).toHaveCount(0);
  await page.goto("/demo/whatsapp?phone=9999900001");
  await expect(page.getByText("Business account")).toBeVisible();
  await expect(page.getByText("Demo key required")).toHaveCount(0);
});

test("the dock is on customer pages too, and the API is only reached through /api", async ({ page }) => {
  const apiHosts = new Set<string>();
  page.on("request", (r) => { if (r.url().includes("/public/") || r.url().includes("/prototype/")) apiHosts.add(new URL(r.url()).origin); });
  await page.goto("/b/glow-studio");
  await expect(page.getByRole("button", { name: /Prototype/ })).toBeVisible();
  await page.getByRole("button", { name: /Hair Spa/ }).click();
  await expect(page.getByRole("heading", { name: "Choose a stylist" })).toBeVisible();
  const origin = new URL(page.url()).origin;
  expect([...apiHosts].every((h) => h === origin), `API calls left the site origin: ${[...apiHosts].join(", ")}`).toBe(true);
});
