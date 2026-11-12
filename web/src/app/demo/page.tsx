"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { QRCodeSVG } from "qrcode.react";
import { DEMO_KEY } from "@/lib/prototype";
import { API_BASE } from "@/lib/supabase";

type State = { slug: string; name: string; booking_url: string; active_holds: number; latest: { booking_id: string; status: string; name: string; phone: string } | null };
type Ev = { id: string; type: string; text: string; at: string };
type Result = { title: string; lines: string[]; big?: string };

const hm = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit", second: "2-digit", hour12: true });
const ICON: Record<string, string> = {
  slot_held: "🔒", razorpay_order_created: "🧾", checkout_opened: "📱", signature_verified: "✅", webhook_payment_captured: "🪝", booking_confirmed: "🎉",
  whatsapp_sent: "💬", messages_scheduled: "⏰", hold_expired: "⌛", hold_released: "↩️", booking_cancelled: "✖️", refund_initiated: "💸", double_booking_test: "⚔️", demo_reset: "♻️",
};

export default function Page() {
  return <Suspense fallback={<div className="p-6 text-stone-500">Loading…</div>}><Console /></Suspense>;
}

function Console() {
  const sp = useSearchParams();
  const key = sp.get("key") || DEMO_KEY;
  const [st, setSt] = useState<State | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [res, setRes] = useState<Result | null>(null);
  const [copied, setCopied] = useState(false);

  const call = useCallback(async (path: string, init?: RequestInit) => {
    const r = await fetch(`${API_BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", "x-demo-key": key, ...(init?.headers ?? {}) } });
    if (r.status === 403) throw new Error("Demo key missing or wrong. Open this page with ?key=YOUR_DEMO_KEY");
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? "Request failed");
    return r.json();
  }, [key]);

  const refresh = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([call("/demo/state"), call("/demo/timeline?limit=40")]);
      setSt(s); setEvents(t.events); setError(null);
    } catch (e) { setError((e as Error).message); }
  }, [call]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { refresh(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, [refresh]);

  async function run(label: string, path: string, body: unknown, show: (r: Record<string, unknown>) => Result) {
    if (busy) return;
    setBusy(label); setRes(null);
    try { setRes(show(await call(path, { method: "POST", body: JSON.stringify(body ?? {}) }))); refresh(); }
    catch (e) { setRes({ title: label, lines: [(e as Error).message] }); }
    finally { setBusy(null); }
  }
  const btn = "rounded-xl bg-white px-4 py-3 text-left text-sm font-medium ring-1 ring-stone-300 active:bg-brand-50 disabled:opacity-50";
  const base = typeof window !== "undefined" ? window.location.origin : "";
  const simUrl = st?.latest ? `${base}/demo/whatsapp?phone=${st.latest.phone}&key=${encodeURIComponent(key)}` : null;

  return (
    <main className="mx-auto min-h-screen max-w-6xl bg-cream p-4 text-brand-900">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="tracking-tight text-2xl font-semibold">SlotPay · Presenter console</h1>
        <span className="text-sm text-stone-500">{st ? `${st.name} · ${st.active_holds} active hold${st.active_holds === 1 ? "" : "s"}` : ""}</span>
      </header>
      {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <div className="rounded-2xl bg-white p-4 text-center ring-1 ring-stone-200">
            {st ? <QRCodeSVG value={st.booking_url} size={200} className="mx-auto" /> : <div className="mx-auto h-[200px] w-[200px] animate-pulse rounded bg-stone-200" />}
            <p className="mt-2 break-all text-sm" data-testid="booking-url">{st?.booking_url}</p>
            <button className="mt-2 text-sm underline" onClick={() => { navigator.clipboard?.writeText(st?.booking_url ?? ""); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? "Copied" : "Copy link"}</button>
          </div>
          <div className="grid gap-2">
            <a className={btn} href="/admin" target="_blank" rel="noreferrer">Open admin calendar ↗</a>
            {simUrl ? <a className={btn} href={simUrl} target="_blank" rel="noreferrer">WhatsApp simulator · {st?.latest?.name} ↗</a> : <span className={`${btn} opacity-50`}>WhatsApp simulator (after the first booking)</span>}
          </div>
          <div className="grid gap-2">
            <button className={btn} disabled={!!busy} onClick={() => run("24 h reminder", "/demo/actions/send-reminder", { kind: "remind_24h" }, (r) => ({ title: "24 h reminder", lines: [`Sent ${r.sent} message(s) to the latest booking`] }))}>Send 24 h reminder now</button>
            <button className={btn} disabled={!!busy} onClick={() => run("2 h reminder", "/demo/actions/send-reminder", { kind: "remind_2h" }, (r) => ({ title: "2 h reminder", lines: [`Sent ${r.sent} message(s) to the latest booking`] }))}>Send 2 h reminder now</button>
            <button className={btn} disabled={!!busy} onClick={() => run("Expire holds", "/demo/actions/expire-holds", {}, (r) => ({ title: "Holds expired", lines: [`${r.expired} hold(s) released`] }))}>Expire all holds now</button>
            <button className={btn} disabled={!!busy} onClick={() => run("Double-booking test", "/demo/actions/double-booking-test", {}, (r) => ({ title: "Double-booking test", big: String(r.summary), lines: [`${r.attempts} simultaneous requests for ${r.slot}`, `Finished in ${r.elapsed_ms} ms. The exclusion constraint in Postgres decided, not application code.`] }))}>{busy === "Double-booking test" ? "Running 20 simultaneous requests…" : "Run double-booking test"}</button>
            <button className={`${btn} text-red-700`} disabled={!!busy} onClick={() => { if (confirm("Reset all demo data?")) run("Reset demo", "/demo/actions/reset", {}, (r) => ({ title: "Demo reset", lines: [`Rebuilt ${r.bookings} bookings in ${r.seconds}s`] })); }}>{busy === "Reset demo" ? "Resetting…" : "Reset demo"}</button>
          </div>
          {res && (
            <div role="status" className="rounded-2xl bg-white p-4 ring-1 ring-stone-200" data-testid="result">
              <p className="text-xs text-stone-500">{res.title}</p>
              {res.big && <p className="my-1 text-2xl font-semibold text-brand-700">{res.big}</p>}
              {res.lines.map((l, i) => <p key={i} className="text-sm">{l}</p>)}
            </div>
          )}
        </div>
        <section aria-label="Live event timeline" className="rounded-2xl bg-white p-4 ring-1 ring-stone-200">
          <h2 className="mb-3 font-semibold">Under the hood · live</h2>
          <ol className="space-y-2" data-testid="timeline">
            {events.map((e) => (
              <li key={e.id} className="flex gap-3 text-sm"><span className="w-6 text-center">{ICON[e.type] ?? "•"}</span>
                <span className="flex-1">{e.text}</span><span className="shrink-0 text-xs text-stone-400">{hm(e.at)}</span></li>
            ))}
            {events.length === 0 && <li className="text-sm text-stone-500">Waiting for the first booking…</li>}
          </ol>
        </section>
      </div>
    </main>
  );
}
