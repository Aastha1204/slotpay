# SlotPay demo script (Glow Studio Salon & Spa, Thane West)

Total: about 3 minutes, plus an optional 30-second "under the hood" segment. Razorpay is in **test mode**: real UPI apps cannot pay a test order. Use the test UPI IDs below inside Checkout.

## Before the meeting (10 minutes ahead)
- [ ] Reset the demo: **Presenter console → Reset demo** (or Admin → Manage → Settings → *Reset demo data*, or `make reset-demo`). It rebuilds a busy calendar in a couple of seconds and leaves **next Saturday 4:00–5:00 PM with Neha** free.
- [ ] Open the API `/health` URL so a sleeping host is awake. In the Razorpay test dashboard, check that recent webhooks show **200**.
- [ ] Laptop: presenter console (`/demo?key=DEMO_KEY`) on one screen, admin calendar (`/admin`, signed in as the owner) on another. Phone: open the booking link.
- [ ] Practise the payment once: in Checkout choose **UPI**, enter `success@razorpay` (use `failure@razorpay` to show the retry state). If Razorpay changes its test methods, check its test-mode docs.
- [ ] WhatsApp: your own **verified** test number receives the real message. For a prospect's phone use the **simulator** on the laptop (button on the console), unless you added and verified their number earlier.
- [ ] Keep a screen recording of one good run as a backup.

## The 3-minute script

| Time | You say / do | What the audience sees |
|---|---|---|
| 0:00 | "Let me show you what *your* customers would see." Show the QR on the console; the owner scans it, or you send the link. | `/b/glow-studio` opens on their phone: salon name, "Open now", Call and Directions. |
| 0:20 | Pick **Hair Spa → Neha → next Saturday → 4:00 PM**. | Prices say "incl. GST", an advance chip shows ₹200, the full-month calendar shows how many times are free each day (green/amber/orange dots, "Full" and "Closed" days), with the times panel beside it. |
| 0:45 | Enter their name and number, tick the policy, tap **Hold my slot**. | "Slot held for 09:59" countdown. The cancellation policy was shown before payment. |
| 1:00 | Tap **Pay ₹200 advance**, choose UPI, enter `success@razorpay`. | Checkout opens; payment succeeds; "Confirming your payment…" then **You're booked**. |
| 1:25 | "Now look at your side." Switch to the **admin calendar**. | The booking slides in on Saturday under Neha, highlighted, with a toast: *New booking · … · Hair Spa · Sat 4:00 PM · ₹200 paid*. |
| 1:45 | Show the phone: the **WhatsApp confirmation** (or the simulator). | Message with service, time, advance paid, booking ID and a "View booking" button. |
| 2:00 | **Two phones, same slot.** Ask the owner to try the same Saturday 4:00 PM on a second phone. | The slot is gone; if they race you, "just taken" appears with a way back. |
| 2:25 | Open the booking in admin → **Cancel**. Read the policy line ("More than 4 h before: full ₹200 refund") → **Confirm**. | "Refund initiated", then **Refunded** when Razorpay's webhook arrives. The slot reopens on the booking page. |
| 2:50 | Close: "No-shows drop because the slot is paid for, and your reminders run themselves." | |

## 30-second "under the hood" (optional, for the technical owner)
1. On the **presenter console**, point at the live timeline: *slot held → Razorpay order created → checkout opened → signature verified → webhook payment.captured → booking confirmed → WhatsApp sent → reminders scheduled for …*. "Every step is logged; the booking only confirms after the server verifies the payment, never from the browser alone."
2. Tap **Run double-booking test**. 20 simultaneous requests fire for one slot; the console shows **"1 booked · 19 rejected by the database"**. "Double booking is impossible at the database level, not just in code."
3. Tap **Send 24 h reminder now**; show the reminder with Reschedule and Cancel buttons in the simulator. Tap **Cancel** there to show it works from WhatsApp too.

## If something goes wrong
| Symptom | Fix |
|---|---|
| The booking page spins or the API is silent | Open `/health` in a tab and wait ~30 s (free hosts sleep). Re-open the page. |
| Checkout won't open | Check the key id is a **test** key (`rzp_test_…`) and the "Test mode" badge shows. Reload the booking page and start again. |
| Payment succeeded but "Confirming…" stays | The webhook may be delayed. Wait up to 30 s, tap **Check again**. If it persists, the console timeline shows whether the webhook arrived; verify in Razorpay → Webhooks → recent deliveries. |
| `failure@razorpay` shows an error | That is the designed retry state; tap retry and use `success@razorpay`. |
| WhatsApp message doesn't arrive | Use the **simulator** button on the console (mirrors every message). Live sending only reaches numbers you added and verified in Meta's API Setup. |
| The Saturday slot is gone | Console → **Reset demo** (about 2 s). |
| Calendar looks stale or empty | Reset the demo, then reload `/admin`. |
| The network drops | Play the backup screen recording. |
