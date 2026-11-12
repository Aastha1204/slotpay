import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import PrototypeDock from "@/components/PrototypeDock";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  manifest: "/manifest.webmanifest",
  title: "Glow Studio Salon & Spa · Book online in 60 seconds",
  description: "Book hair, skin, nails and spa appointments at Glow Studio, Thane West. Pick a slot, pay a small advance, get a WhatsApp confirmation.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {children}
        {process.env.NEXT_PUBLIC_PROTOTYPE === "1" && (
          <Suspense fallback={null}>
            <PrototypeDock />
          </Suspense>
        )}
      </body>
    </html>
  );
}
