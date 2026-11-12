"use client";
import type { Day } from "@/lib/booking";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

const parts = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return { y, m, d, wd: (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7 };
};

/** Full calendar grid (weeks start Monday) for the bookable window. Each day shows how many times are free. */
export default function MonthCalendar({ days, selected, onPick }: { days: Day[]; selected: string | null; onPick: (date: string) => void }) {
  if (days.length === 0) {
    return <div className="grid grid-cols-7 gap-1.5" aria-busy="true">{Array.from({ length: 35 }, (_, i) => <div key={i} className="aspect-square animate-pulse rounded-2xl bg-brand-100" />)}</div>;
  }
  const first = parts(days[0].date), last = parts(days[days.length - 1].date);
  const cells: (Day | null)[] = [...Array(first.wd).fill(null), ...days];
  while (cells.length % 7) cells.push(null);
  const title = first.m === last.m ? `${MONTH_FULL[first.m - 1]} ${first.y}` : `${MONTH_FULL[first.m - 1]} – ${MONTH_FULL[last.m - 1]} ${last.y}`;
  const bookable = days.filter((d) => d.count > 0).length;

  return (
    <div>
      <div className="mb-3 flex items-end justify-between">
        <h3 className="text-xl font-extrabold tracking-tight">{title}</h3>
        <p className="text-xs text-slate-500">{bookable} days with free times</p>
      </div>
      <div className="grid grid-cols-7 gap-1.5 sm:gap-2" role="grid" aria-label="Choose a date">
        {WEEKDAYS.map((w) => <div key={w} role="columnheader" className="pb-1 text-center text-[11px] font-bold uppercase tracking-wide text-slate-500">{w}</div>)}
        {cells.map((d, i) => {
          if (!d) return <div key={`e${i}`} aria-hidden />;
          const p = parts(d.date);
          const off = d.closed !== null || d.count === 0;
          const sel = selected === d.date;
          const label = `${WEEKDAYS[p.wd]} ${p.d} ${MONTHS[p.m - 1]}${d.closed === "holiday" ? ", closed" : d.closed === "out_of_range" ? ", not open for booking yet" : d.count === 0 ? ", fully booked" : `, ${d.count} ${d.count === 1 ? "time" : "times"} available`}`;
          const level = d.count >= 8 ? "bg-emerald-500" : d.count >= 4 ? "bg-amber-400" : "bg-orange-500";
          return (
            <button key={d.date} role="gridcell" disabled={off} aria-label={label} aria-selected={sel} onClick={() => onPick(d.date)}
              className={`relative flex min-h-[54px] flex-col items-center justify-center rounded-2xl border px-0.5 py-1.5 text-center transition sm:min-h-[66px] ${
                sel ? "border-brand-700 bg-brand-700 text-white shadow-[0_10px_22px_-8px_rgba(2,132,199,0.6)]"
                  : off ? "cursor-not-allowed border-transparent bg-slate-50 text-slate-400"
                  : "raise border-line bg-white text-brand-900 hover:border-brand-300"}`}>
              {p.d === 1 && <span className={`absolute left-1 top-0.5 text-[9px] font-bold uppercase ${sel ? "text-brand-100" : "text-brand-600"}`}>{MONTHS[p.m - 1]}</span>}
              <span className={`text-base font-bold sm:text-lg ${off && !sel ? "font-medium" : ""}`}>{p.d}</span>
              <span className={`mt-0.5 flex items-center gap-1 text-[10px] font-semibold leading-none ${sel ? "text-brand-100" : off ? "text-slate-400" : "text-slate-600"}`}>
                {d.closed === "holiday" ? "Closed" : d.closed === "out_of_range" ? "" : d.count === 0 ? "Full" : (<><span className={`h-1.5 w-1.5 rounded-full ${sel ? "bg-white" : level}`} /><span>{d.count}<span className="hidden sm:inline"> {d.count === 1 ? "time" : "times"}</span></span></>)}
              </span>
              {d.date === days[0].date && <span className={`absolute -bottom-1 left-1/2 -translate-x-1/2 rounded-full px-1.5 text-[8px] font-bold uppercase ${sel ? "bg-white text-brand-700" : "bg-brand-700 text-white"}`}>Today</span>}
            </button>
          );
        })}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500" aria-label="Legend">
        <li className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-500" />Plenty of times</li>
        <li className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-400" />Filling up</li>
        <li className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-orange-500" />Last few</li>
        <li>The number is how many start times are free that day</li>
      </ul>
    </div>
  );
}
