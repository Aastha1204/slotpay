"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AdminError, admin } from "@/lib/admin";
import { ServicesTab, StaffTab } from "./ServicesStaff";
import { ReportsTab, SettingsTab } from "./SettingsReports";

const TABS = [["services", "Services"], ["staff", "Staff & shifts"], ["settings", "Settings"], ["reports", "Reports"]] as const;

export default function Manage() {
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("services");
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    admin<{ role: string }>("/me").then((m) => setRole(m.role)).catch((e) => {
      if (e instanceof AdminError && e.status === 401) router.push("/admin/login");
      else setRole("error");
    });
  }, [router]);

  if (role === null) return <div className="p-6 text-stone-500">Loading…</div>;
  if (role !== "owner") {
    return (
      <main className="mx-auto max-w-md p-6 text-center">
        <h1 className="mb-2 text-xl font-semibold">Owner access only</h1>
        <p className="mb-4 text-stone-600">Services, pricing, settings and reports are available to the salon owner.</p>
        <Link href="/admin" className="underline">Back to calendar</Link>
      </main>
    );
  }
  return (
    <main className="min-h-screen bg-cream text-brand-900">
      <header className="sticky top-0 z-20 flex flex-wrap items-center gap-2 border-b bg-white/90 px-3 py-2 backdrop-blur">
        <Link href="/admin" className="rounded-lg px-3 py-2 ring-1 ring-stone-300">← Calendar</Link>
        <nav className="flex flex-wrap gap-1" role="tablist">
          {TABS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
              className={`rounded-lg px-3 py-2 text-sm ${tab === k ? "bg-brand-700 text-white" : "ring-1 ring-stone-300"}`}>{label}</button>
          ))}
        </nav>
      </header>
      <div className="mx-auto max-w-6xl p-4">
        {tab === "services" && <ServicesTab />}
        {tab === "staff" && <StaffTab />}
        {tab === "settings" && <SettingsTab />}
        {tab === "reports" && <ReportsTab />}
      </div>
    </main>
  );
}
