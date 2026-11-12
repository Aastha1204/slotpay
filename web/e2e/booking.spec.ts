import { expect, Page, test } from "@playwright/test";

const RZP_STUB = `
window.Razorpay = function (o) {
  window.__rzp = o;
  this.on = function (ev, cb) { window.__rzpHandlers = window.__rzpHandlers || {}; window.__rzpHandlers[ev] = cb; };
  this.open = function () {
    window.__opened = true;
    if (window.__dismissAfter) setTimeout(function () { o.modal.ondismiss(); }, window.__dismissAfter);
  };
};`;

async function stubCheckoutScript(page: Page) {
  await page.route("https://checkout.razorpay.com/v1/checkout.js", (r) => r.fulfill({ contentType: "application/javascript", body: RZP_STUB }));
}

function hold(expiresInMs = 9 * 60_000, extra: Record<string, unknown> = {}) {
  return {
    status: 201, contentType: "application/json",
    body: JSON.stringify({
      booking_id: "11111111-1111-1111-1111-111111111111", public_token: "tok_e2e", staff_id: "s1",
      hold_expires_at: new Date(Date.now() + expiresInMs).toISOString(), status: "held", advance_paise: 20000,
      order: { order_id: "order_e2e", key_id: "rzp_test_e2e", amount_paise: 20000 }, ...extra,
    }),
  };
}

async function noHorizontalScroll(page: Page) {
  const w = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, i: window.innerWidth }));
  expect(w.s, `page is ${w.s}px wide in a ${w.i}px viewport`).toBeLessThanOrEqual(w.i);
}

/** service -> stylist -> first open date -> first open time -> details form, stopping before "Hold my slot". */
async function reachDetails(page: Page) {
  await page.goto("/b/glow-studio");
  await expect(page.getByRole("heading", { name: "Choose a service" })).toBeVisible();
  await noHorizontalScroll(page);
  await page.getByRole("button", { name: /Hair Spa/ }).click();
  await expect(page.getByRole("heading", { name: "Choose a stylist" })).toBeVisible();
  await page.getByRole("button", { name: /Neha/ }).click();
  await expect(page.getByRole("heading", { name: "Pick a date & time" })).toBeVisible();
  await noHorizontalScroll(page);
  await expect(page.getByRole("gridcell")).not.toHaveCount(0); // the month calendar has rendered
  const day = page.getByRole("gridcell", { name: /\d+ times? available$/ }); // only days that have free times
  await day.first().waitFor();
  const n = await day.count();
  for (let i = 0; i < n; i++) {
    await day.nth(i).click();
    const time = page.getByRole("button", { name: /^\d{1,2}:\d{2} (AM|PM)$/ }).first();
    const ok = await time.waitFor({ state: "visible", timeout: 9000 }).then(() => true, () => false);
    if (ok) { await time.click(); break; }
  }
  await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();
  await noHorizontalScroll(page);
  await page.getByLabel("Full name").fill("Priya Sharma");
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByLabel("I agree to the cancellation policy").check();
}

test("happy path reaches Razorpay Checkout with the right order and prefill", async ({ page }) => {
  await stubCheckoutScript(page);
  const scripts: string[] = [];
  page.on("request", (r) => { if (r.url().includes("razorpay")) scripts.push(r.url()); });
  await page.route("**/public/glow-studio/holds", (r) => (r.request().method() === "POST" ? r.fulfill(hold()) : r.continue()));
  await page.route("**/checkout-opened", (r) => r.fulfill({ json: { ok: true } }));
  await reachDetails(page);
  expect(scripts, "Checkout.js must not load before the pay step").toHaveLength(0);
  await page.getByRole("button", { name: "Hold my slot" }).click();
  await expect(page.getByText(/Slot held for \d\d:\d\d/)).toBeVisible();
  await expect(page.getByText("Test mode")).toBeVisible();
  await expect(page.getByText("₹1,000 incl. GST").first().or(page.getByText(/incl\. GST/).first())).toBeVisible();
  await noHorizontalScroll(page);
  await page.getByRole("button", { name: /Pay ₹200 advance/ }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { __opened?: boolean }).__opened)).toBe(true);
  const o = await page.evaluate(() => (window as unknown as { __rzp: Record<string, unknown> }).__rzp);
  expect(o.order_id).toBe("order_e2e");
  expect(o.amount).toBe(20000);
  expect((o.prefill as { contact: string }).contact).toBe("+919876543210");
  expect((o.retry as { enabled: boolean }).enabled).toBe(true);
  expect(o.timeout as number).toBeLessThan(9 * 60);
});

test("slot taken (409) returns to the time step with a clear message", async ({ page }) => {
  await page.route("**/public/glow-studio/holds", (r) => (r.request().method() === "POST"
    ? r.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: "SLOT_TAKEN", message: "That slot was just taken. Please pick another time." }) })
    : r.continue()));
  await reachDetails(page);
  await page.getByRole("button", { name: "Hold my slot" }).click();
  await expect(page.locator("[role=alert]:not(#__next-route-announcer__)")).toContainText(/just taken/i);
  await expect(page.getByRole("heading", { name: "Pick a date & time" })).toBeVisible();
  await noHorizontalScroll(page);
});

test("hold expiring during payment shows a designed expired state", async ({ page }) => {
  await stubCheckoutScript(page);
  await page.route("**/public/glow-studio/holds", (r) => (r.request().method() === "POST" ? r.fulfill(hold(3000)) : r.continue()));
  await reachDetails(page);
  await page.getByRole("button", { name: "Hold my slot" }).click();
  await expect(page.getByText(/Slot held for/)).toBeVisible();
  await expect(page.getByText("Your slot hold expired. Please choose a time again.")).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Pick another time" }).click();
  await expect(page.getByRole("heading", { name: "Pick a date & time" })).toBeVisible();
});

test("closing Checkout releases the hold and says so", async ({ page }) => {
  await stubCheckoutScript(page);
  await page.addInitScript(() => { (window as unknown as { __dismissAfter: number }).__dismissAfter = 100; });
  let released = false;
  await page.route("**/public/glow-studio/holds", (r) => (r.request().method() === "POST" ? r.fulfill(hold()) : r.continue()));
  await page.route("**/checkout-opened", (r) => r.fulfill({ json: { ok: true } }));
  await page.route("**/public/holds/*/release", (r) => { released = true; return r.fulfill({ json: { released: true } }); });
  await reachDetails(page);
  await page.getByRole("button", { name: "Hold my slot" }).click();
  await page.getByRole("button", { name: /Pay ₹200 advance/ }).click();
  await expect(page.locator("[role=alert]:not(#__next-route-announcer__)")).toContainText(/cancelled and your slot was released/i);
  expect(released).toBe(true);
  await expect(page.getByRole("heading", { name: "Pick a date & time" })).toBeVisible();
});

test("confirmation page shows a calm waiting state, then success", async ({ page }) => {
  let calls = 0;
  const view = (status: string) => ({
    booking_id: "11111111-1111-1111-1111-111111111111", status, service: "Hair Spa", stylist: "Neha",
    start: "2026-11-14T16:00:00+05:30", end: "2026-11-14T17:00:00+05:30", price_paise: 120000, advance_paid_paise: status === "confirmed" ? 20000 : 0,
    balance_paise: status === "confirmed" ? 100000 : 120000, payment_status: null, refunded_paise: 0, hold_expires_at: null,
    masked_phone: "+91 98xxxxx210", whatsapp_sent: status === "confirmed", customer_first_name: "Priya", cancellation_cutoff_hours: 4,
    business: { name: "Glow Studio Salon & Spa", address: "Thane West", maps_url: "https://maps.example", slug: "glow-studio" },
  });
  await page.route("**/public/bookings/tok_e2e", (r) => { calls += 1; return r.fulfill({ json: view(calls < 3 ? "held" : "confirmed") }); });
  await page.goto("/b/glow-studio/confirm/tok_e2e");
  await expect(page.getByText("Confirming your payment…")).toBeVisible();
  await expect(page.getByText("You're booked, Priya!")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Balance at the salon")).toBeVisible();
  await expect(page.getByText(/WhatsApp confirmation sent to \+91 98xxxxx210/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Add to calendar" })).toBeVisible();
  await noHorizontalScroll(page);
});

test("a network error while loading stylists is recoverable", async ({ page }) => {
  await page.route("**/public/glow-studio/stylists*", (r) => r.abort());
  await page.goto("/b/glow-studio");
  await page.getByRole("button", { name: /Hair Spa/ }).click();
  await expect(page.locator("[role=alert]:not(#__next-route-announcer__)")).toContainText(/couldn't reach the server/i);
  await noHorizontalScroll(page);
  await page.unroute("**/public/glow-studio/stylists*");
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("button", { name: /Any available/ })).toBeVisible();
});


test("date step shows a full month calendar with availability and a times panel", async ({ page }) => {
  await page.goto("/b/glow-studio");
  await page.getByRole("button", { name: /Hair Spa/ }).click();
  await page.getByRole("button", { name: /Neha/ }).click();
  await expect(page.getByRole("heading", { name: "Pick a date & time" })).toBeVisible();
  const grid = page.getByRole("grid", { name: "Choose a date" });
  await expect(grid).toBeVisible();
  await expect(grid.getByRole("columnheader")).toHaveText(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
  await expect(page.getByRole("gridcell").first()).toBeVisible();
  expect(await page.getByRole("gridcell").count()).toBeGreaterThan(28); // about five weeks, not a 14-day strip
  await expect(page.getByText("Choose a day on the calendar")).toBeVisible();
  await noHorizontalScroll(page);
  const open = page.getByRole("gridcell", { name: /\d+ times? available$/ });
  await expect(open.first()).toBeVisible();
  await open.first().click();
  await expect(open.first()).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: /^\d{1,2}:\d{2} (AM|PM)$/ }).first()).toBeVisible();
  await expect(page.getByText(/times · IST/)).toBeVisible();
  await noHorizontalScroll(page);
});
