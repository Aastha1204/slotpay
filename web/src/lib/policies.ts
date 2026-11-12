import type { Business } from "./booking";

export const PAGES = ["terms", "privacy", "refund", "contact"] as const;
export type PolicyPage = (typeof PAGES)[number];
export type Section = { h: string; p: string[] };

const REFUND_DAYS = "5–7 working days";

export function policy(page: PolicyPage, b: Business): { title: string; sections: Section[] } {
  const cutoff = b.cancellation_cutoff_hours;
  const contact = `${b.name}, ${b.address}. Phone: ${b.phone || "see our booking page"}. Email: ${b.email || "see our booking page"}.`;
  switch (page) {
    case "terms":
      return { title: "Terms of Service", sections: [
        { h: "Bookings", p: [`Bookings made on this page are appointments with ${b.name}. A slot is held for ${b.hold_minutes} minutes while you complete payment; unpaid holds are released automatically.`] },
        { h: "Prices and advance", p: ["All prices are shown in Indian Rupees (INR) and are inclusive of GST. An advance may be collected online to confirm your booking; the balance is payable at the salon after your service."] },
        { h: "Your responsibilities", p: ["Please arrive on time. If you are more than 15 minutes late we may need to shorten or reschedule your service.", "Provide a valid mobile number so we can send booking updates."] },
        { h: "Cancellation", p: [b.policy_text || `Free cancellation up to ${cutoff} hours before your appointment. Later cancellations forfeit the advance.`] },
        { h: "Contact", p: [contact] },
      ] };
    case "privacy":
      return { title: "Privacy Policy", sections: [
        { h: "What we collect", p: ["Your name, mobile number, and booking details (service, stylist, date and time). Payments are processed by Razorpay; we do not store your card, UPI or bank details."] },
        { h: "How we use it", p: ["To confirm and manage your appointment, to send booking confirmations and reminders (including on WhatsApp if you opt in), and to process refunds."] },
        { h: "Sharing", p: ["We share data only with service providers needed to run bookings and payments (such as Razorpay and our messaging provider). We do not sell personal data."] },
        { h: "Your choices", p: [`You can ask us to correct or delete your data, or stop WhatsApp updates, by contacting us. ${contact}`] },
      ] };
    case "refund":
      return { title: "Refund & Cancellation Policy", sections: [
        { h: "Free cancellation", p: [`Cancel at least ${cutoff} hours before your appointment and your advance is refunded in full to the original payment method.`] },
        { h: "Late cancellation and no-shows", p: [`Cancellations within ${cutoff} hours of the appointment, and no-shows, forfeit the advance.`] },
        { h: "If we cancel or the slot is unavailable", p: ["If we cancel, or your payment completes after the slot was taken by someone else, you receive a full refund automatically."] },
        { h: "Refund timelines", p: [`Refunds are initiated immediately and usually reach your account within ${REFUND_DAYS}, depending on your bank or UPI app.`] },
        { h: "How to cancel", p: ["Tap Cancel on your WhatsApp reminder, or contact us. " + contact] },
      ] };
    case "contact":
      return { title: "Contact Us", sections: [
        { h: b.name, p: [b.address, `Phone: ${b.phone || "—"}`, `Email: ${b.email || "—"}`] },
      ] };
  }
}
