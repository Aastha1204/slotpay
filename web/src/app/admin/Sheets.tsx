"use client";
import { useEffect, useState } from "react";
import { AdminError, CalStaff, Calendar, Detail, admin } from "@/lib/admin";

export const inr = (p: number) => `₹${(p / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
export const hm = (iso: string) => {
  const h = +iso.slice(11, 13), m = iso.slice(14, 16);
  return `${h % 12 || 12}:${m} ${h < 12 ? "AM" : "PM"}`;
};
export const dayLabel = (iso: string) =>
  new Date(`${iso.slice(0, 10)}T00:00:00+05:30`).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short" });

const field = "w-full rounded-xl border border-stone-300 bg-white p-3 text-base";
const primary = "w-full rounded-xl bg-brand-700 px-4 py-3 font-semibold text-white disabled:opacity-50";
const ghost = "w-full rounded-xl bg-white px-4 py-3 font-medium ring-1 ring-stone-300 disabled:opacity-50";

export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-brand-900/40 sm:items-center" onClick={onClose}>
      <div role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}
        className="animate-step max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-cream p-5 shadow-xl sm:rounded-3xl">
        <div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="px-2 text-2xl leading-none text-stone-500">×</button></div>
        {children}
      </div>
    </div>
  );
}

const Err = ({ msg }: { msg: string | null }) => (msg ? <p role="alert" className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-800">{msg}</p> : null);

// ---------------------------------------------------------------- cell action choice
export function CellSheet({ staff, startIso, onClose, onPick }: { staff: CalStaff; startIso: string; onClose: () => void; onPick: (k: "booking" | "block") => void }) {
  return (
    <Sheet title={`${staff.name} · ${dayLabel(startIso)} · ${hm(startIso)}`} onClose={onClose}>
      <div className="space-y-2">
        <button className={primary} onClick={() => onPick("booking")}>Add walk-in / phone booking</button>
        <button className={ghost} onClick={() => onPick("block")}>Block time (break or leave)</button>
      </div>
    </Sheet>
  );
}

// ---------------------------------------------------------------- quick add
export function QuickAdd({ cal, staff, startIso, onClose, onDone }: { cal: Calendar; staff: CalStaff; startIso: string; onClose: () => void; onDone: (id: string) => void }) {
  const svcs = cal.services.filter((s) => staff.service_ids.includes(s.id));
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [svc, setSvc] = useState(svcs[0]?.id ?? "");
  const [source, setSource] = useState("walk_in");
  const [matches, setMatches] = useState<{ id: string; name: string; phone: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (phone.length < 3) return;
    const t = setTimeout(() => admin<{ customers: typeof matches }>(`/customers/search?q=${encodeURIComponent(phone)}`).then((r) => setMatches(r.customers)).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [phone]);

  const valid = /^[6-9]\d{9}$/.test(phone) && name.trim() && svc;
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true); setErr(null);
    try {
      const r = await admin<{ booking_id: string }>("/bookings", { method: "POST", body: JSON.stringify({ service_id: svc, staff_id: staff.id, start: startIso, name, phone, source }) });
      onDone(r.booking_id);
    } catch (e2) { setErr(e2 instanceof AdminError ? e2.message : "Failed"); } finally { setBusy(false); }
  }
  return (
    <Sheet title={`New booking · ${staff.name} · ${hm(startIso)}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Err msg={err} />
        <div className="relative">
          <input className={field} inputMode="numeric" maxLength={10} placeholder="Customer mobile (10 digits)" value={phone}
            onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} aria-label="Customer mobile" />
          {phone.length >= 3 && matches.length > 0 && phone.length < 10 && (
            <ul className="absolute z-10 mt-1 w-full rounded-xl bg-white shadow ring-1 ring-stone-200">
              {matches.map((m) => (
                <li key={m.id}><button type="button" className="w-full p-3 text-left text-sm hover:bg-brand-50"
                  onClick={() => { setPhone(m.phone.slice(-10)); setName(m.name); setMatches([]); }}>{m.name} · {m.phone}</button></li>
              ))}
            </ul>
          )}
        </div>
        <input className={field} placeholder="Customer name" value={name} onChange={(e) => setName(e.target.value)} aria-label="Customer name" />
        <select className={field} value={svc} onChange={(e) => setSvc(e.target.value)} aria-label="Service">
          {svcs.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.duration_min} min · {inr(s.price_paise)}</option>)}
        </select>
        <div className="flex gap-2">
          {(["walk_in", "phone"] as const).map((k) => (
            <button type="button" key={k} onClick={() => setSource(k)}
              className={`flex-1 rounded-xl py-3 text-sm font-medium ${source === k ? "bg-brand-700 text-white" : "bg-white ring-1 ring-stone-300"}`}>{k === "walk_in" ? "Walk-in" : "Phone"}</button>
          ))}
        </div>
        <p className="text-xs text-stone-500">No online payment. Balance is collected at the salon.</p>
        <button className={primary} disabled={!valid || busy}>{busy ? "Saving…" : "Confirm booking"}</button>
      </form>
    </Sheet>
  );
}

// ---------------------------------------------------------------- block time
export function BlockTime({ staff, startIso, onClose, onDone }: { staff: CalStaff; startIso: string; onClose: () => void; onDone: () => void }) {
  const [mins, setMins] = useState(60);
  const [reason, setReason] = useState("Break");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    const end = new Date(new Date(startIso).getTime() + mins * 60000).toISOString();
    try {
      await admin("/time-blocks", { method: "POST", body: JSON.stringify({ staff_id: staff.id, start: startIso, end, reason }) });
      onDone();
    } catch (e2) { setErr(e2 instanceof AdminError ? e2.message : "Failed"); } finally { setBusy(false); }
  }
  return (
    <Sheet title={`Block time · ${staff.name} · ${hm(startIso)}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Err msg={err} />
        <select className={field} value={mins} onChange={(e) => setMins(+e.target.value)} aria-label="Duration">
          {[15, 30, 45, 60, 90, 120, 180, 240, 480].map((m) => <option key={m} value={m}>{m >= 60 ? `${m / 60} h` : `${m} min`}</option>)}
        </select>
        <input className={field} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason" aria-label="Reason" />
        <button className={primary} disabled={busy}>{busy ? "Saving…" : "Block this time"}</button>
      </form>
    </Sheet>
  );
}

// ---------------------------------------------------------------- booking detail
export function BookingSheet({ id, role, onClose, onChanged }: { id: string; role: string; onClose: () => void; onChanged: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [mode, setMode] = useState<"view" | "reschedule" | "cancel">("view");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [override, setOverride] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const load = () => admin<Detail>(`/bookings/${id}`).then(setD).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  // refund status flips from "initiated" to "Refunded" when the webhook lands
  useEffect(() => {
    if (!d || !d.refunds.some((r) => r.status !== "processed")) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [d]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(path: string, body: unknown, after?: () => void) {
    setBusy(true); setErr(null);
    try { await admin(path, { method: "POST", body: JSON.stringify(body) }); after?.(); onChanged(); await load(); }
    catch (e) { setErr(e instanceof AdminError ? e.message : "Failed"); } finally { setBusy(false); }
  }

  if (!d) return <Sheet title="Booking" onClose={onClose}><Err msg={err} />{!err && <p className="text-stone-500">Loading…</p>}</Sheet>;
  const open = d.status === "confirmed" || d.status === "held";
  const refund = d.refunds[0];
  return (
    <Sheet title={`${d.service} · ${d.staff}`} onClose={onClose}>
      <Err msg={err} />
      {done && <p className="mb-3 rounded-lg bg-emerald-50 p-2 text-sm text-emerald-900">{done}</p>}
      {mode === "view" && (
        <>
          <div className="mb-3 space-y-1 rounded-2xl bg-white p-3 text-sm ring-1 ring-stone-200">
            <Row k="When" v={`${dayLabel(d.start)} · ${hm(d.start)}–${hm(d.end)}`} />
            <Row k="Status" v={d.status.replace("_", "-")} />
            <Row k="Customer" v={`${d.customer.name} · ${d.customer.phone}`} />
            <Row k="Source" v={d.source.replace("_", "-")} />
            <Row k="Price" v={`${inr(d.price_paise)} incl. GST`} />
            <Row k="Advance paid" v={inr(d.advance_paid_paise)} />
          </div>
          {d.payments.length > 0 && (
            <div className="mb-3 rounded-2xl bg-white p-3 text-xs ring-1 ring-stone-200">
              <p className="mb-1 text-sm font-medium">Payment</p>
              {d.payments.map((p) => (
                <div key={p.order_id} className="space-y-0.5">
                  <Row k="Order" v={p.order_id} mono /><Row k="Payment" v={p.payment_id ?? "—"} mono />
                  <Row k="Method" v={`${p.method ?? "—"} · ${inr(p.amount_paise)} · ${p.status}${p.is_seeded ? " (seeded)" : ""}`} />
                </div>
              ))}
              {refund && <p className="mt-1 font-medium text-amber-800">{refund.status === "processed" ? `Refunded ${inr(refund.amount_paise)}` : `Refund initiated · ${inr(refund.amount_paise)}`}</p>}
            </div>
          )}
          <details className="mb-3 rounded-2xl bg-white p-3 text-sm ring-1 ring-stone-200">
            <summary className="cursor-pointer font-medium">Messages ({d.messages.length})</summary>
            <ul className="mt-2 space-y-2">
              {d.messages.map((m, i) => (
                <li key={i} className={`rounded-lg p-2 text-xs ${m.direction === "in" ? "bg-emerald-50" : "bg-stone-50"}`}><span className="text-stone-500">{m.direction === "in" ? "Customer" : "Sent"} · {hm(m.at)}</span><br />{m.body}</li>
              ))}
              {d.messages.length === 0 && <li className="text-xs text-stone-500">No messages yet.</li>}
            </ul>
          </details>
          {open && (
            <div className="grid grid-cols-2 gap-2">
              {d.status === "confirmed" && <button className={primary} disabled={busy} onClick={() => act(`/bookings/${id}/status`, { status: "completed" })}>Mark completed</button>}
              {d.status === "confirmed" && <button className={ghost} disabled={busy} onClick={() => act(`/bookings/${id}/status`, { status: "no_show" })}>Mark no-show</button>}
              <button className={ghost} disabled={busy} onClick={() => setMode("reschedule")}>Reschedule</button>
              <button className="w-full rounded-xl bg-white px-4 py-3 font-medium text-red-700 ring-1 ring-red-200" onClick={() => setMode("cancel")}>Cancel</button>
            </div>
          )}
        </>
      )}
      {mode === "cancel" && (
        <div className="space-y-3">
          <div className="rounded-2xl bg-white p-4 ring-1 ring-stone-200">
            <p className="font-medium">{d.cancel_policy.text}</p>
            {d.advance_paid_paise === 0 && <p className="mt-1 text-sm text-stone-500">No advance was collected for this booking.</p>}
          </div>
          {!d.cancel_policy.refund_eligible && d.advance_paid_paise > 0 && role === "owner" && (
            <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="h-5 w-5" checked={override} onChange={(e) => setOverride(e.target.checked)} />Refund anyway ({inr(d.advance_paid_paise)})</label>
          )}
          <button className="w-full rounded-xl bg-red-700 px-4 py-3 font-semibold text-white disabled:opacity-50" disabled={busy}
            onClick={() => act(`/bookings/${id}/cancel`, { refund_override: override }, () => { setMode("view"); setDone("Booking cancelled. Refund initiated if applicable."); })}>
            {busy ? "Cancelling…" : "Confirm cancellation"}</button>
          <button className={ghost} onClick={() => setMode("view")}>Keep booking</button>
        </div>
      )}
      {mode === "reschedule" && <Reschedule d={d} onBack={() => setMode("view")} onMoved={() => { setMode("view"); setDone("Rescheduled. The customer was notified."); onChanged(); load(); }} />}
    </Sheet>
  );
}

function Reschedule({ d, onBack, onMoved }: { d: Detail; onBack: () => void; onMoved: () => void }) {
  const [date, setDate] = useState(d.start.slice(0, 10));
  const [slots, setSlots] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    admin<{ slots: string[] }>(`/slots?service_id=${d.service_id}&staff_id=${d.staff_id}&date=${date}&exclude_booking_id=${d.id}`)
      .then((r) => setSlots(r.slots)).catch((e) => setErr(e.message));
  }, [date, d]);
  async function move(start: string) {
    setBusy(true); setErr(null);
    try { await admin(`/bookings/${d.id}/reschedule`, { method: "POST", body: JSON.stringify({ start }) }); onMoved(); }
    catch (e) { setErr(e instanceof AdminError ? e.message : "Failed"); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-3">
      <Err msg={err} />
      <input type="date" className={field} value={date} onChange={(e) => setDate(e.target.value)} aria-label="New date" />
      <div className="grid grid-cols-3 gap-2">
        {slots.map((s) => <button key={s} disabled={busy} onClick={() => move(s)} className="rounded-xl bg-white py-3 text-sm font-medium ring-1 ring-stone-300 disabled:opacity-50">{hm(s)}</button>)}
      </div>
      {slots.length === 0 && <p className="text-sm text-stone-500">No free times for {d.staff} on this day.</p>}
      <button className={ghost} onClick={onBack}>Back</button>
    </div>
  );
}

const Row = ({ k, v, mono }: { k: string; v: string; mono?: boolean }) => (
  <div className="flex justify-between gap-3"><span className="text-stone-500">{k}</span><span className={`text-right ${mono ? "break-all font-mono" : ""}`}>{v}</span></div>
);
