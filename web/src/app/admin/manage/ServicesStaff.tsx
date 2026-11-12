"use client";
import { useCallback, useEffect, useState } from "react";
import { AdminError, admin } from "@/lib/admin";
import { Sheet, inr } from "../Sheets";

const field = "w-full rounded-xl border border-stone-300 bg-white p-3";
const primary = "rounded-xl bg-brand-700 px-4 py-3 font-semibold text-white disabled:opacity-50";
const ghost = "rounded-xl bg-white px-4 py-3 font-medium ring-1 ring-stone-300";
const errText = (e: unknown) => (e instanceof AdminError ? e.message : "Something went wrong");

type Svc = { id: string; category: string; name: string; description: string; duration_min: number; price_paise: number; advance_type: string; advance_value: number; buffer_min: number; is_active: boolean; sort_order: number };
type StaffRow = { id: string; name: string; title: string; bio: string; avatar_url: string; is_active: boolean; shift_template: Tpl; service_ids: string[] };
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
type Day = (typeof DAYS)[number];
type Win = { start: string; end: string };
type Tpl = Partial<Record<Day, Win[]>> & { breaks?: Partial<Record<Day, Win[]>> };

// ---------------------------------------------------------------- services
export function ServicesTab() {
  const [rows, setRows] = useState<Svc[]>([]);
  const [edit, setEdit] = useState<Partial<Svc> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => admin<{ services: Svc[] }>("/manage/services").then((r) => setRows(r.services)).catch((e) => setErr(errText(e))), []);
  useEffect(() => { load(); }, [load]);

  async function toggle(s: Svc) { await admin(`/manage/services/${s.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !s.is_active }) }).catch((e) => setErr(errText(e))); load(); }
  async function move(s: Svc, dir: -1 | 1) {
    const i = rows.findIndex((r) => r.id === s.id), o = rows[i + dir];
    if (!o) return;
    await Promise.all([admin(`/manage/services/${s.id}`, { method: "PATCH", body: JSON.stringify({ sort_order: o.sort_order }) }),
      admin(`/manage/services/${o.id}`, { method: "PATCH", body: JSON.stringify({ sort_order: s.sort_order }) })]).catch((e) => setErr(errText(e)));
    load();
  }
  async function del(s: Svc) {
    if (!confirm(`Delete "${s.name}"?`)) return;
    try { await admin(`/manage/services/${s.id}`, { method: "DELETE" }); setErr(null); } catch (e) { setErr(errText(e)); }
    load();
  }
  return (
    <section>
      <div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-semibold">Services &amp; pricing</h2>
        <button className={primary} onClick={() => setEdit({ category: "hair", duration_min: 30, price_paise: 50000, advance_type: "fixed", advance_value: 10000, buffer_min: 5, is_active: true, sort_order: rows.length + 1 })}>Add service</button></div>
      {err && <p role="alert" className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{err}</p>}
      <div className="overflow-x-auto rounded-2xl bg-white ring-1 ring-stone-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-stone-50 text-xs text-stone-500"><tr><th className="p-3">Service</th><th>Category</th><th>Min</th><th>Buffer</th><th>Price (incl. GST)</th><th>Advance</th><th>Active</th><th /></tr></thead>
          <tbody>
            {rows.map((s, i) => (
              <tr key={s.id} className={`border-t ${s.is_active ? "" : "opacity-50"}`}>
                <td className="p-3 font-medium">{s.name}</td><td className="capitalize">{s.category}</td><td>{s.duration_min}</td><td>{s.buffer_min}</td><td>{inr(s.price_paise)}</td>
                <td>{s.advance_type === "none" ? "—" : s.advance_type === "fixed" ? inr(s.advance_value) : `${s.advance_value}%`}</td>
                <td><input type="checkbox" aria-label={`Active ${s.name}`} className="h-5 w-5" checked={s.is_active} onChange={() => toggle(s)} /></td>
                <td className="space-x-2 whitespace-nowrap p-2 text-right">
                  <button aria-label="Move up" disabled={i === 0} onClick={() => move(s, -1)}>↑</button>
                  <button aria-label="Move down" disabled={i === rows.length - 1} onClick={() => move(s, 1)}>↓</button>
                  <button className="underline" onClick={() => setEdit(s)}>Edit</button>
                  <button className="text-red-700 underline" onClick={() => del(s)}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {edit && <ServiceForm initial={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </section>
  );
}

function ServiceForm({ initial, onClose, onSaved }: { initial: Partial<Svc>; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<Partial<Svc>>(initial);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof Svc, v: unknown) => setF((p) => ({ ...p, [k]: v }));
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    const body = { category: f.category, name: f.name, description: f.description ?? "", duration_min: f.duration_min, price_paise: f.price_paise,
      advance_type: f.advance_type, advance_value: f.advance_type === "none" ? 0 : f.advance_value, buffer_min: f.buffer_min, is_active: f.is_active, sort_order: f.sort_order };
    try {
      if (f.id) await admin(`/manage/services/${f.id}`, { method: "PATCH", body: JSON.stringify(body) });
      else await admin("/manage/services", { method: "POST", body: JSON.stringify(body) });
      onSaved();
    } catch (e2) { setErr(errText(e2)); } finally { setBusy(false); }
  }
  const pct = f.advance_type === "percent";
  return (
    <Sheet title={f.id ? "Edit service" : "New service"} onClose={onClose}>
      <form onSubmit={save} className="space-y-3">
        {err && <p role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-red-800">{err}</p>}
        <input className={field} placeholder="Name" aria-label="Name" value={f.name ?? ""} onChange={(e) => set("name", e.target.value)} required />
        <select className={field} aria-label="Category" value={f.category} onChange={(e) => set("category", e.target.value)}>{["hair", "skin", "nails", "spa"].map((c) => <option key={c}>{c}</option>)}</select>
        <div className="grid grid-cols-3 gap-2">
          <label className="text-xs">Duration (min)<input className={field} type="number" min={5} value={f.duration_min ?? 30} onChange={(e) => set("duration_min", +e.target.value)} /></label>
          <label className="text-xs">Buffer (min)<input className={field} type="number" min={0} value={f.buffer_min ?? 0} onChange={(e) => set("buffer_min", +e.target.value)} /></label>
          <label className="text-xs">Price ₹ (incl. GST)<input className={field} type="number" min={0} value={(f.price_paise ?? 0) / 100} onChange={(e) => set("price_paise", Math.round(+e.target.value * 100))} /></label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs">Advance<select className={field} value={f.advance_type} onChange={(e) => set("advance_type", e.target.value)}><option value="none">None</option><option value="fixed">Fixed ₹</option><option value="percent">Percent %</option></select></label>
          {f.advance_type !== "none" && <label className="text-xs">{pct ? "Percent" : "Amount ₹"}<input className={field} type="number" min={0} max={pct ? 100 : undefined}
            value={pct ? f.advance_value ?? 0 : (f.advance_value ?? 0) / 100} onChange={(e) => set("advance_value", pct ? +e.target.value : Math.round(+e.target.value * 100))} /></label>}
        </div>
        <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="h-5 w-5" checked={!!f.is_active} onChange={(e) => set("is_active", e.target.checked)} />Active (shown on the booking page)</label>
        <button className={`${primary} w-full`} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </form>
    </Sheet>
  );
}

// ---------------------------------------------------------------- staff + shifts + leave
export function StaffTab() {
  const [rows, setRows] = useState<StaffRow[]>([]);
  const [svcs, setSvcs] = useState<Svc[]>([]);
  const [leave, setLeave] = useState<{ id: string; staff: string; from: string; to: string; reason: string }[]>([]);
  const [edit, setEdit] = useState<StaffRow | "new" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => {
    admin<{ staff: StaffRow[] }>("/manage/staff").then((r) => setRows(r.staff)).catch((e) => setErr(errText(e)));
    admin<{ services: Svc[] }>("/manage/services").then((r) => setSvcs(r.services));
    admin<{ leave: typeof leave }>("/manage/leave").then((r) => setLeave(r.leave));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function del(s: StaffRow) {
    if (!confirm(`Delete ${s.name}?`)) return;
    try { await admin(`/manage/staff/${s.id}`, { method: "DELETE" }); setErr(null); } catch (e) { setErr(errText(e)); }
    load();
  }
  const summary = (s: StaffRow) => DAYS.filter((d) => (s.shift_template[d] ?? []).length).map((d) => `${d[0].toUpperCase()}${d.slice(1)} ${s.shift_template[d]![0].start}–${s.shift_template[d]![0].end}`);
  return (
    <section>
      <div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-semibold">Staff &amp; shifts</h2><button className={primary} onClick={() => setEdit("new")}>Add stylist</button></div>
      {err && <p role="alert" className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{err}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        {rows.map((s) => (
          <div key={s.id} className={`rounded-2xl bg-white p-4 ring-1 ring-stone-200 ${s.is_active ? "" : "opacity-50"}`}>
            <div className="flex justify-between"><div><p className="font-semibold">{s.name}</p><p className="text-sm text-stone-500">{s.title}</p></div>
              <div className="space-x-3 text-sm"><button className="underline" onClick={() => setEdit(s)}>Edit</button><button className="text-red-700 underline" onClick={() => del(s)}>Delete</button></div></div>
            <p className="mt-2 text-xs text-stone-600">{summary(s).join(" · ") || "No shifts"}</p>
            <p className="mt-1 text-xs text-stone-500">{s.service_ids.length} services</p>
          </div>
        ))}
      </div>
      <h3 className="mb-2 mt-6 font-semibold">Leave</h3>
      <LeaveForm staff={rows} onAdded={load} />
      <ul className="mt-2 space-y-1 text-sm">
        {leave.map((l) => (
          <li key={l.id} className="flex items-center justify-between rounded-xl bg-white p-3 ring-1 ring-stone-200">
            <span>{l.staff} · {l.from === l.to ? l.from : `${l.from} → ${l.to}`} · {l.reason}</span>
            <button className="text-red-700 underline" onClick={async () => { await admin(`/time-blocks/${l.id}`, { method: "DELETE" }); load(); }}>Remove</button></li>
        ))}
        {leave.length === 0 && <li className="text-stone-500">No upcoming leave.</li>}
      </ul>
      {edit && <StaffForm initial={edit === "new" ? null : edit} svcs={svcs} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </section>
  );
}

function LeaveForm({ staff, onAdded }: { staff: StaffRow[]; onAdded: () => void }) {
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  const [sid, setSid] = useState("");
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [reason, setReason] = useState("Leave");
  const [err, setErr] = useState<string | null>(null);
  async function add(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    try { await admin("/manage/leave", { method: "POST", body: JSON.stringify({ staff_id: sid || staff[0]?.id, from_date: from, to_date: to, reason }) }); onAdded(); }
    catch (e2) { setErr(errText(e2)); }
  }
  return (
    <form onSubmit={add} className="flex flex-wrap items-end gap-2">
      <select aria-label="Leave stylist" className={`${field} w-40`} value={sid || staff[0]?.id || ""} onChange={(e) => setSid(e.target.value)}>{staff.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
      <input aria-label="Leave from" type="date" className={`${field} w-40`} value={from} onChange={(e) => { setFrom(e.target.value); if (e.target.value > to) setTo(e.target.value); }} />
      <input aria-label="Leave to" type="date" className={`${field} w-40`} value={to} min={from} onChange={(e) => setTo(e.target.value)} />
      <input aria-label="Leave reason" className={`${field} w-44`} value={reason} onChange={(e) => setReason(e.target.value)} />
      <button className={ghost}>Add leave</button>
      {err && <p role="alert" className="w-full text-sm text-red-700">{err}</p>}
    </form>
  );
}

function StaffForm({ initial, svcs, onClose, onSaved }: { initial: StaffRow | null; svcs: Svc[]; onClose: () => void; onSaved: () => void }) {
  const base: Tpl = Object.fromEntries(DAYS.map((d) => [d, d === "sun" ? [] : [{ start: "10:00", end: "20:00" }]])) as Tpl;
  const [f, setF] = useState({ name: initial?.name ?? "", title: initial?.title ?? "", bio: initial?.bio ?? "", is_active: initial?.is_active ?? true });
  const [tpl, setTpl] = useState<Tpl>(initial?.shift_template && Object.keys(initial.shift_template).length ? initial.shift_template : base);
  const [ids, setIds] = useState<string[]>(initial?.service_ids ?? []);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const win = (d: Day) => tpl[d]?.[0];
  const brk = (d: Day) => tpl.breaks?.[d]?.[0];
  const setWin = (d: Day, w: Win | null) => setTpl((t) => ({ ...t, [d]: w ? [w] : [] }));
  const setBrk = (d: Day, w: Win | null) => setTpl((t) => ({ ...t, breaks: { ...(t.breaks ?? {}), [d]: w ? [w] : [] } }));
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    const body = { ...f, shift_template: tpl, service_ids: ids };
    try {
      if (initial) await admin(`/manage/staff/${initial.id}`, { method: "PATCH", body: JSON.stringify(body) });
      else await admin("/manage/staff", { method: "POST", body: JSON.stringify(body) });
      onSaved();
    } catch (e2) { setErr(errText(e2)); } finally { setBusy(false); }
  }
  const time = "rounded-lg border border-stone-300 bg-white p-2 text-sm";
  return (
    <Sheet title={initial ? `Edit ${initial.name}` : "New stylist"} onClose={onClose}>
      <form onSubmit={save} className="space-y-3">
        {err && <p role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-red-800">{err}</p>}
        <input className={field} placeholder="Name" aria-label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
        <input className={field} placeholder="Title (e.g. Senior Stylist)" aria-label="Title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
        <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="h-5 w-5" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />Active</label>
        <div><p className="mb-1 text-sm font-medium">Services performed</p>
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">{svcs.map((s) => (
            <label key={s.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ids.includes(s.id)} onChange={(e) => setIds(e.target.checked ? [...ids, s.id] : ids.filter((x) => x !== s.id))} />{s.name}</label>))}</div></div>
        <div><p className="mb-1 text-sm font-medium">Weekly shifts and breaks</p>
          <div className="space-y-2">{DAYS.map((d) => (
            <div key={d} className="flex flex-wrap items-center gap-2 text-sm">
              <label className="flex w-16 items-center gap-2 capitalize"><input type="checkbox" checked={!!win(d)} onChange={(e) => setWin(d, e.target.checked ? { start: "10:00", end: "20:00" } : null)} />{d}</label>
              {win(d) ? <>
                <input type="time" aria-label={`${d} start`} className={time} value={win(d)!.start} onChange={(e) => setWin(d, { ...win(d)!, start: e.target.value })} />–
                <input type="time" aria-label={`${d} end`} className={time} value={win(d)!.end} onChange={(e) => setWin(d, { ...win(d)!, end: e.target.value })} />
                <span className="text-xs text-stone-500">Break</span>
                <input type="time" aria-label={`${d} break start`} className={time} value={brk(d)?.start ?? ""} onChange={(e) => setBrk(d, e.target.value ? { start: e.target.value, end: brk(d)?.end ?? e.target.value } : null)} />–
                <input type="time" aria-label={`${d} break end`} className={time} value={brk(d)?.end ?? ""} onChange={(e) => brk(d) && setBrk(d, { ...brk(d)!, end: e.target.value })} />
              </> : <span className="text-stone-400">Day off</span>}
            </div>))}</div></div>
        <button className={`${primary} w-full`} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
      </form>
    </Sheet>
  );
}
