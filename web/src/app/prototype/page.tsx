"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { LogoMark } from "@/components/art";
import { API_BASE } from "@/lib/supabase";
import { DEMO_KEY, PROTOTYPE, Role, currentRole, switchRole } from "@/lib/prototype";
import { WALKTHROUGH, surfaces } from "@/lib/surfaces";

type Status = { payments: string; whatsapp: string; reminder_demo_delay_sec: number; whatsapp_live_configured: boolean };
type Summary = { ready: boolean; name?: string; latest_phone: string | null; counts?: Record<string, number> };

export default function Hub() {
  const [sum, setSum] = useState<Summary | null>(null);
  const [sys, setSys] = useState<Status | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [role, setRole] = useState<Role>(() => currentRole());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch(`${API_BASE}/health`).then((r) => setApiOk(r.ok)).catch(() => setApiOk(false));
    fetch(`${API_BASE}/prototype/status`).then((r) => (r.ok ? r.json() : null)).then(setSys).catch(() => setSys(null));
    fetch(`${API_BASE}/prototype/summary`).then((r) => (r.ok ? r.json() : null)).then(setSum).catch(() => setSum(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function reset() {
    if (!confirm("Reset all demo data? Current bookings are replaced with a fresh, busy calendar.")) return;
    setBusy(true); setMsg(null);
    try {
      const r = await fetch(`${API_BASE}/demo/actions/reset?key=${encodeURIComponent(DEMO_KEY)}`, { method: "POST" });
      const j = await r.json();
      setMsg(r.ok ? `Demo reset in ${j.seconds}s · ${j.bookings} bookings` : (j.detail ?? "Reset failed"));
      load();
    } catch { setMsg("Reset failed"); } finally { setBusy(false); }
  }

  const groups = surfaces(DEMO_KEY, sum?.latest_phone ?? null);
  const c = sum?.counts;
  const stat = (n: number | undefined, label: string) => (
    <div className="rounded-2xl bg-white/80 px-4 py-3 ring-1 ring-brand-100"><p className="text-2xl font-extrabold tracking-tight text-brand-800">{n ?? "—"}</p><p className="text-xs font-medium text-slate-500">{label}</p></div>
  );

  return (
    <main className="bg-aurora min-h-screen text-brand-900">
      <div className="mx-auto max-w-5xl px-4 pb-24 pt-8">
        <header className="flex flex-wrap items-center gap-3">
          <LogoMark className="h-11 w-11" />
          <div className="mr-auto"><p className="font-extrabold tracking-tight">SlotPay prototype</p><p className="text-sm text-slate-500">{sum?.name ?? "Glow Studio Salon & Spa"} · Thane West</p></div>
          <span className={`rounded-full px-3 py-1 text-xs font-bold ${apiOk ? "bg-emerald-100 text-emerald-800" : apiOk === false ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-500"}`}>
            {apiOk === null ? "Checking…" : apiOk ? "API online" : "API offline"}
          </span>
        </header>

        <section className="mt-10">
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">Everything in one place.</h1>
          <p className="mt-3 max-w-2xl text-lg text-slate-600">Booking site, staff admin and the presenter tools all live on this one website. Open any of them from here, or from the <b>Prototype</b> button on every page.</p>
          {!PROTOTYPE && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Prototype mode is off in this build, so admin login and demo keys won&apos;t be filled in automatically.</p>}
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {stat(c?.services, "services")}{stat(c?.stylists, "stylists")}{stat(c?.upcoming_bookings, "upcoming bookings")}{stat(c?.customers, "customers")}
          </div>
        </section>

        {sys && (
          <section aria-label="How this prototype works" className="mt-8 rounded-3xl border border-line bg-white/80 p-5">
            <h2 className="text-lg font-extrabold tracking-tight">What is real in this prototype</h2>
            <ul className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
              <li className="rounded-2xl bg-brand-50 p-3"><b className="block">Payments: {sys.payments === "razorpay" ? "Razorpay test mode" : "simulated"}</b>{sys.payments === "razorpay" ? "Real Razorpay test orders, verification and refunds." : "A built-in checkout (success@razorpay / failure@razorpay) runs the same confirm, refund and audit code. Add Razorpay test keys to the API to use the real thing."}</li>
              <li className="rounded-2xl bg-brand-50 p-3"><b className="block">WhatsApp: {sys.whatsapp === "simulator" ? "simulator" : sys.whatsapp === "both" ? "live + simulator" : "live"}</b>{sys.whatsapp === "simulator" ? "Every message is generated and shown on a phone on the confirmation page and in the WhatsApp simulator. Sending to a real phone needs Meta WhatsApp Cloud API credentials (see README)." : sys.whatsapp_live_configured ? "Messages also go to real WhatsApp numbers you verified in Meta." : "Live mode selected but credentials are missing."}</li>
              <li className="rounded-2xl bg-brand-50 p-3"><b className="block">Reminders: {sys.reminder_demo_delay_sec > 0 ? `demo speed (${sys.reminder_demo_delay_sec}s / ${sys.reminder_demo_delay_sec * 2}s)` : "real schedule"}</b>{sys.reminder_demo_delay_sec > 0 ? "The 24 h and 2 h reminders arrive seconds after booking so you can watch them. Production uses the real appointment time." : "Sent 24 h and 2 h before the appointment."}</li>
            </ul>
          </section>
        )}

        {groups.map((g) => (
          <section key={g.name} className="mt-12">
            <h2 className="text-2xl font-extrabold tracking-tight">{g.name}</h2>
            <p className="text-slate-600">{g.blurb}</p>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              {g.items.map((s) => (
                <Link key={s.title} href={s.href} className="raise group flex flex-col rounded-3xl border border-line bg-white p-5">
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-100 text-lg font-extrabold text-brand-700">{s.initial}</span>
                  <h3 className="mt-4 text-lg font-bold tracking-tight">{s.title}</h3>
                  <p className="mt-1 flex-1 text-sm text-slate-600">{s.desc}</p>
                  <div className="mt-4 flex items-center justify-between text-sm"><span className="rounded-full bg-brand-50 px-2.5 py-1 text-xs font-bold text-brand-700">{s.tag}</span><span className="font-bold text-brand-700 transition group-hover:translate-x-1">Open →</span></div>
                </Link>
              ))}
            </div>
          </section>
        ))}

        <section className="mt-12 grid gap-4 md:grid-cols-2">
          <div className="rounded-3xl border border-line bg-white p-6">
            <h2 className="text-xl font-extrabold tracking-tight">3-minute walkthrough</h2>
            <ol className="mt-3 space-y-2">
              {WALKTHROUGH.map((w, i) => (
                <li key={w.href} className="flex gap-3 text-sm"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">{i + 1}</span>
                  <Link href={w.href === "/demo" || w.href === "/demo/whatsapp" ? surfaces(DEMO_KEY, sum?.latest_phone ?? null)[2].items[w.href === "/demo" ? 0 : 1].href : w.href} className="underline decoration-brand-300 underline-offset-2 hover:text-brand-700">{w.text}</Link></li>
              ))}
            </ol>
            <p className="mt-4 text-xs text-slate-500">Paying needs Razorpay test keys on the API. Without them, services with an advance can&apos;t complete payment.</p>
          </div>
          <div className="rounded-3xl border border-line bg-white p-6">
            <h2 className="text-xl font-extrabold tracking-tight">Controls</h2>
            <p className="mt-1 text-sm text-slate-600">Staff pages sign in automatically as:</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {(["owner", "front_desk"] as const).map((r) => (
                <button key={r} aria-pressed={role === r} onClick={async () => { if (await switchRole(r)) setRole(r); }}
                  className={`rounded-xl py-2.5 text-sm font-semibold ${role === r ? "bg-brand-700 text-white" : "bg-brand-50 ring-1 ring-brand-200"}`}>{r === "owner" ? "Owner (everything)" : "Front desk (limited)"}</button>
              ))}
            </div>
            <button onClick={reset} disabled={busy || !DEMO_KEY} className="mt-4 w-full rounded-xl border border-line bg-white py-2.5 text-sm font-semibold text-red-700 disabled:opacity-50">{busy ? "Resetting…" : "Reset demo data"}</button>
            {msg && <p role="status" className="mt-2 text-sm">{msg}</p>}
          </div>
        </section>
      </div>
    </main>
  );
}
