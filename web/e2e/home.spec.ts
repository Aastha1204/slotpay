import { expect, test } from "@playwright/test";

async function noHorizontalScroll(page: import("@playwright/test").Page) {
  const w = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, i: window.innerWidth }));
  expect(w.s, `page is ${w.s}px wide in a ${w.i}px viewport`).toBeLessThanOrEqual(w.i);
}

test("front page renders real content, links to booking, and fits the phone", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Book your glow");
  await expect(page.getByText("What would you like today?")).toBeVisible();
  await expect(page.getByRole("link", { name: "Book an appointment" })).toHaveAttribute("href", "/b/glow-studio");
  await noHorizontalScroll(page);
  await page.getByRole("link", { name: "Book now" }).first().click();
  await expect(page.getByRole("heading", { name: "Choose a service" })).toBeVisible();
});

test("3D hero starts after load and every section is reachable (scroll reveal)", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("hero-3d")).toHaveAttribute("data-3d", "on", { timeout: 20_000 });
  await expect(page.getByTestId("hero-3d").locator("canvas")).toBeVisible();
  // scroll through the whole page like a visitor would; everything must end up revealed
  await page.evaluate(async () => {
    for (let y = 0; y < document.documentElement.scrollHeight; y += 350) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 140)); }
    window.scrollTo(0, document.documentElement.scrollHeight);
    await new Promise((r) => setTimeout(r, 900));
  });
  expect(await page.locator(".reveal").count()).toBeGreaterThan(8);
  await expect(page.locator(".reveal:not(.reveal-in)")).toHaveCount(0, { timeout: 5000 });
  for (const id of ["services", "how", "team", "visit"]) await expect(page.locator(`#${id}`)).toBeAttached();
  await noHorizontalScroll(page);
});

test("reduced motion keeps the static illustration and shows content immediately", async ({ browser }) => {
  const ctx = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 390, height: 800 } });
  const page = await ctx.newPage();
  await page.goto("/");
  await page.waitForTimeout(3500);
  await expect(page.getByTestId("hero-3d")).toHaveAttribute("data-3d", "off");
  await expect(page.getByTestId("hero-3d").locator("canvas")).toHaveCount(0);
  await expect(page.locator(".reveal")).toHaveCount(0);
  await ctx.close();
});
