import { expect, test } from "@playwright/test";

// The whole product story in a real browser, against the prototype build (simulated payments + demo-speed reminders):
// book -> pay -> WhatsApp confirmation -> admin calendar shows it -> reminders arrive -> Cancel from WhatsApp -> refund.

test("book, pay, WhatsApp confirmation + reminders, calendar entry, cancel from WhatsApp", async ({ page, request }, testInfo) => {
  test.setTimeout(180_000);
  const sys = await (await request.get("/api/prototype/status")).json();
  test.skip(sys.payments !== "simulated" || !sys.reminder_demo_delay_sec, "needs a prototype API with simulated payments and demo-speed reminders");
  const delay: number = sys.reminder_demo_delay_sec;

  // --- customer books
  await page.goto("/b/glow-studio");
  await page.getByRole("button", { name: /Hair Spa/ }).click();
  await page.getByRole("button", { name: /Neha/ }).click();
  await expect(page.getByRole("gridcell")).not.toHaveCount(0);
  const days = page.getByRole("gridcell", { name: /\d+ times? available$/ });
  for (let i = 0; i < (await days.count()); i++) {
    await days.nth(i).click();
    const t = page.getByRole("button", { name: /^\d{1,2}:\d{2} (AM|PM)$/ }).first();
    if (await t.waitFor({ state: "visible", timeout: 9000 }).then(() => true, () => false)) { await t.click(); break; }
  }
  await expect(page.getByRole("heading", { name: "Your details" })).toBeVisible();
  const bookingDate = new URL(page.url()).searchParams.get("date")!;
  const phone = testInfo.project.name === "pixel-7" ? "9876500101" : "9876500102";
  await page.getByLabel("Full name").fill("E2E Tester");
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel("I agree to the cancellation policy").check();
  await page.getByRole("button", { name: "Hold my slot" }).click();
  await expect(page.getByText(/Slot held for/)).toBeVisible();
  await expect(page.getByText(/Simulated payment/)).toBeVisible();

  // --- simulated checkout: a failed test UPI keeps the slot, then success confirms
  await page.getByRole("button", { name: /Pay ₹/ }).click();
  const checkout = page.getByRole("dialog", { name: "Simulated checkout" });
  await checkout.getByLabel("UPI ID").fill("failure@razorpay");
  await checkout.getByRole("button", { name: /^Pay ₹/ }).click();
  await expect(checkout.getByRole("alert")).toContainText(/Payment failed/);
  await checkout.getByLabel("UPI ID").fill("success@razorpay");
  await checkout.getByRole("button", { name: /^Pay ₹/ }).click();

  // --- confirmation + WhatsApp confirmation arrives immediately
  await expect(page).toHaveURL(/\/confirm\//, { timeout: 20_000 });
  await expect(page.getByText(/You're booked, E2E!/)).toBeVisible({ timeout: 20_000 });
  const wa = page.getByLabel("Customer's WhatsApp (live)");
  await expect(wa.getByText(/is confirmed for/)).toBeVisible({ timeout: 15_000 });
  await expect(wa.getByText(/Advance paid: ₹200/)).toBeVisible();

  // --- the booking is on the admin calendar
  const login = await (await request.post("/api/prototype/login", { data: { role: "owner" } })).json();
  const cal = await (await request.get(`/api/admin/calendar?date=${bookingDate}`, { headers: { Authorization: `Bearer ${login.token}` } })).json();
  const mine = cal.bookings.find((b: { customer: string; status: string }) => b.customer === "E2E Tester");
  expect(mine, "booking should appear on the admin calendar").toBeTruthy();
  expect(mine.status).toBe("confirmed");
  expect(mine.advance_paid_paise).toBe(20000);

  // --- reminders arrive on WhatsApp by themselves
  await expect(wa.getByText(/is tomorrow at/)).toHaveCount(1, { timeout: (delay + 25) * 1000 });
  await expect(wa.getByText(/is in 2 hours at/)).toHaveCount(1, { timeout: (delay * 2 + 25) * 1000 });
  await expect(wa.getByRole("button", { name: "Reschedule" }).first()).toBeVisible();

  // --- tapping Cancel on WhatsApp cancels the booking and refunds the advance
  await wa.getByRole("button", { name: "Cancel" }).first().click();
  // two WhatsApp messages mention the refund: the "booking cancelled" template and the chat reply to the button
  await expect(wa.getByText(/refund has been initiated/)).toHaveCount(2, { timeout: 15_000 });
  await expect(page.getByText("This slot is no longer available")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/being refunded/)).toBeVisible();
});
