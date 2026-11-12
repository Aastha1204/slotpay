"use client";
import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { API_BASE } from "@/lib/supabase";
import { AdminError, admin, getToken } from "@/lib/admin";
import { inr } from "../Sheets";

const field = "w-full rounded-xl border border-stone-300 bg-white p-3";
const primary = "rounded-xl bg-brand-700 px-4 py-3 font-semibold text-white disabled:opacity-50";
const errText = (e: unknown) => (e instanceof AdminError ? e.message : "Something went wrong");

type Settings = { name: string; address: string; phone: string; email: string; maps_url: string; hold_minutes: number; cancellation_cutoff_hours: number;
  min_lead_min: number; slot_step_min: number; max_advance_days: number; advance_applies: string; policy_text: string };
type Holiday = { id: string; date: string; reason: string };

export function SettingsTab() {
  const [s, setS] = useState<Settings | null>(null);
  const [hol, setHol] = useState<Holiday[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const [hd, setHd] = useState("");
  const [hr, setHr] = useState("");
  const load = useCallback(() => admin<{ settings: Settings; holidays: Holiday[] }>("/manage/settings").then((r) => { setS(r.settings); setHol(r.holidays); }).catch((e) => setMsg({ ok: false, t: errText(e) })), []);
  useEffect(() => { load(); }, [load]);
  if (!s) return <p className="text-stone-500">{msg?.t ?? "Loading…"}</p>;
  const set = (k: keyof Settings, v: string | number) => setS({ ...s, [k]: v });
  const num = (k: keyof Settings, label: string, hint?: string) => (
    <label className="text-sm">{label}<input className={field} type="number" value={s[k] as number} onChange={(e) => set(k, +e.target.value)} />{hint && <span className="text-xs text-stone-500">{hint}</span>}</label>);
  async function save(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try { await admin("/manage/settings", { method: "PATCH", body: JSON.stringify(s) }); setMsg({ ok: true, t: "Settings saved." }); } catch (e2) { setMsg({ ok: false, t: errText(e2) }); }
  }
  async function addHoliday() {
    if (!hd) return;
    try { await admin("/manage/holidays", { method: "POST", body: JSON.stringify({ date: hd, reason: hr }) }); setHd(""); setHr(""); load(); } catch (e) { setMsg({ ok: false, t: errText(e) }); }
  }
  return (
    <section className="space-y-6">
      <form onSubmit={save} className="space-y-4">
        <h2 className="text-lg font-semibold">Settings</h2>
        {msg && <p role="alert" className={`rounded-lg p-3 text-sm ${msg.ok ? "bg-emerald-50 text-emerald-900" : "bg-red-50 text-red-800"}`}>{msg.t}</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">Salon name<input className={field} value={s.name} onChange={(e) => set("name", e.target.value)} /></label>
          <label className="text-sm">Phone<input className={field} value={s.phone} onChange={(e) => set("phone", e.target.value)} /></label>
          <label className="text-sm">Email<input className={field} value={s.email} onChange={(e) => set("email", e.target.value)} /></label>
          <label className="text-sm">Maps link<input className={field} value={s.maps_url} onChange={(e) => set("maps_url", e.target.value)} /></label>
        </div>
        <label className="block text-sm">Address<input className={field} value={s.address} onChange={(e) => set("address", e.target.value)} /></label>
        <div className="grid gap-3 sm:grid-cols-3">
          {num("hold_minutes", "Slot hold (minutes)", "Unpaid holds release after this")}
          {num("cancellation_cutoff_hours", "Free cancellation until (hours before)")}
          {num("min_lead_min", "Minimum notice (minutes)")}
          {num("max_advance_days", "Book up to (days ahead)")}
          <label className="text-sm">Slot step (minutes)<select className={field} value={s.slot_step_min} onChange={(e) => set("slot_step_min", +e.target.value)}>{[5, 10, 15, 20, 30, 60].map((n) => <option key={n}>{n}</option>)}</select></label>
          <label className="text-sm">Advance applies<select className={field} value={s.advance_applies} onChange={(e) => set("advance_applies", e.target.value)}>
            <option value="always">Always</option><option value="weekends_and_holidays">Weekends and holidays only</option></select></label>
        </div>
        <label className="block text-sm">Cancellation policy text (shown before payment)<textarea className={field} rows={3} value={s.policy_text} onChange={(e) => set("policy_text", e.target.value)} /></label>
        <button className={primary}>Save settings</button>
      </form>
      <ResetDemo />
      <div>
        <h3 className="mb-2 font-semibold">Holidays</h3>
        <div className="flex flex-wrap gap-2"><input type="date" aria-label="Holiday date" className={`${field} w-44`} value={hd} onChange={(e) => setHd(e.target.value)} />
          <input aria-label="Holiday reason" placeholder="Reason" className={`${field} w-56`} value={hr} onChange={(e) => setHr(e.target.value)} />
          <button type="button" className="rounded-xl bg-white px-4 ring-1 ring-stone-300" onClick={addHoliday}>Add holiday</button></div>
        <ul className="mt-2 space-y-1 text-sm">{hol.map((h) => (
          <li key={h.id} className="flex justify-between rounded-xl bg-white p-3 ring-1 ring-stone-200"><span>{h.date} · {h.reason || "Closed"}</span>
            <button className="text-red-700 underline" onClick={async () => { await admin(`/manage/holidays/${h.id}`, { method: "DELETE" }); load(); }}>Remove</button></li>))}</ul>
      </div>
    </section>
  );
}

function ResetDemo() {
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<string | null>(null);
  async function reset() {
    if (!confirm("Reset ALL demo data? This deletes current bookings and customers and rebuilds a fresh, busy calendar.")) return;
    setBusy(true); setOut(null);
    try {
      const r = await admin<{ seconds: number; bookings: number }>("/demo/reset", { method: "POST" });
      setOut(`Demo reset in ${r.seconds}s · ${r.bookings} bookings`);
    } catch (e) { setOut(errText(e)); } finally { setBusy(false); }
  }
  return (
    <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4">
      <h3 className="font-semibold">Demo data</h3>
      <p className="mb-2 text-sm text-stone-600">Rebuilds the sample salon, customers and a busy calendar. Demo environments only.</p>
      <button type="button" onClick={reset} disabled={busy} className="rounded-xl bg-white px-4 py-3 font-medium ring-1 ring-amber-400 disabled:opacity-50">{busy ? "Resetting…" : "Reset demo data"}</button>
      {out && <p role="status" className="mt-2 text-sm">{out}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- reports
type Report = { from: string; to: string; kpis: Record<string, number>;
  services: { name: string; category: string; count: number; revenue_paise: number }[];
  staff: { name: string; booked_min: number; shift_min: number; utilisation: number; revenue_paise: number; completed: number }[];
  daily: { date: string; bookings: number; cancelled: number }[] };

const isoDay = (d: Date) => d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

export function ReportsTab() {
  const [to, setTo] = useState(() => isoDay(new Date()));
  const [from, setFrom] = useState(() => isoDay(new Date(Date.now() - 29 * 86400000)));
  const [r, setR] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    admin<Report>(`/reports?from=${from}&to=${to}`).then((x) => { setR(x); setErr(null); }).catch((e) => setErr(errText(e)));
  }, [from, to]);

  async function download(table: string) {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/admin/reports/export?table=${table}&from=${from}&to=${to}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { setErr("Export failed"); return; }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url; a.download = `slotpay-${table}-${from}-to-${to}.csv`; a.click();
    URL.revokeObjectURL(url);
  }
  const k = r?.kpis;
  const card = (label: string, v: string, sub?: string) => (
    <div className="rounded-2xl bg-white p-4 ring-1 ring-stone-200"><p className="text-xs text-stone-500">{label}</p><p className="text-2xl font-semibold">{v}</p>{sub && <p className="text-xs text-stone-500">{sub}</p>}</div>);
  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <h2 className="mr-auto text-lg font-semibold">Reports</h2>
        <label className="text-xs">From<input type="date" aria-label="Report from" className={field} value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label className="text-xs">To<input type="date" aria-label="Report to" className={field} value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <div className="flex gap-2 text-sm">{["summary", "services", "staff", "daily"].map((t) => <button key={t} onClick={() => download(t)} className="rounded-xl bg-white px-3 py-3 ring-1 ring-stone-300">CSV · {t}</button>)}</div>
      </div>
      {err && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{err}</p>}
      {k && r && (<>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="kpis">
          {card("Bookings", String(k.bookings), `${k.completed} completed`)}
          {card("Online advance collected", inr(k.online_advance_collected_paise), `${inr(k.refunded_paise)} refunded`)}
          {card("No-show rate", `${k.no_show_rate}%`, `${k.no_shows} no-shows`)}
          {card("Cancellation rate", `${k.cancellation_rate}%`, `${k.cancelled} cancelled`)}
        </div>
        <Panel title="Bookings per day"><ResponsiveContainer width="100%" height={220}><LineChart data={r.daily}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={11} /><YAxis allowDecimals={false} fontSize={11} /><Tooltip /><Legend />
          <Line type="monotone" dataKey="bookings" stroke="#0284c7" dot={false} name="Bookings" /><Line type="monotone" dataKey="cancelled" stroke="#a8a29e" dot={false} name="Cancelled" /></LineChart></ResponsiveContainer></Panel>
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title={`Revenue by service · ${inr(k.revenue_paise)} total`}><ResponsiveContainer width="100%" height={Math.max(220, r.services.length * 28)}>
            <BarChart data={r.services.map((s) => ({ ...s, revenue: s.revenue_paise / 100 }))} layout="vertical" margin={{ left: 60 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" fontSize={11} /><YAxis type="category" dataKey="name" width={130} fontSize={11} /><Tooltip formatter={(v) => `₹${Number(v).toLocaleString("en-IN")}`} /><Bar dataKey="revenue" fill="#0284c7" name="Revenue" /></BarChart></ResponsiveContainer></Panel>
          <Panel title="Staff utilisation (booked ÷ shift minutes)"><ResponsiveContainer width="100%" height={220}>
            <BarChart data={r.staff}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" fontSize={11} /><YAxis unit="%" fontSize={11} /><Tooltip formatter={(v) => `${v}%`} /><Bar dataKey="utilisation" fill="#0f766e" name="Utilisation" /></BarChart></ResponsiveContainer>
            <table className="mt-3 w-full text-sm"><thead className="text-left text-xs text-stone-500"><tr><th>Stylist</th><th>Utilisation</th><th>Completed</th><th className="text-right">Revenue</th></tr></thead>
              <tbody>{r.staff.map((s) => <tr key={s.name} className="border-t"><td className="py-1">{s.name}</td><td>{s.utilisation}%</td><td>{s.completed}</td><td className="text-right">{inr(s.revenue_paise)}</td></tr>)}</tbody></table></Panel>
        </div>
        <Panel title="Top services"><ol className="list-decimal pl-5 text-sm">{r.services.slice(0, 5).map((s) => <li key={s.name}>{s.name} · {s.count} · {inr(s.revenue_paise)}</li>)}</ol></Panel>
      </>)}
    </section>
  );
}

const Panel = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="rounded-2xl bg-white p-4 ring-1 ring-stone-200"><h3 className="mb-2 text-sm font-semibold">{title}</h3>{children}</div>);
