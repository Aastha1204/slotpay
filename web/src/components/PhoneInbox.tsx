"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/supabase";

type Msg = { id: string; direction: "in" | "out"; body: string; buttons: { text: string; payload: string }[] | null; at: string };
type Inbox = {
  business: string; customer: string; phone: string; demo_delay_sec: number; booking_status: string;
  messages: Msg[]; reminders: { kind: string; status: string; in_sec: number }[];
};

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit", hour12: true }).toLowerCase();
const KIND: Record<string, string> = { remind_24h: "24-hour reminder", remind_2h: "2-hour reminder" };

/** Prototype: the customer's WhatsApp conversation for this booking, live. Shows the confirmation the moment it is sent,
 *  then each reminder as it arrives, with working Reschedule / Cancel buttons. */
export default function PhoneInbox({ token, onChange }: { token: string; onChange?: () => void }) {
  const [box, setBox] = useState<Inbox | null>(null);
  const [fetched, setFetched] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [alertText, setAlertText] = useState<string | null>(null);
  const [pressed, setPressed] = useState<Set<string>>(new Set());
  const count = useRef<number | null>(null);
  const chat = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/prototype/inbox/${token}`);
      if (!r.ok) return;
      const j: Inbox = await r.json();
      if (count.current !== null && j.messages.length > count.current) {
        const last = j.messages[j.messages.length - 1];
        if (last.direction === "out") {
          setAlertText(last.body.length > 78 ? `${last.body.slice(0, 78)}…` : last.body);
          try { navigator.vibrate?.(60); } catch { /* not supported */ }
          setTimeout(() => setAlertText(null), 4500);
        }
      }
      count.current = j.messages.length;
      setBox(j); setFetched(Date.now());
    } catch { /* server asleep: next poll retries */ }
  }, [token]);

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load(); const t = setInterval(load, 2000); return () => clearInterval(t); }, [load]);
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { if (chat.current) chat.current.scrollTop = chat.current.scrollHeight; }, [box?.messages.length]);

  async function press(b: { text: string; payload: string }) {
    if (pressed.has(b.payload)) return;
    setPressed((s) => new Set(s).add(b.payload));
    await fetch(`${API_BASE}/prototype/inbox/${token}/button`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).catch(() => {});
    await load();
    onChange?.();
  }

  const initials = (box?.business ?? "Glow Studio").split(" ").slice(0, 2).map((w) => w[0]).join("");
  const left = (sec: number) => Math.max(0, Math.round(sec - (now - fetched) / 1000));
  const pending = box?.reminders.filter((r) => r.status === "pending") ?? [];

  return (
    <aside aria-label="Customer's WhatsApp (live)" className="mx-auto w-full max-w-[320px]">
      <p className="mb-2 text-center text-xs font-bold uppercase tracking-[0.18em] text-brand-600">Customer&apos;s WhatsApp · live</p>
      <div className="relative rounded-[2.4rem] border-[10px] border-brand-800 bg-brand-800 shadow-[0_24px_50px_-20px_rgba(2,132,199,0.55)]">
        {alertText && (
          <div role="status" className="animate-step absolute inset-x-2 top-2 z-20 flex items-start gap-2 rounded-2xl bg-white/95 p-2.5 text-left text-xs shadow-lg ring-1 ring-brand-200">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#25d366] text-[10px] font-bold text-white">W</span>
            <span><b className="block text-brand-900">New WhatsApp message</b><span className="text-slate-600">{alertText}</span></span>
          </div>
        )}
        <div className="overflow-hidden rounded-[1.7rem] bg-[#e5ddd5]">
          <div className="flex items-center gap-2.5 bg-[#075e54] px-3 py-2.5 text-white">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-sm font-bold text-brand-800">{initials}</span>
            <div className="min-w-0 leading-tight"><p className="truncate text-sm font-semibold">{box?.business ?? "Glow Studio Salon & Spa"}</p><p className="text-[11px] opacity-80">Business account · {box?.phone ?? ""}</p></div>
          </div>
          <div ref={chat} className="h-[420px] space-y-2 overflow-y-auto p-2.5">
            {!box && <p className="mt-16 text-center text-xs text-slate-600">Connecting…</p>}
            {box && box.messages.length === 0 && <p className="mt-16 text-center text-xs text-slate-600">Waiting for the confirmation message…</p>}
            {box?.messages.map((m) => (
              <div key={m.id} className={`animate-step flex ${m.direction === "out" ? "justify-start" : "justify-end"}`}>
                <div className={`max-w-[88%] rounded-lg px-2.5 py-1.5 text-[13px] leading-snug shadow-sm ${m.direction === "out" ? "bg-white text-slate-900" : "bg-[#dcf8c6] text-slate-900"}`}>
                  <p className="whitespace-pre-wrap">{m.body}</p>
                  <p className="mt-0.5 text-right text-[10px] text-slate-500">{time(m.at)}{m.direction === "in" && " ✓✓"}</p>
                  {m.buttons && m.buttons.length > 0 && (
                    <div className="mt-1.5 space-y-1 border-t border-slate-200 pt-1.5">
                      {m.buttons.map((b) => (
                        <button key={b.payload} onClick={() => press(b)} disabled={pressed.has(b.payload) || box.booking_status === "cancelled"}
                          className="w-full rounded bg-slate-50 py-1.5 text-center text-[13px] font-semibold text-sky-700 transition hover:bg-sky-50 disabled:opacity-50">{b.text}</button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 rounded-2xl bg-white p-3 text-xs text-slate-600 ring-1 ring-brand-100">
        {pending.length > 0 ? (
          <ul className="space-y-1">
            {pending.map((r) => <li key={r.kind} className="flex justify-between"><span>{KIND[r.kind] ?? r.kind}</span><b className="text-brand-700">{box && box.demo_delay_sec > 0 ? `arrives in ${left(r.in_sec)} s` : "scheduled"}</b></li>)}
          </ul>
        ) : box && box.messages.length > 0 ? <p>All reminders sent{box.booking_status === "cancelled" ? " · booking cancelled" : ""}.</p> : <p>Messages appear here as they are sent.</p>}
        {box && box.demo_delay_sec > 0 && <p className="mt-2 border-t border-slate-100 pt-2 text-[11px] text-slate-500">Prototype speed-up: the &quot;24 h&quot; and &quot;2 h&quot; reminders arrive after {box.demo_delay_sec} s and {box.demo_delay_sec * 2} s so you can watch them. In production they follow the real appointment time.</p>}
      </div>
    </aside>
  );
}
