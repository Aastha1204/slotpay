// Every part of the prototype, grouped by who uses it. Shared by the floating dock and the /prototype hub.
export type Surface = { href: string; title: string; desc: string; tag: string; initial: string };
export type Group = { name: string; blurb: string; items: Surface[] };

export function surfaces(demoKey: string, phone: string | null): Group[] {
  const key = demoKey ? `key=${encodeURIComponent(demoKey)}` : "";
  const sim = `/demo/whatsapp?phone=${phone ?? "9811100001"}${key ? `&${key}` : ""}`;
  return [
    {
      name: "Customer", blurb: "What a salon customer sees on their phone.",
      items: [
        { href: "/", title: "Front page", desc: "Landing page with the 3D hero, services, team and location.", tag: "Public", initial: "H" },
        { href: "/b/glow-studio", title: "Online booking", desc: "Pick a service, stylist and time, then pay a small advance.", tag: "Public", initial: "B" },
        { href: "/b/glow-studio/terms", title: "Policy pages", desc: "Terms, privacy, refund and contact, generated from settings.", tag: "Public", initial: "P" },
      ],
    },
    {
      name: "Salon staff", blurb: "The owner's and front desk's day-to-day tools.",
      items: [
        { href: "/admin", title: "Admin calendar", desc: "Day and week calendar, live new bookings, walk-ins, reschedule, cancel and refund.", tag: "Owner + front desk", initial: "C" },
        { href: "/admin/manage", title: "Services, staff & reports", desc: "Prices, shifts, settings, holidays, revenue and utilisation reports with CSV export.", tag: "Owner only", initial: "R" },
      ],
    },
    {
      name: "Presenter", blurb: "For running the live sales demo.",
      items: [
        { href: `/demo${key ? `?${key}` : ""}`, title: "Presenter console", desc: "QR code, live event timeline, reminders, the 20-way double-booking test and reset.", tag: "Demo key", initial: "D" },
        { href: sim, title: "WhatsApp simulator", desc: "A WhatsApp-style chat showing every message, with working Cancel and Reschedule buttons.", tag: "Demo key", initial: "W" },
      ],
    },
  ];
}

export const WALKTHROUGH: { href: string; text: string }[] = [
  { href: "/b/glow-studio", text: "Book a slot as a customer (pick Hair Spa, then any stylist)." },
  { href: "/admin", text: "Watch it appear on the admin calendar. Try a walk-in, reschedule or cancel." },
  { href: "/demo", text: "Open the presenter console: the timeline shows every step under the hood." },
  { href: "/demo/whatsapp", text: "See the WhatsApp messages and tap Cancel on a reminder." },
  { href: "/admin/manage", text: "Owner view: change a price or open the reports." },
];
