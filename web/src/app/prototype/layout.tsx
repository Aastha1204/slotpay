import type { Metadata } from "next";

export const metadata: Metadata = { title: "SlotPay prototype · everything in one place" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
