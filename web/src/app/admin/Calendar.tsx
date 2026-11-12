"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { PROTOTYPE } from "@/lib/prototype";
import { AdminError, CalBooking, CalStaff, Calendar, admin, signOut } from "@/lib/admin";
import { BlockTime, BookingSheet, CellSheet, QuickAdd, dayLabel, hm, inr } from "./Sheets";

const ROW = 24; // px per 15 minutes (96 px per hour)
const HEAD = 56; // sticky column header height
const mins = (iso: string) => +iso.slice(11, 13) * 60 + +iso.slice(14, 16);
const istToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
const addDays = (d: string, n: number) => new Date(new Date(`${d}T00:00:00Z`).getTime() + n * 86400000).toISOString().slice(0, 10);
const nowMin = () => { const p = new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour12: false }); return +p.slice(0, 2) * 60 + +p.slice(3, 5); };
const mmss = (ms: number) => { const s = Math.max(0, Math.floor(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const clock = (m: number) => { const h = Math.floor(m / 60); return `${h % 12 || 12}:${String(m % 60).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };
const hourLabel = (m: number) => { const h = Math.floor(m / 60); return `${h % 12 || 12} ${h < 12 ? "AM" : "PM"}`; };
const longDay = (d: string) => new Date(`${d}T00:00:00+05:30`).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", weekday: "long", day: "numeric", month: "long" });
const hatch = "bg-[repeating-linear-gradient(135deg,rgba(148,163,184,0.16)_0,rgba(148,163,184,0.16)_6px,transparent_6px,transparent_12px)]";

type Look = { box: string; tag: string | null };
const LOOK: Record<string, Look> = {
  confirmed: { box: "bg-brand-100 border-brand-600 text-brand-900", tag: null },
  completed: { box: "bg-emerald-100 border-emerald-600 text-emerald-950", tag: "Done" },
  no_show: { box: "bg-red-50 border-red-500 text-red-900", tag: "No-show" },
  held: { box: "border-amber-500 text-amber-950 bg-[repeating-linear-gradient(45deg,#fef3c7,#fef3c7_6px,#fde68a_6px,#fde68a_12px)]", tag: "Awaiting payment" },
  cancelled: { box: "bg-stone-100 border-stone-300 text-stone-500 opacity-70", tag: "Cancelled" },
};
const SOURCE: Record<string, string> = { online: "Online", walk_in: "Walk-in", phone: "Phone" };

export default function CalendarView() {
  const router = useRouter();
  const [date, setDate] = useState(istToday());
  const [view, setView] = useState<"day" | "week">("day");
  const [weekStaff, setWeekStaff] = useState<string | null>(null);
  const [cal, setCal] = useState<Calendar | null>(null);
  const [role, setRole] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [cell, setCell] = useState<{ staff: CalStaff; iso: string } | null>(null);
  const [mode, setMode] = useState<"booking" | "block" | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [hover, setHover] = useState<{ key: string; m: number } | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const seen = useRef<Set<string> | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const scrolledFor = useRef<string>("");

  const load = useCallback(async () => {
    try {
      const c = await admin<Calendar>(`/calendar?date=${date}&view=${view}`);
      // new online booking -> highlight + toast (first load only sets the baseline)
      const ids = new Set(c.bookings.map((b) => b.id));
      if (seen.current) {
        const added = c.bookings.filter((b) => !seen.current!.has(b.id) && b.status === "confirmed" && b.source === "online");
        if (added.length) {
          const b = added[0];
          setToast(`New booking · ${b.customer.split(" ").map((w, i) => (i ? w[0] + "." : w)).join(" ")} · ${b.service} · ${dayLabel(b.start)} ${hm(b.start)} · ${inr(b.advance_paid_paise)} paid`);
          setFresh(new Set(added.map((a) => a.id)));
          setTimeout(() => setFresh(new Set()), 6000);
          setTimeout(() => setToast(null), 7000);
        }
      }
      seen.current = ids;
      setCal(c); setError(null);
    } catch (e) {
      if (e instanceof AdminError && (e.status === 401 || e.status === 403)) { router.push("/admin/login"); return; }
      setError(e instanceof AdminError ? e.message : "Failed to load");
    }
  }, [date, view, router]);

  useEffect(() => { seen.current = null; }, [date, view]);
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, [load]);
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { admin<{ role: string }>("/me").then((m) => setRole(m.role)).catch(() => {}); }, []);
  useEffect(() => {
    if (!cal?.business_id || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) return;
    const ch = supabase.channel(`admin:${cal.business_id}`).on("broadcast", { event: "*" }, () => load()).subscribe();
    return () => { supabase.removeChannel(ch); };
  }, [cal?.business_id, load]);

  const staffList = useMemo(() => cal?.staff ?? [], [cal]);
  const active = weekStaff ?? staffList[0]?.id ?? null;
  const today = istToday();
  const columns: { key: string; date: string; staff: CalStaff; label: string; sub: string }[] = useMemo(() => {
    if (!cal) return [];
    if (view === "day") return staffList.map((s) => ({ key: s.id, date, staff: s, label: s.name, sub: s.title }));
    const s = staffList.find((x) => x.id === active) ?? staffList[0];
    return s ? Array.from({ length: 7 }, (_, i) => { const d = addDays(cal.range_start, i); return { key: d, date: d, staff: s, label: dayLabel(d), sub: s.name }; }) : [];
  }, [cal, view, staffList, date, active]);

  const dayStart = cal?.day_start_min ?? 600;
  const dayEnd = cal?.day_end_min ?? 1260;
  const height = ((dayEnd - dayStart) / 15) * ROW;
  const hours: number[] = Array.from({ length: Math.max(0, (dayEnd - dayStart) / 60) + 1 }, (_, i) => dayStart + i * 60).filter((h) => h < dayEnd);

  // Open scrolled to "now" (today) or to the first booking of the visible range.
  useEffect(() => {
    if (!cal || !scroller.current) return;
    const sig = `${view}:${date}:${cal.range_start}`;
    if (scrolledFor.current === sig) return;
    scrolledFor.current = sig;
    const visible = cal.bookings.filter((b) => (view === "day" ? b.start.slice(0, 10) === date : true));
    const anchor = (view === "day" && date === today) ? nowMin() - 60 : (visible.length ? Math.min(...visible.map((b) => mins(b.start))) - 30 : dayStart);
    scroller.current.scrollTop = Math.max(0, ((anchor - dayStart) / 15) * ROW);
  }, [cal, view, date, today, dayStart]);

  const summary = useMemo(() => {
    if (!cal) return null;
    const rows = cal.bookings.filter((b) => (view === "day" ? b.start.slice(0, 10) === date : true) && b.status !== "cancelled");
    const live = rows.filter((b) => b.status !== "held");
    return {
      count: live.length,
      held: rows.filter((b) => b.status === "held").length,
      revenue: live.filter((b) => b.status !== "no_show").reduce((s, b) => s + b.price_paise, 0),
      advance: live.reduce((s, b) => s + b.advance_paid_paise, 0),
      online: live.filter((b) => b.source === "online").length,
    };
  }, [cal, view, date]);

  function slotFromEvent(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    return dayStart + Math.floor((e.clientY - rect.top) / ROW) * 15;
  }
  function clickCell(e: React.MouseEvent<HTMLDivElement>, col: (typeof columns)[number]) {
    const m = slotFromEvent(e);
    setCell({ staff: col.staff, iso: `${col.date}T${hhmm(m)}:00+05:30` }); setMode(null);
  }

  const nowVisible = !!cal && (view === "day" ? date === today : cal.range_start <= today && today <= addDays(cal.range_start, 6)) && nowMin() >= dayStart && nowMin() <= dayEnd;
  const chip = "rounded-lg px-3 py-2 ring-1 ring-brand-200 bg-white text-sm font-medium text-brand-800 transition hover:bg-brand-50";
  return (
    <main className="min-h-screen bg-cream text-brand-900">
      <header className="sticky top-0 z-30 flex flex-wrap items-center gap-2 border-b border-line bg-white/90 px-3 py-2 backdrop-blur">
        <h1 className="mr-2 text-lg font-bold tracking-tight">Glow Studio</h1>
        <button aria-label="Previous" className={chip} onClick={() => setDate(addDays(date, view === "week" ? -7 : -1))}>‹</button>
        <button className={chip} onClick={() => setDate(today)}>Today</button>
        <button aria-label="Next" className={chip} onClick={() => setDate(addDays(date, view === "week" ? 7 : 1))}>›</button>
        <input type="date" aria-label="Date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} className={`${chip} py-[7px]`} />
        <div className="flex overflow-hidden rounded-lg ring-1 ring-brand-200">
          {(["day", "week"] as const).map((v) => <button key={v} onClick={() => setView(v)} className={`px-4 py-2 text-sm font-medium ${view === v ? "bg-brand-700 text-white" : "bg-white text-brand-800"}`}>{v === "day" ? "Day" : "Week"}</button>)}
        </div>
        {view === "week" && (
          <select aria-label="Stylist" value={active ?? ""} onChange={(e) => setWeekStaff(e.target.value)} className={chip}>
            {staffList.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
        <span className="ml-auto flex items-center gap-3 text-xs text-slate-500">
          {role === "owner" && <a href="/admin/manage" className={chip}>Manage</a>}
          {role && <span className="rounded-full bg-brand-50 px-2.5 py-1 font-semibold capitalize text-brand-700">{role.replace("_", " ")}</span>}
          {!PROTOTYPE && <button className="underline" onClick={async () => { await signOut(); router.push("/admin/login"); }}>Sign out</button>}
        </span>
      </header>

      {toast && <div role="status" className="fixed inset-x-3 top-16 z-40 mx-auto max-w-xl animate-[pop_.3s_ease-out] rounded-xl bg-brand-700 px-4 py-3 text-center text-sm text-white shadow-lg">{toast}</div>}
      {error && <p role="alert" className="m-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {!cal && !error && <div className="m-4 h-96 animate-pulse rounded-2xl bg-brand-100" />}

      {cal && summary && (
        <div className="px-3 pb-6 pt-3">
          <div className="mb-3 flex flex-wrap items-end gap-x-6 gap-y-2">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight">{view === "day" ? longDay(date) : `${dayLabel(cal.range_start)} – ${dayLabel(addDays(cal.range_start, 6))}`}</h2>
              <p className="text-sm text-slate-500">{view === "day" ? (date === today ? "Today" : date < today ? "Past day" : "Upcoming") : "Week view · one stylist at a time"} · tap an empty slot to add a booking or block time</p>
            </div>
            <dl className="ml-auto flex flex-wrap gap-2 text-sm" aria-label="Summary">
              {[["Bookings", String(summary.count)], ["Online", String(summary.online)], ["Booked value", inr(summary.revenue)], ["Advance collected", inr(summary.advance)], ...(summary.held ? [["Awaiting payment", String(summary.held)]] : [])].map(([k, v]) => (
                <div key={k} className="rounded-xl bg-white px-3 py-1.5 ring-1 ring-brand-100"><dt className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{k}</dt><dd className="text-base font-bold text-brand-800">{v}</dd></div>
              ))}
            </dl>
          </div>
          <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600" aria-label="Legend">
            {[["Confirmed", "bg-brand-100 border-brand-600"], ["Completed", "bg-emerald-100 border-emerald-600"], ["No-show", "bg-red-50 border-red-500"], ["Awaiting payment", "bg-amber-100 border-amber-500"], ["Blocked / leave", "bg-slate-300 border-slate-400"]].map(([l, c]) => (
              <li key={l} className="flex items-center gap-1.5"><span className={`inline-block h-3 w-3 rounded-sm border-l-4 ${c}`} />{l}</li>
            ))}
            <li className="flex items-center gap-1.5"><span className={`inline-block h-3 w-3 rounded-sm border border-slate-300 ${hatch}`} />Break / off shift</li>
            <li className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 bg-red-500" />Now</li>
          </ul>

          <div ref={scroller} className="max-h-[calc(100vh-250px)] min-h-[420px] overflow-auto rounded-2xl border border-line bg-white shadow-[0_12px_32px_-18px_rgba(2,132,199,0.35)]">
            <div className="relative flex" style={{ minWidth: view === "week" ? 900 : Math.max(680, 64 + columns.length * 170) }}>
              {/* time gutter */}
              <div className="sticky left-0 z-20 w-16 shrink-0 border-r border-line bg-white">
                <div className="sticky top-0 z-10 border-b border-line bg-white" style={{ height: HEAD }} />
                <div className="relative" style={{ height }}>
                  {hours.map((h) => <span key={h} className="absolute right-2 -translate-y-1/2 whitespace-nowrap text-[11px] font-medium text-slate-500" style={{ top: ((h - dayStart) / 15) * ROW }}>{h === dayStart || (nowVisible && Math.abs(nowMin() - h) < 14) ? "" : hourLabel(h)}</span>)}
                  {nowVisible && (
                    <span className="absolute right-1 z-10 -translate-y-1/2 rounded bg-red-500 px-1 text-[10px] font-bold text-white" style={{ top: ((nowMin() - dayStart) / 15) * ROW }}>{clock(nowMin()).replace(" ", "")}</span>
                  )}
                </div>
              </div>

              {columns.map((col) => {
                const bks = cal.bookings.filter((b) => b.staff_id === col.staff.id && b.start.slice(0, 10) === col.date);
                const blocks = cal.time_blocks.filter((t) => t.staff_id === col.staff.id && t.start.slice(0, 10) === col.date);
                const isToday = col.date === today;
                const live = bks.filter((b) => b.status !== "cancelled").length;
                const dayOff = view === "day" ? col.staff.working.length === 0 : false;
                return (
                  <div key={col.key} className="min-w-[150px] flex-1 border-r border-line last:border-r-0">
                    <div className={`sticky top-0 z-10 flex flex-col items-center justify-center border-b border-line px-2 ${isToday && view === "week" ? "bg-brand-50" : "bg-white"}`} style={{ height: HEAD }}>
                      <span className="truncate text-sm font-bold">{col.label}{isToday && view === "week" && <span className="ml-1.5 rounded bg-brand-700 px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">Today</span>}</span>
                      <span className="truncate text-[11px] text-slate-500">{col.sub} · {dayOff ? "day off" : `${live} booking${live === 1 ? "" : "s"}`}</span>
                    </div>
                    <div className="relative cursor-pointer" style={{ height }} data-testid={`col-${col.staff.name}-${col.date}`}
                      onClick={(e) => clickCell(e, col)}
                      onMouseMove={(e) => { const m = slotFromEvent(e); setHover((h) => (h && h.key === col.key && h.m === m ? h : { key: col.key, m })); }}
                      onMouseLeave={() => setHover(null)}>
                      {hours.map((h) => <div key={h} className="absolute inset-x-0 border-t border-slate-200" style={{ top: ((h - dayStart) / 15) * ROW }} />)}
                      {hours.map((h) => <div key={`h${h}`} className="absolute inset-x-0 border-t border-dashed border-slate-100" style={{ top: ((h + 30 - dayStart) / 15) * ROW }} />)}
                      {view === "day" && <OffShift staff={col.staff} dayStart={dayStart} dayEnd={dayEnd} />}
                      {hover && hover.key === col.key && !dayOff && (
                        <div className="pointer-events-none absolute inset-x-1 z-[5] flex items-center justify-center rounded-md border border-dashed border-brand-400 bg-brand-50/70 text-[11px] font-semibold text-brand-700" style={{ top: ((hover.m - dayStart) / 15) * ROW, height: ROW }}>+ Add at {clock(hover.m)}</div>
                      )}
                      {blocks.map((t) => (
                        <div key={t.id} onClick={(e) => { e.stopPropagation(); if (confirm(`Remove block "${t.reason}"?`)) admin(`/time-blocks/${t.id}`, { method: "DELETE" }).then(load); }}
                          className={`absolute inset-x-1 z-[6] overflow-hidden rounded-md border border-slate-300 bg-slate-200/90 px-1.5 py-0.5 text-[11px] font-medium text-slate-700 ${hatch}`}
                          style={{ top: ((mins(t.start) - dayStart) / 15) * ROW, height: ((mins(t.end) - mins(t.start)) / 15) * ROW - 1 }}>{t.reason || "Blocked"} · {clock(mins(t.start))}–{clock(mins(t.end))}</div>
                      ))}
                      {bks.filter((b) => b.status !== "cancelled").map((b) => <Block key={b.id} b={b} dayStart={dayStart} now={now} hl={fresh.has(b.id)} onOpen={() => setOpenId(b.id)} />)}
                      {isToday && <div className="pointer-events-none absolute inset-x-0 z-10 border-t-2 border-red-500" style={{ top: ((nowMin() - dayStart) / 15) * ROW }}><span className="absolute -left-1 -top-[5px] h-2 w-2 rounded-full bg-red-500" /></div>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {cell && !mode && <CellSheet staff={cell.staff} startIso={cell.iso} onClose={() => setCell(null)} onPick={setMode} />}
      {cell && mode === "booking" && cal && <QuickAdd cal={cal} staff={cell.staff} startIso={cell.iso} onClose={() => { setCell(null); setMode(null); }}
        onDone={(id) => { setCell(null); setMode(null); setOpenId(id); load(); }} />}
      {cell && mode === "block" && <BlockTime staff={cell.staff} startIso={cell.iso} onClose={() => { setCell(null); setMode(null); }} onDone={() => { setCell(null); setMode(null); load(); }} />}
      {openId && <BookingSheet id={openId} role={role} onClose={() => setOpenId(null)} onChanged={load} />}
    </main>
  );
}

function OffShift({ staff, dayStart, dayEnd }: { staff: CalStaff; dayStart: number; dayEnd: number }) {
  const m = (s: string) => +s.slice(0, 2) * 60 + +s.slice(3, 5);
  const shade = `pointer-events-none absolute inset-x-0 ${hatch} bg-slate-50`;
  const out: React.ReactNode[] = [];
  if (staff.working.length === 0) {
    return <div className={`${shade} flex items-center justify-center text-sm font-semibold text-slate-400`} style={{ top: 0, bottom: 0 }}>Day off</div>;
  }
  const w = staff.working;
  const first = m(w[0].start), last = m(w[w.length - 1].end);
  if (first > dayStart) out.push(<div key="a" className={shade} style={{ top: 0, height: ((first - dayStart) / 15) * ROW }} />);
  if (last < dayEnd) out.push(<div key="b" className={shade} style={{ top: ((last - dayStart) / 15) * ROW, bottom: 0 }} />);
  staff.breaks.forEach((b, i) => out.push(
    <div key={`br${i}`} className={`pointer-events-none absolute inset-x-0 z-[1] flex items-center justify-center border-y border-slate-200 bg-slate-100/80 text-[11px] font-semibold text-slate-500 ${hatch}`}
      style={{ top: ((m(b.start) - dayStart) / 15) * ROW, height: ((m(b.end) - m(b.start)) / 15) * ROW }}>Break</div>));
  return <>{out}</>;
}

function Block({ b, dayStart, now, hl, onOpen }: { b: CalBooking; dayStart: number; now: number; hl: boolean; onOpen: () => void }) {
  const s = mins(b.start), e = mins(b.end);
  const top = ((s - dayStart) / 15) * ROW, h = ((e - s) / 15) * ROW - 2;
  const look = LOOK[b.status] ?? LOOK.confirmed;
  const left = b.hold_expires_at ? new Date(b.hold_expires_at).getTime() - now : 0;
  const compact = h < 44;
  return (
    <button onClick={(ev) => { ev.stopPropagation(); onOpen(); }} data-testid={`booking-${b.id}`} title={`${b.customer} · ${b.service} · ${clock(s)}–${clock(e)}`}
      className={`absolute inset-x-1 z-[7] overflow-hidden rounded-lg border-l-4 px-2 py-1 text-left text-[11px] leading-snug shadow-sm transition hover:z-20 hover:shadow-md ${look.box} ${hl ? "animate-pulse ring-2 ring-brand-600" : ""}`}
      style={{ top, height: h }}>
      {compact ? (
        <span className="block truncate"><b>{clock(s)}</b> {b.customer} · {b.service}</span>
      ) : (
        <>
          <span className="flex items-center justify-between gap-1 text-[10px] font-semibold opacity-80"><span>{clock(s)} – {clock(e)}</span>{look.tag && b.status !== "held" && <span className="rounded bg-white/70 px-1">{look.tag}</span>}</span>
          <span className="block truncate text-xs font-bold">{b.customer}</span>
          <span className="block truncate">{b.service}</span>
          {b.status === "held"
            ? <span className="block font-semibold">Awaiting payment · {mmss(left)}</span>
            : h > 70 && <span className="block truncate text-[10px] opacity-75">{SOURCE[b.source] ?? b.source}{b.advance_paid_paise > 0 ? ` · ${inr(b.advance_paid_paise)} paid` : ""}</span>}
        </>
      )}
    </button>
  );
}
